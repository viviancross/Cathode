"""The remote control: every input device becomes the same small set of
buttons a satellite box's remote has. Screens only ever see these names.

Keyboard, media keys (so a FLIRC or Media Center remote just works), and any
SDL game controller map onto them. Mappings are overridable from config.
"""

import pygame
from pygame._sdl2 import controller as sdl_controller

# The buttons. Plain strings so config files and tests can name them.
UP, DOWN, LEFT, RIGHT, SELECT = "UP", "DOWN", "LEFT", "RIGHT", "SELECT"
BACK, EXIT, MENU, GUIDE, INFO = "BACK", "EXIT", "MENU", "GUIDE", "INFO"
CH_UP, CH_DOWN, PREV = "CH_UP", "CH_DOWN", "PREV"
PAGE_UP, PAGE_DOWN = "PAGE_UP", "PAGE_DOWN"
VOL_UP, VOL_DOWN, MUTE = "VOL_UP", "VOL_DOWN", "MUTE"
PAUSE, PLAY, STOP, REW, FF, REPLAY, SKIP = "PAUSE", "PLAY", "STOP", "REW", "FF", "REPLAY", "SKIP"
FAV, THEMES, BROWSE, LIST = "FAV", "THEMES", "BROWSE", "LIST"
FULLSCREEN, QUIT, FORMAT = "FULLSCREEN", "QUIT", "FORMAT"
DIGITS = [f"DIGIT{i}" for i in range(10)]

# Buttons a user can rebind, in the order the remap menu lists them.
BINDABLE = [GUIDE, INFO, MENU, EXIT, BACK, SELECT, UP, DOWN, LEFT, RIGHT, CH_UP, CH_DOWN,
            PAGE_UP, PAGE_DOWN, PREV, FAV, BROWSE, THEMES, PAUSE, REW, FF, SKIP,
            VOL_UP, VOL_DOWN, MUTE, FORMAT, FULLSCREEN, QUIT]

# Held, these repeat (menus and the guide scroll; channels don't race away).
REPEATABLE = {UP, DOWN, LEFT, RIGHT, PAGE_UP, PAGE_DOWN, VOL_UP, VOL_DOWN, BACK}


def _k(name):
    """pygame key constant by name, or None on an SDL without it."""
    return getattr(pygame, name, None)


DEFAULT_KEYS = {
    "K_UP": UP, "K_DOWN": DOWN, "K_LEFT": LEFT, "K_RIGHT": RIGHT,
    "K_RETURN": SELECT, "K_KP_ENTER": SELECT,
    "K_BACKSPACE": BACK, "K_ESCAPE": EXIT,
    "K_c": MENU, "K_g": GUIDE, "K_i": INFO, "K_TAB": INFO,
    "K_PAGEUP": PAGE_UP, "K_PAGEDOWN": PAGE_DOWN,
    "K_p": PREV, "K_BACKQUOTE": PREV,
    "K_EQUALS": VOL_UP, "K_PLUS": VOL_UP, "K_KP_PLUS": VOL_UP,
    "K_MINUS": VOL_DOWN, "K_KP_MINUS": VOL_DOWN, "K_m": MUTE,
    "K_SPACE": PAUSE, "K_COMMA": REW, "K_PERIOD": FF,
    "K_f": FAV, "K_t": THEMES, "K_b": BROWSE, "K_l": LIST,
    "K_w": FULLSCREEN, "K_F11": FULLSCREEN, "K_q": QUIT, "K_a": FORMAT,
    # Media keys: IR receivers and media remotes send these.
    "K_AUDIOPLAY": PAUSE, "K_AUDIOSTOP": STOP, "K_AUDIONEXT": SKIP, "K_AUDIOPREV": REPLAY,
    "K_AUDIOREWIND": REW, "K_AUDIOFASTFORWARD": FF, "K_AUDIOMUTE": MUTE, "K_MUTE": MUTE,
    "K_VOLUMEUP": VOL_UP, "K_VOLUMEDOWN": VOL_DOWN, "K_AC_BACK": BACK, "K_MENU": MENU,
}
for _i in range(10):
    DEFAULT_KEYS[f"K_{_i}"] = DIGITS[_i]
    DEFAULT_KEYS[f"K_KP{_i}"] = DIGITS[_i]

DEFAULT_PAD = {
    "A": SELECT, "B": BACK, "X": GUIDE, "Y": INFO,
    "BACK": MENU, "START": MENU, "GUIDE": EXIT,
    "LEFTSHOULDER": CH_DOWN, "RIGHTSHOULDER": CH_UP,
    "LEFTSTICK": MUTE, "RIGHTSTICK": PREV,
    "DPAD_UP": UP, "DPAD_DOWN": DOWN, "DPAD_LEFT": LEFT, "DPAD_RIGHT": RIGHT,
    "TRIGGERLEFT": VOL_DOWN, "TRIGGERRIGHT": VOL_UP,
}

_PAD_BUTTONS = {name: getattr(pygame, f"CONTROLLER_BUTTON_{name}") for name in DEFAULT_PAD
                if hasattr(pygame, f"CONTROLLER_BUTTON_{name}")}
_STICK_DIR = {(pygame.CONTROLLER_AXIS_LEFTX, -1): LEFT, (pygame.CONTROLLER_AXIS_LEFTX, 1): RIGHT,
              (pygame.CONTROLLER_AXIS_LEFTY, -1): UP, (pygame.CONTROLLER_AXIS_LEFTY, 1): DOWN}
_TRIGGERS = {pygame.CONTROLLER_AXIS_TRIGGERLEFT: "TRIGGERLEFT",
             pygame.CONTROLLER_AXIS_TRIGGERRIGHT: "TRIGGERRIGHT"}
_AXIS_ON, _AXIS_OFF = 20000, 12000   # hysteresis, so a resting stick can't chatter


def pad_button_name(code: int) -> str:
    return {v: k for k, v in _PAD_BUTTONS.items()}.get(code, "")


class Remote:
    """Turns pygame events into remote buttons. Press-and-release devices
    (controller axes) are edge-detected here; repeats for held controller
    buttons are driven by `held()`, polled by the kernel's repeat timer."""

    def __init__(self, key_overrides=None, pad_overrides=None):
        self.keys = {}
        for name, action in DEFAULT_KEYS.items():
            code = _k(name)
            if code is not None:
                self.keys[code] = action
        for action, keyname in (key_overrides or {}).items():
            if action not in BINDABLE:
                continue            # e.g. a 3.x binding: its actions had other names
            try:
                self.keys = {c: a for c, a in self.keys.items() if a != action}
                self.keys[pygame.key.key_code(keyname)] = action
            except (ValueError, TypeError):
                pass        # unknown key name in config: keep the default
        pad = dict(DEFAULT_PAD)
        for action, button in (pad_overrides or {}).items():
            if action not in BINDABLE:
                continue
            pad = {b: a for b, a in pad.items() if a != action}
            pad[button.upper()] = action
        self.pad = {_PAD_BUTTONS[b]: a for b, a in pad.items() if b in _PAD_BUTTONS}
        self.pad_names = pad        # button name -> action, for the remap menu
        self.pad_axes = {axis: pad.get(name) for axis, name in _TRIGGERS.items()}
        self._axis_down = set()     # (instance, axis, sign) currently past threshold
        self.held_action = None     # controller direction/button now held, for repeat
        self.controllers = {}

    def key_for(self, action: str) -> str:
        """Display name of the keys bound to an action (the remap menu)."""
        names = sorted({pygame.key.name(c) for c, a in self.keys.items() if a == action})
        return ", ".join(n for n in names if n)[:24] or "-"

    def pad_for(self, action: str) -> str:
        return ", ".join(sorted(b for b, a in self.pad_names.items() if a == action)) or "-"

    def translate(self, e) -> list:
        """Remote buttons this event presses (usually zero or one)."""
        t = e.type
        if t == pygame.KEYDOWN:
            a = self.keys.get(e.key)
            return [a] if a else []
        if t == pygame.CONTROLLERBUTTONDOWN:
            a = self.pad.get(e.button)
            if a:
                self.held_action = a
            return [a] if a else []
        if t == pygame.CONTROLLERBUTTONUP:
            if self.pad.get(e.button) == self.held_action:
                self.held_action = None
            return []
        if t == pygame.CONTROLLERAXISMOTION:
            return self._axis(e)
        if t == pygame.MOUSEWHEEL:
            return [UP] if e.y > 0 else [DOWN] if e.y < 0 else []
        if t == pygame.CONTROLLERDEVICEADDED:
            try:
                c = sdl_controller.Controller(e.device_index)
                self.controllers[c.id] = c
                print(f"[remote] controller connected: {c.name}")
            except pygame.error:
                pass
        elif t == pygame.CONTROLLERDEVICEREMOVED:
            self.controllers.pop(e.instance_id, None)
            self.held_action = None
        return []

    def _axis(self, e) -> list:
        out = []
        if e.axis in _TRIGGERS:
            key = (e.instance_id, e.axis, 1)
            action = self.pad_axes.get(e.axis)
            if e.value > _AXIS_ON and key not in self._axis_down:
                self._axis_down.add(key)
                if action:
                    out.append(action)
                    self.held_action = action
            elif e.value < _AXIS_OFF and key in self._axis_down:
                self._axis_down.discard(key)
                if self.held_action == action:
                    self.held_action = None
            return out
        for sign in (-1, 1):
            action = _STICK_DIR.get((e.axis, sign))
            if not action:
                continue
            key = (e.instance_id, e.axis, sign)
            if e.value * sign > _AXIS_ON and key not in self._axis_down:
                self._axis_down.add(key)
                out.append(action)
                self.held_action = action
            elif e.value * sign < _AXIS_OFF and key in self._axis_down:
                self._axis_down.discard(key)
                if self.held_action == action:
                    self.held_action = None
        return out

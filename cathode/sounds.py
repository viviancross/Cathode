"""The box's UI sounds. Only the HR20 made any (docs/cathode-4/box-behaviour.md):
"beeps and boops" on key presses and a low "bonk" on an error, from its
2007-08 firmware on, with Audio > Sound Effects setting their volume. No
clean recording of them exists, so these are synthesised to the
descriptions; a real sample dropped in assets/sounds/key.wav or bonk.wav
takes over.

Played through pygame's mixer, apart from mpv's audio, so they sound over
the programme as the box's did."""

from __future__ import annotations

import array
import math
import os
from typing import Optional

import pygame

from . import paths

RATE = 44100
LEVELS = [("off", "Off"), ("low", "Low"), ("medium", "Medium"), ("high", "High")]
GAIN = {"off": 0.0, "low": 0.25, "medium": 0.5, "high": 0.9}


def _tone(seconds: float, freq, env, rate: int = RATE) -> pygame.mixer.Sound:
    """A mono tone: freq(t) and env(t) in 0..1 give the pitch and loudness
    along it. Built as stereo 16-bit, the mixer's format."""
    n = int(seconds * rate)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / rate
        phase += 2 * math.pi * freq(t) / rate
        v = int(32767 * 0.8 * env(t) * math.sin(phase))
        buf.append(v)
        buf.append(v)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def key_sound() -> pygame.mixer.Sound:
    """A short, soft tick: a 2.2 kHz blip that dies in 25 ms."""
    return _tone(0.025, lambda t: 2200, lambda t: min(1.0, t / 0.002) * math.exp(-t / 0.006))


def bonk_sound() -> pygame.mixer.Sound:
    """The error bonk: low, a quick droop in pitch, gone in 180 ms."""
    return _tone(0.18, lambda t: 220 * math.exp(-t / 0.25) + 60,
                 lambda t: min(1.0, t / 0.004) * math.exp(-t / 0.07))


class Sounds:
    def __init__(self, level: str = "medium"):
        self.level = level
        self._ok = False
        self._key: Optional[pygame.mixer.Sound] = None
        self._bonk: Optional[pygame.mixer.Sound] = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=RATE, size=-16, channels=2, buffer=512)
            self._key = self._load("key.wav") or key_sound()
            self._bonk = self._load("bonk.wav") or bonk_sound()
            self._ok = True
        except Exception as e:          # no audio device: the box is just quiet
            print(f"[sounds] off: {e!r}")

    @staticmethod
    def _load(name: str) -> Optional[pygame.mixer.Sound]:
        p = os.path.join(paths.asset("sounds"), name)
        if os.path.isfile(p):
            try:
                return pygame.mixer.Sound(p)
            except pygame.error:
                return None
        return None

    def _play(self, s: Optional[pygame.mixer.Sound]):
        gain = GAIN.get(self.level, 0.0)
        if self._ok and s is not None and gain > 0:
            s.set_volume(gain)
            s.play()

    def key(self):
        self._play(self._key)

    def bonk(self):
        self._play(self._bonk)

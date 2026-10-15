"""Start Cathode when the user logs in: the per-user Run key on Windows, a
LaunchAgent on macOS, an XDG autostart entry on Linux. Nothing system-wide."""

import os
import shlex
import sys

_NAME = "Cathode"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def command() -> list:
    """How to start this install: the frozen executable, or this Python on
    main.py."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    exe = sys.executable
    if os.name == "nt":   # no console window at login
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = w if os.path.exists(w) else exe
    return [exe, main]


def _mac_plist() -> str:
    return os.path.expanduser(f"~/Library/LaunchAgents/io.cathode.{_NAME}.plist")


def _linux_desktop() -> str:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "autostart", "cathode.desktop")


def supported() -> bool:
    return sys.platform in ("win32", "darwin") or sys.platform.startswith("linux")


def enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, _NAME)
            return True
        except OSError:
            return False
    if sys.platform == "darwin":
        return os.path.exists(_mac_plist())
    return os.path.exists(_linux_desktop())


def mac_plist_text(cmd: list) -> str:
    from xml.sax.saxutils import escape
    args = "".join(f"\n        <string>{escape(a)}</string>" for a in cmd)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.cathode.{_NAME}</string>
    <key>ProgramArguments</key>
    <array>{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""


def linux_desktop_text(cmd: list) -> str:
    return ("[Desktop Entry]\nType=Application\nName=Cathode\n"
            f"Exec={' '.join(shlex.quote(a) for a in cmd)}\n"
            "X-GNOME-Autostart-enabled=true\n")


def set_enabled(on: bool):
    cmd = command()
    if sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, _NAME)
                except FileNotFoundError:
                    pass
        return
    path, text = ((_mac_plist(), mac_plist_text(cmd)) if sys.platform == "darwin"
                  else (_linux_desktop(), linux_desktop_text(cmd)))
    if on:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    elif os.path.exists(path):
        os.remove(path)

"""The announcer: "Coming up next on Nickelodeon: Rugrats", spoken over the
coming-up-next card. The system's own voice makes it (Windows' speech;
espeak-ng, espeak or pico2wave on Linux), once a line, kept as a WAV in the
cache folder and played through pygame's mixer. Where there's no voice to
be had it stays quiet."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading

from . import paths


def _dir() -> str:
    d = os.path.join(paths.cache_dir(), "voice")
    os.makedirs(d, exist_ok=True)
    return d


def can() -> bool:
    return os.name == "nt" or any(shutil.which(x) for x in ("espeak-ng", "espeak", "pico2wave"))


def synth(text: str, path: str) -> bool:
    """The line spoken into a WAV file; False when there's no voice."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if os.name == "nt":
        q = lambda s: s.replace("'", "''")     # noqa: E731  (PowerShell's single quotes)
        ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{q(path)}'); $s.Speak('{q(text)}'); $s.Dispose()")
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]
    elif shutil.which("espeak-ng") or shutil.which("espeak"):
        cmd = [shutil.which("espeak-ng") or shutil.which("espeak"), "-s", "150", "-w", path, text]
    elif shutil.which("pico2wave"):
        cmd = ["pico2wave", "-w", path, text]
    else:
        return False
    try:
        subprocess.run(cmd, timeout=30, capture_output=True, creationflags=flags)
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.exists(path) and os.path.getsize(path) > 100


def say(text: str, volume: float = 0.8):
    """Speaks a line, on a thread (made once, played from the file after)."""
    if not text:
        return

    def work():
        path = os.path.join(_dir(), hashlib.sha1(text.encode()).hexdigest()[:16] + ".wav")
        if not os.path.exists(path) and not synth(text, path):
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                return
            snd = pygame.mixer.Sound(path)
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
        except Exception as e:
            print(f"[announcer] {e!r}")
    threading.Thread(target=work, daemon=True).start()


def line(channel: str, nxt: dict) -> str:
    title = (nxt or {}).get("title")
    return f"Coming up next on {channel}: {title}." if title else ""

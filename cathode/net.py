"""Shared networking bits — one certifi-aware SSL context for every fetch.

macOS Pythons often ship without a usable CA bundle, so HTTPS verification
fails. certifi's bundle fixes that when present. Every module that fetches
over HTTPS (plex, updater, weather, EPG, playlists, logos) shares this
context instead of rolling its own.
"""

from __future__ import annotations

import ssl


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


SSL = _ssl_context()

_LOOPBACK = ("localhost", "127.0.0.1", "::1")


def as_seen_from(url: str, base: str) -> str:
    """`url`, handed out by the server at `base`. A server that writes its
    own 'localhost' into what it hands out (Tunarr keeps channel icon paths
    as the browser that uploaded them saw them) means itself, so from
    another machine that's base's host."""
    from urllib.parse import urlsplit, urlunsplit
    try:
        u, b = urlsplit(url or ""), urlsplit(base or "")
        if u.hostname not in _LOOPBACK or not b.hostname or b.hostname in _LOOPBACK:
            return url
        host = f"[{b.hostname}]" if ":" in b.hostname else b.hostname
        return urlunsplit(u._replace(netloc=host + (f":{u.port}" if u.port else "")))
    except ValueError:
        return url

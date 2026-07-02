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

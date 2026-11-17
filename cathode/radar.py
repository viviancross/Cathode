"""The weather channel's radar and the alerts.

Radar: RainViewer's free radar mosaic (the last hour, ten-minute frames)
over Esri's dark grey base map, a 3x3 block of map tiles round the place the
forecast is for, fetched on a thread every ten minutes. Only the map tiles'
coordinates leave the machine (a few hundred kilometres square).

Alerts: the US National Weather Service's active alerts for that point
(api.weather.gov), every five minutes, for the weather channel's alerts
page and the crawl over live TV when one is severe."""

from __future__ import annotations

import io
import json
import math
import threading
import time
import urllib.request
from typing import Optional

import pygame

from .net import SSL as _SSL

ZOOM = 6
TILE = 256
MAPS = "https://api.rainviewer.com/public/weather-maps.json"
BASE = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
RADAR_EVERY, ALERTS_EVERY = 600.0, 300.0
SEVERE = ("Severe", "Extreme")


def tile_of(lat: float, lon: float, z: int = ZOOM) -> tuple:
    """(x, y) of a point in tiles at zoom z (fractional)."""
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(max(-85.0, min(85.0, lat)))
    y = (1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n
    return x, y


def _get(url: str, ua: str, timeout: float = 12) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
        return r.read()


class Radar:
    def __init__(self, user_agent: str = "Cathode"):
        self.ua = user_agent
        self.where = None                   # (lat, lon) drawn for
        self.base: Optional[pygame.Surface] = None
        self.frames: list = []              # [(unix time, Surface)], oldest first
        self.offset = (0, 0)                # where the place is on the mosaic
        self._at = 0.0
        self._busy = False

    def get(self, lat: float, lon: float):
        """(base, frames, place's pixel) as they are; a refresh started when
        stale or for a new place."""
        if (not self._busy and (time.monotonic() - self._at > RADAR_EVERY or self.where != (lat, lon))):
            self._busy = True
            threading.Thread(target=self._fetch, args=(lat, lon), daemon=True).start()
        return self.base, self.frames, self.offset

    def _fetch(self, lat, lon):
        try:
            fx, fy = tile_of(lat, lon)
            cx, cy = int(fx), int(fy)
            n = 2 ** ZOOM

            def mosaic(url_of):
                out = pygame.Surface((TILE * 3, TILE * 3), pygame.SRCALPHA)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        x, y = (cx + dx) % n, cy + dy
                        if not 0 <= y < n:
                            continue
                        try:
                            img = pygame.image.load(io.BytesIO(_get(url_of(x, y), self.ua)), "t.png")
                        except Exception:
                            continue
                        out.blit(img, ((dx + 1) * TILE, (dy + 1) * TILE))
                return out
            base = mosaic(lambda x, y: BASE.format(z=ZOOM, x=x, y=y))
            maps = json.loads(_get(MAPS, self.ua))
            host = maps.get("host", "https://tilecache.rainviewer.com")
            frames = []
            for f in ((maps.get("radar") or {}).get("past") or [])[-6:]:
                frames.append((int(f.get("time", 0)), mosaic(
                    lambda x, y, p=f["path"]: f"{host}{p}/{TILE}/{ZOOM}/{x}/{y}/2/1_1.png")))
            self.base, self.frames = base, frames
            self.offset = (int((fx - cx + 1) * TILE), int((fy - cy + 1) * TILE))
            self.where = (lat, lon)
        except Exception as e:
            print(f"[radar] {e!r}")
        finally:
            self._at = time.monotonic()
            self._busy = False


class Alerts:
    """The NWS's active alerts for a point (US only)."""

    def __init__(self, user_agent: str = "Cathode"):
        self.ua = user_agent
        self.items: list = []
        self._at = 0.0
        self._busy = False
        self.where = None

    def get(self, lat: float, lon: float) -> list:
        if not self._busy and (time.monotonic() - self._at > ALERTS_EVERY or self.where != (lat, lon)):
            self._busy = True
            threading.Thread(target=self._fetch, args=(lat, lon), daemon=True).start()
        return self.items

    def severe(self) -> list:
        return [a for a in self.items if a.get("severity") in SEVERE]

    def _fetch(self, lat, lon):
        try:
            d = json.loads(_get(f"https://api.weather.gov/alerts/active?point={lat:.4f},{lon:.4f}", self.ua))
            self.items = [parse(f.get("properties") or {}) for f in d.get("features") or []]
            self.where = (lat, lon)
        except Exception as e:
            print(f"[alerts] {e!r}")
        finally:
            self._at = time.monotonic()
            self._busy = False


def parse(p: dict) -> dict:
    return {"event": p.get("event", ""), "headline": p.get("headline") or p.get("event", ""),
            "severity": p.get("severity", ""), "expires": p.get("expires") or p.get("ends") or "",
            "area": p.get("areaDesc", ""), "text": " ".join((p.get("description") or "").split())[:600]}


def place(weather) -> Optional[tuple]:
    """(lat, lon) the forecast is for, as the weather kept it."""
    try:
        with open(weather._place_path(), encoding="utf-8") as f:
            p = json.load(f)
        if p.get("zip") == weather.zip:
            return float(p["lat"]), float(p["lon"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


_radar, _alerts = None, None


def radar(app) -> Radar:
    global _radar
    if _radar is None:
        from . import __version__
        _radar = Radar(f"Cathode/{__version__}")
    return _radar


def alerts(app) -> Alerts:
    global _alerts
    if _alerts is None:
        from . import __version__
        _alerts = Alerts(f"Cathode/{__version__} (personal weather channel)")
    return _alerts


def alerts_now(app) -> list:
    """The active alerts where the weather is for (US; [] elsewhere or off)."""
    wx = getattr(app, "weather", None)
    if wx is None or not wx.zip or (getattr(wx, "country", "") or "US") != "US" or not getattr(app.config, "weather_alerts", True):
        return []
    p = place(wx)
    return alerts(app).get(*p) if p else []

"""Current-weather lookup for the guide header.

Uses wttr.in's JSON endpoint: it takes a zip/postal code directly, needs no API
key, and returns conditions, temperature, humidity, a rain chance and the city —
everything the header shows.  Fetched on a background thread and cached (like the
logo store), so the network never blocks rendering.

# ponytail: wttr.in is free/no-auth but rate-limited and best-effort. Swap _fetch
# for a keyed provider (OpenWeather/WeatherAPI) if you need reliability/accuracy.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from typing import Callable, Optional

_REFRESH = 900.0   # seconds between refreshes (15 min)

# Countries offered in the Weather menu (ISO-2 code, display name).  The code is
# appended to the zip ("90210,US") so wttr.in's geocoder pins the lookup to one
# country instead of guessing — a bare zip is ambiguous across borders.
# ponytail: a curated short list (fits the menu without scrolling); extend freely.
COUNTRIES = [
    ("US", "United States"), ("GB", "United Kingdom"), ("CA", "Canada"),
    ("AU", "Australia"), ("IE", "Ireland"), ("NZ", "New Zealand"),
    ("AT", "Austria"), ("BE", "Belgium"), ("BR", "Brazil"), ("DK", "Denmark"),
    ("FI", "Finland"), ("FR", "France"), ("DE", "Germany"), ("IN", "India"),
    ("IT", "Italy"), ("JP", "Japan"), ("MX", "Mexico"), ("NL", "Netherlands"),
    ("NO", "Norway"), ("PL", "Poland"), ("PT", "Portugal"), ("ES", "Spain"),
    ("SE", "Sweden"), ("CH", "Switzerland"),
]
_COUNTRY_NAMES = dict(COUNTRIES)


def country_name(code: str) -> str:
    return _COUNTRY_NAMES.get((code or "").upper(), code or "")

# WWO weather codes → icon category (a few explicit; everything wet defaults to
# "rain").  # ponytail: approximate grouping; extend per the WWO code table.
_FOG = {143, 248, 260}
_STORM = {200, 386, 389, 392, 395}
_SNOW = {179, 182, 185, 227, 230, 281, 284, 311, 314, 317, 320, 323, 326, 329,
         332, 335, 338, 350, 362, 365, 368, 371, 374, 377}


def _category(code) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "cloudy"
    if c == 113:
        return "clear"
    if c == 116:
        return "partly"
    if c in (119, 122):
        return "cloudy"
    if c in _FOG:
        return "fog"
    if c in _STORM:
        return "storm"
    if c in _SNOW:
        return "snow"
    return "rain"


class Weather:
    def __init__(self, zip_code: str, units: str = "F", country: str = "US",
                 on_update: Optional[Callable] = None,
                 user_agent: str = "Cathode/1.0"):
        self.zip = (zip_code or "").strip()
        self.units = "C" if str(units).upper().startswith("C") else "F"
        self.country = (country or "").strip().upper()
        self._on_update = on_update
        self._ua = user_agent
        self._data: Optional[dict] = None
        self._fetched_at = 0.0
        self._inflight = False
        self._lock = threading.Lock()

    def configure(self, zip_code: str, units: Optional[str] = None,
                  country: Optional[str] = None):
        """Point at a new zip/units/country and drop the cache so the next
        current() refetches.  Called by the Weather menu."""
        with self._lock:
            self.zip = (zip_code or "").strip()
            if units is not None:
                self.units = "C" if str(units).upper().startswith("C") else "F"
            if country is not None:
                self.country = (country or "").strip().upper()
            self._data = None
            self._fetched_at = 0.0

    def current(self) -> Optional[dict]:
        """Cached weather summary, kicking off a background refresh when stale.
        Returns None until the first successful fetch (or if no zip is set)."""
        if not self.zip:
            return None
        with self._lock:
            stale = (time.monotonic() - self._fetched_at) > _REFRESH
            if stale and not self._inflight:
                self._inflight = True
                threading.Thread(target=self._refresh, daemon=True).start()
            return self._data

    def _refresh(self):
        try:
            data = self._fetch()
        except Exception:
            data = None
        with self._lock:
            if data is not None:
                self._data = data
            self._fetched_at = time.monotonic()
            self._inflight = False
        if data is not None and self._on_update:
            try:
                self._on_update()
            except Exception:
                pass

    def _fetch(self) -> Optional[dict]:
        loc = f"{self.zip},{self.country}" if self.country else self.zip
        url = f"https://wttr.in/{urllib.parse.quote(loc)}?format=j1"
        req = urllib.request.Request(url, headers={"User-Agent": self._ua})
        j = json.loads(urllib.request.urlopen(req, timeout=12).read())
        cur = (j.get("current_condition") or [{}])[0]
        area = (j.get("nearest_area") or [{}])[0]
        return {
            "temp": cur.get("temp_C" if self.units == "C" else "temp_F", ""),
            "units": self.units,
            "humidity": cur.get("humidity", ""),
            "conditions": (cur.get("weatherDesc") or [{}])[0].get("value", "").strip(),
            "category": _category(cur.get("weatherCode")),
            "rain": self._rain_chance(j),
            "city": (area.get("areaName") or [{}])[0].get("value", "").strip(),
        }

    @staticmethod
    def _rain_chance(j) -> int:
        """Today's hourly chance-of-rain nearest the current hour, as a percent."""
        try:
            hourly = j["weather"][0]["hourly"]
            now_h = time.localtime().tm_hour
            best = min(hourly, key=lambda h: abs(int(h.get("time", "0")) // 100 - now_h))
            return int(best.get("chanceofrain", "0"))
        except Exception:
            return 0

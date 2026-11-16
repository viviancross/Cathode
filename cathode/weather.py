"""Current-weather lookup for the guide header.

Uses wttr.in's JSON endpoint, which takes a zip/postal code directly and needs no
API key. Fetched on a background thread and cached, so the network never blocks
rendering.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import math
from typing import Callable, Optional

from .net import SSL as _SSL

_REFRESH = 900.0   # seconds between refreshes (15 min)

# Countries offered in the Weather menu (ISO-2 code, display name). The code is
# appended to the zip ("90210,US") so the geocoder doesn't guess the wrong
# country for an ambiguous postal code.
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


def _seasonal_mean(lat: float, d) -> float:
    """A day's usual mean temperature (C) at a latitude: warmer toward the
    equator, a wider swing toward the poles, the peak a month after
    midsummer (late July north, late January south)."""
    a = abs(lat)
    peak = 200 if lat >= 0 else 17
    swing = math.cos(2 * math.pi * (d.timetuple().tm_yday - peak) / 365.25)
    return 28 - 0.42 * a + 0.3 * a * swing


def _sun_times(lat: float, lon: float, d, tz_hours: float) -> tuple:
    """Sunrise and sunset ("07:12 AM"), local, by NOAA's approximation."""
    g = 2 * math.pi / 365 * (d.timetuple().tm_yday - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                   - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    x = math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl)) - math.tan(phi) * math.tan(decl)
    ha = math.degrees(math.acos(max(-1.0, min(1.0, x))))

    def fmt(minutes):
        minutes = (minutes + tz_hours * 60) % 1440
        h, m = int(minutes // 60), int(minutes % 60)
        return f"{(h % 12) or 12:02d}:{m:02d} {'AM' if h < 12 else 'PM'}"
    return fmt(720 - 4 * (lon + ha) - eq), fmt(720 - 4 * (lon - ha) - eq)


def _moon(d) -> tuple:
    """The moon's phase and how lit it is (percent) on a day."""
    import datetime as _dt
    age = ((_dt.datetime(d.year, d.month, d.day, 12) - _dt.datetime(2000, 1, 6, 18, 14)).total_seconds() / 86400) % 29.530588853
    names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon", "Waning Gibbous",
             "Last Quarter", "Waning Crescent"]
    return names[int((age / 29.530588853) * 8 + 0.5) % 8], round((1 - math.cos(2 * math.pi * age / 29.530588853)) / 2 * 100)


def country_name(code: str) -> str:
    return _COUNTRY_NAMES.get((code or "").upper(), code or "")

# WWO weather codes -> icon category; anything wet not listed defaults to "rain".
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
            if data is None and self._data is None:
                data = self.almanac()           # no forecast to be had: the season's, worked out here
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
        j = json.loads(urllib.request.urlopen(req, timeout=12, context=_SSL).read())
        self._keep_place(j)
        return self.parse(j, self.units)

    # ── The almanac ───────────────────────────────────────────────────────

    def _place_path(self) -> str:
        from . import paths
        import os
        return os.path.join(paths.cache_dir(), "weather-place.json")

    def _keep_place(self, j: dict):
        """Where the forecast was for, kept for the almanac."""
        try:
            area = (j.get("nearest_area") or [{}])[0]
            place = {"zip": self.zip, "lat": float(area["latitude"]), "lon": float(area["longitude"]),
                     "city": (area.get("areaName") or [{}])[0].get("value", "").strip()}
            with open(self._place_path(), "w", encoding="utf-8") as f:
                json.dump(place, f)
        except (KeyError, TypeError, ValueError, OSError):
            pass

    def almanac(self, today=None) -> dict:
        """The weather as the almanac has it: each day's sunrise and sunset
        and the moon's phase worked out for the place, the temperatures the
        season's usual ones for its latitude. Marked as such."""
        import datetime as _dt
        try:
            with open(self._place_path(), encoding="utf-8") as f:
                place = json.load(f)
            if place.get("zip") != self.zip:
                place = None
        except (OSError, ValueError):
            place = None
        off = (time.localtime().tm_gmtoff or 0) / 3600
        lat = float(place["lat"]) if place else 40.0
        lon = float(place["lon"]) if place else off * 15
        today = today or _dt.date.today()
        hour = time.localtime().tm_hour
        days = []
        for k in range(3):
            d = today + _dt.timedelta(days=k)
            mean = _seasonal_mean(lat, d)
            rise, sset = _sun_times(lat, lon, d, off)
            phase, lit = _moon(d)
            hours = [{"hour": h, "temp": self._t(mean + 5 * math.cos(2 * math.pi * (h - 15) / 24)),
                      "desc": "Seasonal average", "category": "partly", "rain": 0} for h in range(0, 24, 3)]
            days.append({"date": d.isoformat(), "hi": self._t(mean + 5), "lo": self._t(mean - 5),
                         "desc": "Seasonal average", "category": "partly", "sunrise": rise, "sunset": sset,
                         "moon": phase, "moon_lit": str(lit), "hours": hours})
        now = _seasonal_mean(lat, today) + 5 * math.cos(2 * math.pi * (hour - 15) / 24)
        return {"temp": self._t(now), "units": self.units, "humidity": "", "conditions": "Seasonal average",
                "category": "partly", "rain": 0, "city": (place or {}).get("city") or self.zip, "feels": self._t(now),
                "wind": "", "wind_dir": "", "pressure": "", "visibility": "", "uv": "", "days": days, "almanac": True}

    def _t(self, celsius: float) -> str:
        return str(round(celsius * 9 / 5 + 32 if self.units == "F" else celsius))

    @classmethod
    def parse(cls, j: dict, units: str) -> dict:
        """wttr.in's j1 answer as the summary the header shows plus, for the
        Weather channel, the rest of the conditions and three days of
        three-hourly outlook with each day's sun and moon."""
        imperial = units != "C"
        cur = (j.get("current_condition") or [{}])[0]
        area = (j.get("nearest_area") or [{}])[0]
        desc = lambda h: (h.get("weatherDesc") or [{}])[0].get("value", "").strip()   # noqa: E731
        days = []
        for d in (j.get("weather") or [])[:3]:
            astro = (d.get("astronomy") or [{}])[0]
            hours = [{"hour": int(h.get("time") or 0) // 100,
                      "temp": h.get("tempF" if imperial else "tempC", ""),
                      "desc": desc(h), "category": _category(h.get("weatherCode")),
                      "rain": int(h.get("chanceofrain") or 0)} for h in d.get("hourly") or []]
            noon = hours[min(4, len(hours) - 1)] if hours else {}
            days.append({"date": d.get("date", ""),
                         "hi": d.get("maxtempF" if imperial else "maxtempC", ""),
                         "lo": d.get("mintempF" if imperial else "mintempC", ""),
                         "desc": noon.get("desc", ""), "category": noon.get("category", "cloudy"),
                         "sunrise": astro.get("sunrise", ""), "sunset": astro.get("sunset", ""),
                         "moon": astro.get("moon_phase", ""), "moon_lit": astro.get("moon_illumination", ""),
                         "hours": hours})
        return {
            "temp": cur.get("temp_F" if imperial else "temp_C", ""),
            "units": "F" if imperial else "C",
            "humidity": cur.get("humidity", ""),
            "conditions": desc(cur),
            "category": _category(cur.get("weatherCode")),
            "rain": cls._rain_chance(j),
            "city": (area.get("areaName") or [{}])[0].get("value", "").strip(),
            "feels": cur.get("FeelsLikeF" if imperial else "FeelsLikeC", ""),
            "wind": cur.get("windspeedMiles" if imperial else "windspeedKmph", ""),
            "wind_dir": cur.get("winddir16Point", ""),
            "pressure": (cur.get("pressureInches", "") + " in") if imperial else (cur.get("pressure", "") + " mb"),
            "visibility": cur.get("visibilityMiles" if imperial else "visibility", ""),
            "uv": cur.get("uvIndex", ""),
            "days": days,
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

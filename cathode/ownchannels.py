"""Cathode's own channels: a TV Guide channel and a Weather channel that sit
in the lineup and the guide like any other, and draw their picture instead
of playing a stream.

A page draws itself at SD size (640 wide, the skin's shape); the kernel
uploads the frame where mpv's picture would go, so it fills the screen, sits
in the guide's picture box, takes the channel-change static and the CRT
pass like a broadcast would."""

import time
from datetime import datetime, timedelta, timezone

import pygame

from .epg import Program
from .playlist import Channel

SCHEME = "cathode://"
# kind -> (channel name, listing title, listing description)
KINDS = {
    "tvguide": ("TV Guide", "TV Guide",
                "What's on now and next on every channel, with a look at what's showing."),
    "weather": ("Local Weather", "Local Weather",
                "Current conditions, the hourly outlook, the extended forecast and the almanac, on the 8s."),
}


def is_own(ch) -> bool:
    return ch.url.startswith(SCHEME)


def kind_of(ch) -> str:
    return ch.url[len(SCHEME):]


def real_ids(epg) -> list:
    """The guide's channel ids that came from the guide, not from here."""
    return [cid for cid in epg.channel_ids if not cid.startswith("cathode.")]


def add_to(chans: list, config) -> list:
    """The lineup with the own channels placed in it: at the number the
    settings say, or ("auto") after the lineup's last whole number, in
    numeric position. "off" leaves one out. An empty lineup stays empty: with
    no channels there is nothing for the guide channel to show."""
    out = [c for c in chans if not is_own(c)]
    if not out:
        return out
    taken = {c.number for c in out}
    nxt = int(max(c.number for c in out)) + 1
    for kind, (name, _t, _d) in KINDS.items():
        want = (getattr(config, "own_channels", None) or {}).get(kind, "auto")
        if want == "off":
            continue
        try:
            num = nxt if want == "auto" else int(want)
        except (TypeError, ValueError):
            num = nxt
        while num in taken:         # a number the lineup has: the next free one
            num += 1
        taken.add(num)
        nxt = max(nxt, num + 1)
        ch = Channel(number=num, name=name, url=SCHEME + kind, epg_id=f"cathode.{kind}")
        at = next((i for i, c in enumerate(out) if c.number > num), len(out))
        out.insert(at, ch)
    return out


def fill_guide(epg, now=None, hours: int = 48):
    """The own channels' listings: half-hour blocks from an hour ago, far
    enough ahead to outlast the guide's reload. Replaces what was there."""
    now = now or datetime.now(timezone.utc)
    t = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0) - timedelta(hours=1)
    slot = timedelta(minutes=30)
    for kind, (_n, title, desc) in KINDS.items():
        cid = f"cathode.{kind}"
        epg.set_programs(cid, [Program(channel_id=cid, title=title, description=desc,
                                       start=t + i * slot, stop=t + (i + 1) * slot)
                               for i in range(hours * 2)])


def make_page(ch, app):
    return {"tvguide": TVGuidePage, "weather": WeatherPage}[kind_of(ch)](app)


# ── Pages ─────────────────────────────────────────────────────────────────

class Page:
    """A picture drawn at SD size, `fps` times a second while it's tuned."""
    fps = 1

    def __init__(self, app):
        self.app = app
        skin = getattr(app, "skin", None)
        text = getattr(skin, "text", None)
        if text is None:
            from .skins import Text
            text = Text()
        self.text = text
        cw, ch = getattr(type(skin), "canvas", (1280, 720)) if skin else (1280, 720)
        self.size = (640, round(640 * ch / cw))
        self.t0 = time.monotonic()

    def font(self, file: str, px: int):
        return self.text.font(file, px)

    def frame(self) -> pygame.Surface:
        s = pygame.Surface(self.size)
        self.draw(s, datetime.now())
        return s

    def draw(self, s, now):
        raise NotImplementedError


_PREVUE = "PxPlus_IBM_VGA8.ttf"
_BLUE, _BLUE_DARK, _LINE = (12, 12, 136), (0, 0, 92), (96, 112, 224)
_YELLOW, _WHITE, _GREY = (255, 232, 72), (255, 255, 255), (196, 204, 232)


def _num(ch) -> str:
    return f"{ch.number:g}"


class TVGuidePage(Page):
    """Prevue-style: a promo for something showing now in the top half, the
    grid of every channel's next ninety minutes scrolling up through the
    bottom half, in the blue-and-yellow look."""
    fps = 30
    SLOT = timedelta(minutes=30)
    SCROLL = 24.0           # pixels a second
    PROMO = 8.0             # seconds each promo stays
    ROW, CH_W, HDR = 36, 92, 22

    def __init__(self, app):
        super().__init__(app)
        self._promos = (None, [])

    def draw(self, s, now):
        W, H = self.size
        s.fill(_BLUE)
        top = H // 2
        self._promo(s, now, pygame.Rect(0, 0, W, top))
        self._grid(s, now, pygame.Rect(0, top, W, H - top))

    # The promo panel: what's on now, one channel at a time, with its poster
    # where the guide carries one.
    def _candidates(self, now):
        epg, utc = self.app.epg, now.astimezone(timezone.utc)
        key = (now.minute // 5, id(epg), len(epg.channel_ids) if epg else 0)    # a guide that loads is seen
        if self._promos[0] != key:
            found = []
            for ch in self.app.channels:
                if is_own(ch) or epg is None:
                    continue
                cid = epg.resolve_channel_id(ch.epg_id, ch.name)
                cur = epg.current_program(cid, utc) if cid else None
                if cur:
                    found.append((ch, cur))
            told = [cp for cp in found if cp[1].description or cp[1].icon]
            self._promos = (key, told or found)
        return self._promos[1]

    def _promo(self, s, now, r):
        t, f, fw = self.text, self.font(_PREVUE, 16), self.font(_PREVUE, 28)
        t.draw(s, "TV GUIDE", fw, _YELLOW, 16, 10)
        t.draw(s, now.strftime("%I:%M %p").lstrip("0"), f, _YELLOW, r.right - 16, 14, align="right")
        pygame.draw.line(s, _YELLOW, (16, 44), (r.right - 16, 44))
        cands = self._candidates(now)
        x, y = 16, 56
        if not cands:
            t.draw(s, "No listings yet.", f, _WHITE, x, y)
            return
        ch, prog = cands[int(time.time() // self.PROMO) % len(cands)]
        logo = getattr(self.app.skin, "logo", None)
        art = logo(prog.icon, 72, r.h - y - 12) if prog.icon and logo else None
        if art:
            s.blit(art, (x, y))
            x += art.get_width() + 12
        w = r.w - x - 16
        t.draw(s, t.fit(f, f"NOW ON {_num(ch)}  {ch.name.upper()}", w), f, _YELLOW, x, y)
        t.draw(s, t.fit(f, prog.title.upper(), w), f, _WHITE, x, y + 22)
        for i, line in enumerate(t.wrap(f, prog.description, w, (r.h - y - 50) // 18)):
            t.draw(s, line, f, _GREY, x, y + 48 + i * 18)

    # The grid, scrolling.
    def _grid(self, s, now, r):
        t, f = self.text, self.font(_PREVUE, 16)
        rh, cw, hdr = self.ROW, self.CH_W, self.HDR
        t0 = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
        cols, colw = 3, (r.w - cw) / 3
        pygame.draw.rect(s, _BLUE_DARK, (r.x, r.y, r.w, hdr))
        for i in range(cols):
            x = int(r.x + cw + i * colw)
            t.draw(s, (t0 + i * self.SLOT).strftime("%I:%M %p").lstrip("0"), f, _YELLOW, x + 8, r.y + 3)
            pygame.draw.line(s, _LINE, (x, r.y), (x, r.bottom))
        chans = self.app.channels
        n = len(chans)
        if not n:
            return
        view = pygame.Rect(r.x, r.y + hdr, r.w, r.bottom - r.y - hdr)
        s.set_clip(view)
        period = n + 2                  # two blank rows between one pass and the next
        off = ((time.monotonic() - self.t0) * self.SCROLL) % (period * rh)
        k0 = int(off // rh)
        y = view.y - (off - k0 * rh)
        u0 = t0.astimezone(timezone.utc)
        u1 = u0 + cols * self.SLOT
        for k in range(k0, k0 + view.h // rh + 2):
            slot = k % period
            if slot < n:
                self._row(s, chans[slot], u0, u1, pygame.Rect(r.x, int(y), r.w, rh), f)
            y += rh
        s.set_clip(None)

    def _row(self, s, ch, u0, u1, r, f):
        t, cw = self.text, self.CH_W
        pygame.draw.line(s, _LINE, (r.x, r.bottom - 1), (r.right, r.bottom - 1))
        t.draw(s, _num(ch), f, _YELLOW, r.x + cw - 8, r.y + 3, align="right")
        t.draw(s, t.fit(f, ch.name.upper(), cw - 12), f, _YELLOW, r.x + 6, r.y + 19)
        pygame.draw.line(s, _LINE, (r.x + cw, r.y), (r.x + cw, r.bottom))
        epg = self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
        if not cid:
            return
        span, gw = (u1 - u0).total_seconds(), r.w - cw
        for p in epg.programs_in_window(cid, u0, u1):
            a, b = max(p.start, u0), min(p.stop, u1)
            x0 = r.x + cw + (a - u0).total_seconds() / span * gw
            x1 = r.x + cw + (b - u0).total_seconds() / span * gw
            pygame.draw.line(s, _LINE, (int(x1), r.y), (int(x1), r.bottom))
            w = int(x1 - x0) - 10
            if w < 16:
                continue
            for i, line in enumerate(t.wrap(f, p.title, w, 2)):
                t.draw(s, line, f, _WHITE, int(x0) + 5, r.y + 3 + i * 16)


_STAR = "Barlow-Bold.ttf"
_SKY_TOP, _SKY_BOTTOM = (20, 24, 120), (76, 32, 150)
_PANEL, _PANEL_EDGE, _BAND = (8, 8, 96), (120, 120, 230), (10, 10, 60)
_SUN, _MOON, _CLOUD, _CLOUD_DIM, _RAIN = (255, 210, 60), (228, 228, 214), (236, 240, 250), (190, 196, 214), (120, 190, 255)


def draw_weather_icon(s, x, y, size, cat, night=False):
    """The condition as a simple icon in a size x size box."""
    def disc(cx, cy, r):
        pygame.draw.circle(s, _MOON if night else _SUN, (int(cx), int(cy)), int(r))

    def cloud(bx, by, bw, bh, col):
        r = bh / 2
        pygame.draw.circle(s, col, (int(bx + r), int(by + bh - r)), int(r))
        pygame.draw.circle(s, col, (int(bx + bw - r), int(by + bh - r)), int(r))
        pygame.draw.ellipse(s, col, (bx + bw * 0.28, by, bw * 0.44, bh * 0.95))
        pygame.draw.rect(s, col, (bx + r, by + bh - r, bw - 2 * r, r))
    if cat == "clear":
        disc(x + size / 2, y + size / 2, size * 0.28)
        return
    if cat == "partly":
        disc(x + size * 0.32, y + size * 0.34, size * 0.2)
        cloud(x + size * 0.28, y + size * 0.42, size * 0.66, size * 0.4, _CLOUD)
        return
    cloud(x + size * 0.08, y + size * 0.18, size * 0.84, size * 0.5, _CLOUD_DIM if cat == "fog" else _CLOUD)
    base = y + size * 0.72
    for i in range(3):
        dx = x + size * (0.3 + i * 0.2)
        if cat == "rain":
            pygame.draw.line(s, _RAIN, (dx, base), (dx - size * 0.08, base + size * 0.2), max(2, size // 24))
        elif cat == "snow":
            pygame.draw.circle(s, _CLOUD, (int(dx), int(base + size * 0.12)), max(2, size // 20))
    if cat == "storm":
        pygame.draw.polygon(s, _SUN, [(x + size * 0.5, base - size * 0.05), (x + size * 0.38, base + size * 0.14),
                                      (x + size * 0.5, base + size * 0.14), (x + size * 0.42, base + size * 0.3),
                                      (x + size * 0.62, base + size * 0.08), (x + size * 0.5, base + size * 0.08)])


class WeatherPage(Page):
    """Local on the 8s: the current conditions, the hourly outlook, the
    extended forecast and the almanac, each held for eight seconds under a
    running clock, with the conditions crawling along the foot."""
    fps = 20
    HOLD = 8.0
    CRAWL = 70.0            # pixels a second

    def __init__(self, app):
        super().__init__(app)
        self._bg = None

    def draw(self, s, now):
        W, H = self.size
        t = self.text
        f, f_small = self.font(_STAR, 20), self.font(_STAR, 16)
        if self._bg is None:
            col = pygame.Surface((1, H))
            for y in range(H):
                k = y / max(1, H - 1)
                col.set_at((0, y), tuple(int(a + (b - a) * k) for a, b in zip(_SKY_TOP, _SKY_BOTTOM)))
            self._bg = pygame.transform.scale(col, (W, H))
        s.blit(self._bg, (0, 0))
        t.draw(s, now.strftime("%I:%M:%S %p").lstrip("0"), f, _WHITE, W - 20, 12, align="right")
        t.draw(s, now.strftime("%a %b %d").upper(), f_small, _WHITE, W - 20, 36, align="right")
        body = pygame.Rect(16, 62, W - 32, H - 62 - 48)
        pygame.draw.rect(s, _PANEL, body)
        pygame.draw.rect(s, _PANEL_EDGE, body, 2)
        wx = getattr(self.app, "weather", None)
        data = wx.current() if wx and wx.zip else None
        if not wx or not wx.zip:
            hint = getattr(self.app, "press_hint", None)
            self._title(s, "Local Weather")
            self._message(s, body, ["No zip code set.", f"Press {hint('MENU') if hint else 'MENU'}, then "
                                    "Settings > System > Weather, to add yours."])
        elif data is None:
            self._title(s, "Local Weather")
            self._message(s, body, ["Getting the local weather..."])
        else:
            pages = [self._current, self._hourly, self._extended, self._almanac]
            pages[int((time.monotonic() - self.t0) // self.HOLD) % len(pages)](s, body, data, now)
        self._crawl(s, data, now)

    def _title(self, s, title, sub=""):
        t = self.text
        t.draw(s, title, self.font(_STAR, 30), _YELLOW, 20, 8, outline=(0, 0, 40))
        if sub:
            t.draw(s, sub, self.font(_STAR, 16), _WHITE, 22, 42)

    def _message(self, s, body, lines):
        t, f = self.text, self.font(_STAR, 20)
        y = body.y + 24
        for line in lines:
            for ln in t.wrap(f, line, body.w - 48, 3):
                t.draw(s, ln, f, _WHITE, body.x + 24, y)
                y += 28

    def _current(self, s, body, d, now):
        t, f, f_big = self.text, self.font(_STAR, 20), self.font(_STAR, 56)
        self._title(s, "Current Conditions", d.get("city", ""))
        night = not 6 <= now.hour < 19
        x, y = body.x + 24, body.y + 20
        draw_weather_icon(s, x, y + 6, 84, d.get("category", "cloudy"), night)
        t.draw(s, f"{d.get('temp', '')}°", f_big, _WHITE, x + 104, y - 4)
        for i, line in enumerate(t.wrap(f, d.get("conditions", ""), 250, 2)):
            t.draw(s, line, f, _WHITE, x, y + 104 + i * 26)
        imperial = d.get("units", "F") == "F"
        rows = [("Humidity", f"{d.get('humidity', '')}%"), ("Feels Like", f"{d.get('feels', '')}°"),
                ("Wind", f"{d.get('wind_dir', '')} {d.get('wind', '')} {'mph' if imperial else 'km/h'}".strip()),
                ("Pressure", d.get("pressure", "")), ("Visibility", f"{d.get('visibility', '')} {'mi' if imperial else 'km'}"),
                ("UV Index", str(d.get("uv", "")))]
        rx = body.x + body.w // 2 + 20
        for i, (k, v) in enumerate(rows):
            t.draw(s, k, f, _YELLOW, rx, y + i * 32)
            t.draw(s, v, f, _WHITE, body.right - 24, y + i * 32, align="right")

    def _hours(self, d, now):
        """(local datetime, hour dict) from now on, across the days given."""
        out = []
        for day in d.get("days", []):
            try:
                date = datetime.strptime(day.get("date", ""), "%Y-%m-%d")
            except ValueError:
                continue
            for h in day.get("hours", []):
                when = date + timedelta(hours=h.get("hour", 0))
                if when >= now - timedelta(hours=2):
                    out.append((when, h))
        return out

    def _hourly(self, s, body, d, now):
        t, f = self.text, self.font(_STAR, 20)
        self._title(s, "Local Forecast", d.get("city", ""))
        y = body.y + 16
        rows = self._hours(d, now)[:(body.h - 24) // 30]
        if not rows:
            self._message(s, body, ["No hourly outlook yet."])
            return
        for when, h in rows:
            t.draw(s, when.strftime("%I %p").lstrip("0"), f, _YELLOW, body.x + 24, y)
            draw_weather_icon(s, body.x + 96, y - 2, 26, h.get("category", "cloudy"), not 6 <= when.hour < 19)
            t.draw(s, t.fit(f, h.get("desc", ""), 230), f, _WHITE, body.x + 132, y)
            t.draw(s, f"{h.get('temp', '')}°", f, _WHITE, body.right - 150, y, align="right")
            t.draw(s, f"Rain {h.get('rain', 0)}%", f, _WHITE, body.right - 24, y, align="right")
            y += 30

    def _extended(self, s, body, d, now):
        t, f, f_small = self.text, self.font(_STAR, 20), self.font(_STAR, 16)
        self._title(s, "Extended Forecast", d.get("city", ""))
        days = d.get("days", [])[:3]
        if not days:
            self._message(s, body, ["No outlook yet."])
            return
        colw = body.w // len(days)
        for i, day in enumerate(days):
            cx = body.x + i * colw + colw // 2
            try:
                label = "TODAY" if i == 0 else datetime.strptime(day["date"], "%Y-%m-%d").strftime("%A").upper()
            except (KeyError, ValueError):
                label = ""
            t.draw(s, label, f, _YELLOW, cx, body.y + 14, align="center")
            draw_weather_icon(s, cx - 32, body.y + 44, 64, day.get("category", "cloudy"))
            t.draw(s, f"{day.get('hi', '')}° / {day.get('lo', '')}°", f, _WHITE, cx, body.y + 116, align="center")
            for k, line in enumerate(t.wrap(f_small, day.get("desc", ""), colw - 16, 2)):
                t.draw(s, line, f_small, _WHITE, cx, body.y + 146 + k * 20, align="center")
            if i:
                pygame.draw.line(s, _PANEL_EDGE, (body.x + i * colw, body.y + 10), (body.x + i * colw, body.bottom - 10))

    def _almanac(self, s, body, d, now):
        t, f = self.text, self.font(_STAR, 20)
        self._title(s, "Almanac", d.get("city", ""))
        days = d.get("days", [])[:2]
        if not days:
            self._message(s, body, ["No almanac yet."])
            return
        colw = body.w // 2
        for i, day in enumerate(days):
            x = body.x + 24 + i * colw
            try:
                label = "TODAY" if i == 0 else datetime.strptime(day["date"], "%Y-%m-%d").strftime("%A").upper()
            except (KeyError, ValueError):
                label = ""
            t.draw(s, label, f, _YELLOW, x, body.y + 16)
            t.draw(s, f"Sunrise  {day.get('sunrise', '')}", f, _WHITE, x, body.y + 50)
            t.draw(s, f"Sunset   {day.get('sunset', '')}", f, _WHITE, x, body.y + 80)
        moon = days[0].get("moon", "")
        if moon:
            lit = days[0].get("moon_lit", "")
            t.draw(s, f"Moon: {moon}" + (f" ({lit}% lit)" if lit else ""), f, _WHITE, body.x + 24, body.y + 130)

    def _crawl(self, s, d, now):
        W, H = self.size
        t, f = self.text, self.font(_STAR, 20)
        band = pygame.Rect(0, H - 44, W, 44)
        pygame.draw.rect(s, _BAND, band)
        if not d:
            text = "Local weather on Cathode's own channel."
        else:
            text = (f"Local weather for {d.get('city', 'your area')}:  {d.get('temp', '')}° and "
                    f"{(d.get('conditions') or '').lower()}.  Humidity {d.get('humidity', '')}%.  "
                    f"Wind {d.get('wind_dir', '')} {d.get('wind', '')} {'mph' if d.get('units', 'F') == 'F' else 'km/h'}.")
        tw = t.width(f, text)
        x = W - ((time.monotonic() - self.t0) * self.CRAWL % (tw + W))
        t.draw(s, text, f, _WHITE, int(x), band.y + 11)

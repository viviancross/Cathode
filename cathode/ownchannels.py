"""Cathode's own channels: a TV Guide channel and a Weather channel that sit
in the lineup and the guide like any other, and draw their picture instead
of playing a stream.

A page draws itself at SD size (640 wide, the skin's shape); the kernel
uploads the frame where mpv's picture would go, so it fills the screen, sits
in the guide's picture box, takes the channel-change static and the CRT
pass like a broadcast would."""

import os
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
    """One of these page channels (a music channel is cathode:// too, but not one)."""
    return ch.url.startswith(SCHEME) and kind_of(ch) in KINDS


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


_GUIDE = "Barlow-Bold.ttf"
_NAVY = (14, 10, 72)                                # the dark between the cells
_CELL, _CELL_TOP, _CELL_HI, _CELL_LO = (44, 38, 138), (58, 52, 158), (116, 108, 210), (16, 12, 76)
_TOP0, _TOP1 = (26, 22, 124), (78, 36, 154)         # the promo half's gradient
_YELLOW, _WHITE, _GREY, _SHADOW = (255, 232, 72), (255, 255, 255), (196, 204, 232), (4, 2, 40)
_SQUEEZE = 0.84                                     # Barlow drawn this much narrower: the condensed face


def _num(ch) -> str:
    return f"{ch.number:g}"


def _gradient(size, top, bottom):
    w, h = size
    col = pygame.Surface((1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        col.set_at((0, y), tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)))
    return pygame.transform.scale(col, (w, h))


def _bevel(s, r, col=_CELL, raised=True):
    """A cell: rounded, lighter across its top, a light edge top-left and a
    dark one bottom-right (the other way round for a sunken box)."""
    pygame.draw.rect(s, col, r, border_radius=3)
    if raised:
        pygame.draw.rect(s, _CELL_TOP, (r.x, r.y, r.w, r.h // 2), border_top_left_radius=3, border_top_right_radius=3)
    hi, lo = (_CELL_HI, _CELL_LO) if raised else (_CELL_LO, _CELL_HI)
    pygame.draw.line(s, hi, (r.x + 2, r.y), (r.right - 3, r.y))
    pygame.draw.line(s, hi, (r.x, r.y + 2), (r.x, r.bottom - 3))
    pygame.draw.line(s, lo, (r.x + 2, r.bottom - 1), (r.right - 3, r.bottom - 1))
    pygame.draw.line(s, lo, (r.right - 1, r.y + 2), (r.right - 1, r.bottom - 3))


def _chevrons(s, x, cy, h, right=True):
    """The double arrow on a programme that runs past the window's edge."""
    w = h * 0.55
    for d in (0, 1):
        x0 = x + d * (w + 2)
        pts = ([(x0, cy - h / 2), (x0 + w, cy), (x0, cy + h / 2)] if right
               else [(x0 + w, cy - h / 2), (x0, cy), (x0 + w, cy + h / 2)])
        pygame.draw.polygon(s, _SHADOW, [(px + 1, py + 1) for px, py in pts])
        pygame.draw.polygon(s, _WHITE, pts)


class _Cond:
    """Bold condensed type with a drop shadow: Barlow Bold squeezed, drawn
    twice. Widths are measured through the squeeze."""

    def __init__(self, text, font, k=_SQUEEZE):
        self.text, self.font, self.k = text, font, k
        self.h = font.get_height()

    def width(self, s):
        return int(self.text.width(self.font, s) * self.k)

    def fit(self, s, w):
        return self.text.fit(self.font, s, int(w / self.k))

    def wrap(self, s, w, lines):
        return self.text.wrap(self.font, s, int(w / self.k), lines)

    def render(self, s, color):
        img, _ = self.text.render(self.font, s, color)
        return pygame.transform.smoothscale(img, (max(1, int(img.get_width() * self.k)), img.get_height()))

    def draw(self, surf, s, color, x, y, align="left", shadow=2):
        if not s:
            return
        img = self.render(s, color)
        if align == "center":
            x -= img.get_width() // 2
        elif align == "right":
            x -= img.get_width()
        if shadow:
            surf.blit(self.render(s, _SHADOW), (x + shadow, y + shadow))
        surf.blit(img, (x, y))


def _when(start, now):
    """'Tonight 8:00 PM', 'Tomorrow 9:30 AM', 'Tuesday 8:00 PM'."""
    t = start.astimezone()
    clock = t.strftime("%I:%M %p").lstrip("0")
    day = "Tonight" if t.date() == now.date() and t.hour >= 17 else "Today" if t.date() == now.date() \
        else "Tomorrow" if (t.date() - now.date()).days == 1 else t.strftime("%A")
    return f"{day} {clock}"


class TVGuidePage(Page):
    """The TV Guide Channel at the end of the nineties: the picture and a
    promo panel over the top half, the grid of every channel's next ninety
    minutes rolling up through the bottom half in bevelled navy cells, the
    clock in the corner cell, bold condensed type with a shadow."""
    fps = 30
    SLOT = timedelta(minutes=30)
    SCROLL = 22.0           # pixels a second
    PROMO = 8.0             # seconds each promo stays

    def __init__(self, app):
        super().__init__(app)
        self._promos = (None, [])
        self._rows = (None, {})         # (window start, {channel index: its row drawn})
        self._bg = None
        k = self.k = self.size[1] / 360
        self.ROW, self.CH_W, self.HDR, self.GAP = round(44 * k), round(96 * k), round(26 * k), round(2 * k)
        self.f = _Cond(self.text, self.font(_GUIDE, round(17 * k)))
        self.f_big = _Cond(self.text, self.font(_GUIDE, round(24 * k)))
        self.f_small = _Cond(self.text, self.font(_GUIDE, round(12 * k)))

    def draw(self, s, now):
        W, H = self.size
        top = round(H * 0.52)
        if self._bg is None:
            self._bg = _gradient((W, top), _TOP0, _TOP1)
        s.blit(self._bg, (0, 0))
        pygame.draw.rect(s, _NAVY, (0, top, W, H - top))
        self._promo(s, now, pygame.Rect(0, 0, W, top))
        self._grid(s, now, pygame.Rect(0, top, W, H - top))

    # The promo panel: what's on now, one channel at a time, its poster
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
        k, f = self.k, self.f
        m = round(14 * k)
        box = pygame.Rect(m, m, round(r.w * 0.46), r.h - 2 * m)
        _bevel(s, box, (6, 4, 40), raised=False)
        panel = pygame.Rect(box.right + m, box.y, r.right - m - box.right - m, box.h)
        self._logo(s, r.right - m, box.bottom)
        cands = self._candidates(now)
        if not cands:
            f.draw(s, "No listings yet", _WHITE, panel.centerx, panel.y + round(6 * k), align="center")
            return
        ch, prog = cands[int(time.time() // self.PROMO) % len(cands)]
        logo = getattr(self.app.skin, "logo", None)
        art = logo(prog.icon, box.w - 8, box.h - 8) if prog.icon and logo else None
        if art:
            s.blit(art, (box.centerx - art.get_width() // 2, box.centery - art.get_height() // 2))
        else:
            self.f_big.draw(s, self.f_big.fit(ch.name.upper(), box.w - 24), _WHITE,
                            box.centerx, box.centery - round(14 * k), align="center")
        utc = now.astimezone(timezone.utc)
        on_now = prog.start <= utc < prog.stop
        local = lambda d: d.astimezone().strftime("%I:%M").lstrip("0")
        span = (f"{local(prog.start)} - {local(prog.stop)} " + prog.stop.astimezone().strftime("%p")) if on_now \
            else _when(prog.start, now)
        lines = [prog.category or ("Now Showing" if on_now else "Coming Up"),
                 None, span, f"Channel {_num(ch)}"]
        y, lh = panel.y + round(4 * k), round(30 * k)
        for i, line in enumerate(lines):
            if line is None:                        # the title in quotes, its rating in a badge
                title = f'"{prog.title}"'
                badge = (prog.rating or "").strip().upper()
                bw = self.f_small.width(badge) + round(10 * k) if badge else 0
                title = f.fit(title, panel.w - bw - round(8 * k))
                tw = f.width(title)
                x = panel.centerx - (tw + bw) // 2
                f.draw(s, title, _WHITE, x, y + i * lh)
                if badge:
                    br = pygame.Rect(x + tw + round(6 * k), y + i * lh + round(4 * k), bw, self.f_small.h + round(2 * k))
                    pygame.draw.rect(s, _YELLOW, br, border_radius=2)
                    self.f_small.draw(s, badge, _NAVY, br.centerx, br.y + round(1 * k), align="center", shadow=0)
            else:
                f.draw(s, f.fit(line, panel.w), _WHITE, panel.centerx, y + i * lh, align="center")

    def _logo(self, s, right, bottom):
        """The channel's mark, in the panel's corner."""
        k = self.k
        r = pygame.Rect(0, 0, round(58 * k), round(40 * k))
        r.bottomright = (right, bottom)
        pygame.draw.rect(s, _SHADOW, r.move(2, 2), border_radius=4)
        pygame.draw.rect(s, _WHITE, r, border_radius=4)
        pygame.draw.rect(s, _NAVY, r, width=max(1, round(k)), border_radius=4)
        self.f_big.draw(s, "TV", _NAVY, r.centerx, r.y + round(1 * k), align="center", shadow=0)
        self.f_small.draw(s, "GUIDE", _NAVY, r.centerx, r.bottom - self.f_small.h - round(1 * k), align="center", shadow=0)

    # The grid, rolling up.
    def _grid(self, s, now, r):
        f, rh, cw, hdr, g = self.f, self.ROW, self.CH_W, self.HDR, self.GAP
        t0 = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
        cols, colw = 3, (r.w - cw) / 3
        ty = r.y + g + round(2 * self.k)
        _bevel(s, pygame.Rect(r.x + g, r.y + g, cw - 2 * g, hdr - 2 * g))
        f.draw(s, now.strftime("%I:%M:%S").lstrip("0"), _YELLOW, r.x + cw // 2, ty, align="center")
        for i in range(cols):
            x = int(r.x + cw + i * colw)
            _bevel(s, pygame.Rect(x + g, r.y + g, int(colw) - 2 * g, hdr - 2 * g))
            f.draw(s, (t0 + i * self.SLOT).strftime("%I:%M %p").lstrip("0"), _YELLOW, x + int(colw) // 2, ty, align="center")
        chans = self.app.channels
        n = len(chans)
        if not n:
            return
        u0 = t0.astimezone(timezone.utc)
        u1 = u0 + cols * self.SLOT
        epg = self.app.epg
        key = (u0, id(epg), len(epg.channel_ids) if epg else 0)       # a guide that loads redraws the rows
        if self._rows[0] != key:
            self._rows = (key, {})
        view = pygame.Rect(r.x, r.y + hdr, r.w, r.bottom - r.y - hdr)
        s.set_clip(view)
        period = n + 2                  # two blank rows between one pass and the next
        off = ((time.monotonic() - self.t0) * self.SCROLL) % (period * rh)
        k0 = int(off // rh)
        y = view.y - (off - k0 * rh)
        for k in range(k0, k0 + view.h // rh + 2):
            slot = k % period
            if slot < n:
                s.blit(self._row(slot, chans[slot], u0, u1), (r.x, int(y)))
            y += rh
        s.set_clip(None)

    def _row(self, idx, ch, u0, u1):
        """The channel's row, drawn once a window."""
        rows = self._rows[1]
        surf = rows.get(idx)
        if surf is None:
            surf = rows[idx] = self._draw_row(ch, u0, u1)
        return surf

    def _draw_row(self, ch, u0, u1):
        W = self.size[0]
        f, k, rh, cw, g = self.f, self.k, self.ROW, self.CH_W, self.GAP
        surf = pygame.Surface((W, rh))
        surf.fill(_NAVY)
        ty, lh, pad = g + round(2 * k), round(18 * k), round(6 * k)
        _bevel(surf, pygame.Rect(g, g, cw - 2 * g, rh - 2 * g))
        f.draw(surf, _num(ch), _YELLOW, cw // 2, ty, align="center")
        name, fn = ch.name.upper(), f
        if f.width(name) > cw - 2 * pad:                # a long call sign, smaller before it's cut
            fn = self.f_small
            name = fn.fit(name, cw - 2 * pad)
        fn.draw(surf, name, _YELLOW, cw // 2, ty + lh + (round(3 * k) if fn is not f else 0), align="center")
        epg = self.app.epg
        cid = epg.resolve_channel_id(ch.epg_id, ch.name) if epg else None
        progs = epg.programs_in_window(cid, u0, u1) if cid else []
        span, gw = (u1 - u0).total_seconds(), W - cw
        if not progs:
            cell = pygame.Rect(cw + g, g, gw - 2 * g, rh - 2 * g)
            _bevel(surf, cell)
            f.draw(surf, "No Information", _GREY, cell.x + pad, ty)
            return surf
        for p in progs:
            a, b = max(p.start, u0), min(p.stop, u1)
            x0 = cw + (a - u0).total_seconds() / span * gw
            x1 = cw + (b - u0).total_seconds() / span * gw
            cell = pygame.Rect(int(x0) + g, g, int(x1) - int(x0) - 2 * g, rh - 2 * g)
            if cell.w < 8:
                continue
            _bevel(surf, cell)
            tx0, tx1 = cell.x + pad, cell.right - pad
            arrow, ah = round(22 * k), round(14 * k)        # the chevrons' room, their height
            if p.start < u0:
                _chevrons(surf, cell.x + round(4 * k), cell.centery, ah, right=False)
                tx0 += arrow
            if p.stop > u1:
                _chevrons(surf, cell.right - round(4 * k) - round(18 * k), cell.centery, ah, right=True)
                tx1 -= arrow
            if tx1 - tx0 < round(20 * k):
                continue
            title = p.title
            if p.start > u0 and p.start.minute % 30:
                title = f"({p.start.astimezone().strftime('%I:%M').lstrip('0')}) {title}"
            for i, line in enumerate(f.wrap(title, tx1 - tx0, 2)):
                f.draw(surf, line, _WHITE, tx0, ty + i * lh)
        return surf


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
            self._bg = _gradient((W, H), _SKY_TOP, _SKY_BOTTOM)
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


# ── Music ─────────────────────────────────────────────────────────────────
# Each own channel plays its background music while it's tuned, through
# pygame's mixer (mpv is stopped): Cathode's own loops in assets/sounds,
# or a file dropped in ~/.config/cathode/music/<kind>.ogg (mp3, wav, flac)
# to play instead. It follows the box's volume and mute like a programme's
# sound would.

_playing = None


def music_file(kind: str):
    from . import paths
    own = os.path.join(os.path.dirname(paths.config_path()), "music")
    for d in (own, paths.asset("sounds")):
        for ext in ("ogg", "mp3", "wav", "flac"):
            p = os.path.join(d, f"{kind}.{ext}")
            if os.path.isfile(p):
                return p
    return None


def play_music(kind: str, app):
    global _playing
    stop_music()
    if not getattr(app.config, "own_music", True):
        return
    p = music_file(kind)
    if not p:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.music.load(p)
        _playing = kind
        music_volume(app)
        pygame.mixer.music.play(-1)
    except Exception as e:              # no audio device: a quiet channel
        _playing = None
        print(f"[cathode] channel music off: {e!r}")


def stop_music():
    global _playing
    if _playing:
        _playing = None
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass


def music_volume(app):
    """The box's volume and mute, applied to the music."""
    if not _playing:
        return
    try:
        v = app.video
        pygame.mixer.music.set_volume(0.0 if v.muted else 0.6 * max(0, min(100, v.volume)) / 100)
    except Exception:
        pass

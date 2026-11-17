"""What goes over the picture beside a skin's own drawing, the same in every
box: the rating box as a programme starts, the up-next countdown, the
tuning screen's blue or logo card, the guide's seasonal decorations, and a
television's frame round it all (the bezel)."""

from __future__ import annotations

import math
import random
import time
from datetime import date, datetime, timezone

import pygame


def on_live(skin, live) -> bool:
    """Live TV watched with nothing over it."""
    app = skin.app
    return (live.phase == "watch" and not live.message and not live.standby and not getattr(live, "signoff", None)
            and getattr(live, "page", None) is None and getattr(app, "top", lambda: live)() is live)


def frame(skin) -> int:
    """How far in the bezel reaches (0 without one): what's drawn over the
    picture keeps inside it."""
    if getattr(skin.app.config, "bezel", "off") == "off":
        return 0
    return max(8, skin.canvas[1] // 16) + skin.canvas[1] // 30


def draw_rating(skin, c, live):
    """TV-PG in a box, top left, as a programme starts (the 1997 ratings'
    box: white on black)."""
    r = getattr(live, "rating", None)
    if not r or time.monotonic() >= r["until"] or not on_live(skin, live):
        return
    W, H = skin.canvas
    f = skin.fb(max(14, H // 16))
    text = r["text"]
    tw = skin.text.width(f, text)
    box = pygame.Rect(H // 22 + frame(skin), H // 22 + frame(skin), tw + H // 14, skin.text.ink(f)[1] + H // 16)
    pygame.draw.rect(c, (0, 0, 0), box)
    pygame.draw.rect(c, (255, 255, 255), box, max(2, H // 180))
    skin.text.draw(c, text, f, (255, 255, 255), box.centerx, box.y + H // 32, align="center")


def draw_upnext(skin, c, live):
    """'Up next: The Simpsons  0:23' over a programme's last seconds."""
    u, secs = getattr(live, "upnext", None), int(getattr(skin.app.config, "upnext_seconds", 0) or 0)
    if not u or not secs or not on_live(skin, live):
        return
    left = (u["at"] - datetime.now(timezone.utc)).total_seconds()
    if not 0 < left <= secs:
        return
    W, H = skin.canvas
    f1, f2 = skin.fb(max(12, H // 26)), skin.f(max(12, H // 26))
    label, clock = "UP NEXT", f"{int(left) // 60}:{int(left) % 60:02d}"
    title = skin.text.fit(f2, u["title"], W // 2)
    w = skin.text.width(f1, label) + skin.text.width(f2, title) + skin.text.width(f1, clock) + H // 6
    h = skin.text.ink(f1)[1] + H // 30
    box = pygame.Rect(W - w - H // 20 - frame(skin), H - h - H // 7 - frame(skin) // 2, w, h)
    s = pygame.Surface(box.size, pygame.SRCALPHA)
    s.fill((0, 0, 0, 170))
    c.blit(s, box.topleft)
    x, y = box.x + H // 40, box.y + H // 60
    skin.text.draw(c, label, f1, (255, 210, 60), x, y)
    x += skin.text.width(f1, label) + H // 30
    skin.text.draw(c, title, f2, (255, 255, 255), x, y)
    skin.text.draw(c, clock, f1, (255, 255, 255), box.right - H // 40, y, align="right")
    skin.app.after(1.0, skin.app.invalidate)


def draw_popup(skin, c, live):
    """A pop-up trivia bubble: white, round, with a tail, as Pop-Up Video's."""
    p = getattr(live, "popup", None)
    if not p or time.monotonic() >= p["until"] or not on_live(skin, live):
        return
    W, H = skin.canvas
    f = skin.fb(max(12, H // 28))
    lines = skin.text.wrap(f, p["text"], W // 3, 4)
    lh = skin.text.ink(f)[1] + 2
    w = max(skin.text.width(f, ln) for ln in lines) + H // 14
    h = lh * len(lines) + H // 18
    m = H // 10 + frame(skin)
    x = m if p["pos"].endswith("left") else W - m - w
    y = m if p["pos"].startswith("top") else H // 2 - h // 2
    box = pygame.Rect(x, y, w, h)
    tail_x = box.x + w // 4 if p["pos"].endswith("left") else box.right - w // 4
    pygame.draw.polygon(c, (0, 0, 0), [(tail_x - H // 40, box.bottom - 2), (tail_x + H // 40, box.bottom - 2),
                                       (tail_x - H // 60, box.bottom + H // 18)])
    pygame.draw.rect(c, (0, 0, 0), box.inflate(6, 6), border_radius=h // 3)
    pygame.draw.rect(c, (255, 255, 255), box, border_radius=h // 3)
    pygame.draw.polygon(c, (255, 255, 255), [(tail_x - H // 40 + 3, box.bottom - 3), (tail_x + H // 40 - 3, box.bottom - 3),
                                             (tail_x - H // 60, box.bottom + H // 18 - 5)])
    yy = box.y + H // 36
    for ln in lines:
        skin.text.draw(c, ln, f, (0, 0, 0), box.centerx, yy, align="center")
        yy += lh


def draw_locked(skin, c, live):
    """Over a locked channel's scrambled picture: what it is and how in."""
    if not getattr(live, "locked", False) or live.phase not in ("watch", "reveal"):
        return
    W, H = skin.canvas
    f1, f2 = skin.fb(max(16, H // 14)), skin.f(max(12, H // 26))
    box = pygame.Rect(0, 0, W * 2 // 3, H // 4)
    box.center = (W // 2, H // 2)
    s = pygame.Surface(box.size, pygame.SRCALPHA)
    s.fill((0, 0, 0, 190))
    c.blit(s, box.topleft)
    pygame.draw.rect(c, (255, 255, 255), box, max(1, H // 240))
    skin.text.draw(c, "THIS CHANNEL IS LOCKED", f1, (255, 255, 255), W // 2, box.y + H // 30, align="center")
    skin.text.draw(c, "Press SELECT and enter the PIN to watch.", f2, (220, 220, 220), W // 2, box.y + H // 7,
                   align="center")


def draw_alert_crawl(skin, c, live):
    """A severe weather alert crawling along the top of live TV, red, as
    stations ran them, while the NWS has one out for your area."""
    if getattr(live, "phase", "") != "watch" or getattr(skin.app, "top", lambda: live)() is not live:
        return
    from .. import radar
    items = [a for a in radar.alerts_now(skin.app) if a.get("severity") in radar.SEVERE]
    if not items:
        return
    W, H = skin.canvas
    f = skin.fb(max(12, H // 26))
    text = "     ".join(f"{a['event'].upper()}: {a['headline']}" for a in items)
    h = skin.text.ink(f)[1] + H // 40
    y0 = frame(skin)
    pygame.draw.rect(c, (170, 0, 0), (0, y0, W, h))
    lab = " WEATHER ALERT "
    lw = skin.text.width(f, lab)
    tw = skin.text.width(f, text)
    x = W - ((time.monotonic() * 90) % (tw + W - lw))
    clip = c.get_clip()
    c.set_clip(pygame.Rect(lw, y0, W - lw, h))
    skin.text.draw(c, text, f, (255, 255, 255), int(x), y0 + H // 80)
    c.set_clip(clip)
    pygame.draw.rect(c, (255, 255, 255), (0, y0, lw, h))
    skin.text.draw(c, lab, f, (170, 0, 0), 0, y0 + H // 80)
    skin.app.after(0.1 if _box() else 0.05, skin.app.invalidate)


def _box() -> bool:
    from .. import paths
    return getattr(paths, "ANDROID", False)


def bug_shown(skin, live) -> bool:
    """The screen bug's mode: always; on change (fifteen seconds after a
    tune or a programme's start); periodic (half a minute in every ten)."""
    mode = getattr(skin.app.config, "bug_mode", "always")
    if mode == "change":
        since = time.monotonic() - max(getattr(live, "tuned_at", 0.0), getattr(live, "prog_at", 0.0))
        if since < 15:
            skin.app.after(15 - since + 0.05, skin.app.invalidate)
            return True
        return False
    if mode == "periodic":
        into = time.time() % 600
        skin.app.after((30 - into if into < 30 else 600 - into) + 0.05, skin.app.invalidate)
        return into < 30
    return True


def picture_inset(skin) -> int:
    """How far in a 4:3 picture's edge is on this screen (0 on a 4:3 one)."""
    W, H = skin.canvas
    return max(0, (W - H * 4 // 3) // 2)


def draw_tune_screen(skin, c, live):
    """A chosen tuning screen over the black: blue, or the channel's logo."""
    pick = getattr(skin.app.config, "tune_screen", "box")
    if pick not in ("blue", "logo") or live.phase != "cover":
        return
    W, H = skin.canvas
    if pick == "blue":
        c.fill((16, 32, 160))
        return
    ch = live.channel
    if ch is None:
        return
    from ..logos import url_for
    img = skin.logo(url_for(skin.app, ch), W // 3, H // 3)
    if img is not None:
        c.blit(img, img.get_rect(center=(W // 2, H // 2 - H // 20)))
    f = skin.fb(max(14, H // 18))
    skin.text.draw(c, f"{ch.number:g}  {ch.name}", f, (230, 230, 230), W // 2, int(H * 0.72), align="center")


# ── Seasonal decorations (the guide) ─────────────────────────────────────

SEASONS = [((12, 1), (1, 6), "snow"), ((10, 1), (11, 30), "leaves"), ((2, 1), (2, 14), "hearts"),
           ((6, 28), (7, 4), "stars")]


def season(today: date = None) -> str:
    d = today or date.today()
    md = (d.month, d.day)
    for a, b, kind in SEASONS:
        if (a <= md <= b) if a <= b else (md >= a or md <= b):
            return kind
    return ""


def draw_decorations(skin, c):
    kind = season() if getattr(skin.app.config, "decorations", True) else ""
    if not kind:
        return
    W, H = skin.canvas
    t = time.monotonic()
    rnd = random.Random(7)
    colours = {"snow": [(255, 255, 255)], "leaves": [(214, 120, 30), (180, 70, 20), (230, 170, 40)],
               "hearts": [(240, 90, 130), (255, 150, 180)], "stars": [(230, 40, 40), (255, 255, 255), (60, 90, 230)]}
    for n in range(28):
        x0, speed, sway, size = rnd.random(), 0.03 + 0.04 * rnd.random(), rnd.random() * 6.28, 2 + rnd.random() * 3
        col = rnd.choice(colours[kind])
        if kind == "stars":                    # twinkling where they are
            a = 0.5 + 0.5 * math.sin(t * 2 + sway)
            x, y = int(x0 * W), int(rnd.random() * H)
            r = max(1, int(size * H / 720 * (0.5 + a)))
            pygame.draw.line(c, col, (x - r * 2, y), (x + r * 2, y), max(1, r // 2))
            pygame.draw.line(c, col, (x, y - r * 2), (x, y + r * 2), max(1, r // 2))
            continue
        y = ((t * speed + rnd.random()) % 1.0) * (H + 20) - 10
        x = (x0 * W + math.sin(t * 0.8 + sway) * W * 0.02) % W
        r = max(1, int(size * H / 720))
        if kind == "snow":
            pygame.draw.circle(c, col, (int(x), int(y)), r)
        elif kind == "leaves":
            a = t * 1.5 + sway
            pts = [(x + math.cos(a + k * math.pi / 2) * r * (2 if k % 2 == 0 else 1),
                    y + math.sin(a + k * math.pi / 2) * r * (2 if k % 2 == 0 else 1)) for k in range(4)]
            pygame.draw.polygon(c, col, pts)
        else:                                  # hearts
            pygame.draw.circle(c, col, (int(x - r), int(y)), r)
            pygame.draw.circle(c, col, (int(x + r), int(y)), r)
            pygame.draw.polygon(c, col, [(x - 2 * r, y + r // 3), (x + 2 * r, y + r // 3), (x, y + 2.5 * r)])
    skin.app.after(0.08, skin.app.invalidate)


# ── The bezel ────────────────────────────────────────────────────────────

BEZELS = [("off", "Off"), ("wood", "Wood grain"), ("black", "Black plastic"), ("silver", "Silver")]
_memo: dict = {}


def bezel(size, style: str) -> pygame.Surface:
    """A television's frame for a canvas: the cabinet round a screen with
    rounded corners, its inner edge shaded as a tube's glass sits in it."""
    key = (size, style)
    if key in _memo:
        return _memo[key]
    W, H = size
    th = max(8, H // 16)
    s = pygame.Surface(size, pygame.SRCALPHA)
    base = {"wood": (92, 56, 30), "black": (18, 18, 20), "silver": (150, 152, 158)}[style]
    s.fill(base + (255,))
    if style == "wood":
        rnd = random.Random(3)
        for y in range(0, H, 2):
            k = 0.82 + 0.18 * math.sin(y * 0.09 + math.sin(y * 0.013) * 4) + rnd.uniform(-0.04, 0.04)
            pygame.draw.line(s, tuple(min(255, int(v * k)) for v in base) + (255,), (0, y), (W, y))
    else:
        for y in range(H):                      # a gentle sheen, lighter at the top
            k = 1.25 - 0.45 * y / H
            pygame.draw.line(s, tuple(min(255, int(v * k + (8 if style == "black" else 0))) for v in base) + (255,),
                             (0, y), (W, y))
    hole = pygame.Rect(th, th, W - 2 * th, H - 2 * th - th // 3)
    rad = max(6, H // 14)
    for k in range(max(2, th // 3), 0, -1):    # the inner shadow, darkest at the glass
        a = int(200 * (1 - k / max(2, th // 3)))
        pygame.draw.rect(s, (0, 0, 0, a), hole.inflate(k * 2, k * 2), max(1, 2), border_radius=rad + k)
    pygame.draw.rect(s, (0, 0, 0, 0), hole, border_radius=rad)
    _memo.clear()
    _memo[key] = s
    return s


def draw_bezel(skin, c):
    style = getattr(skin.app.config, "bezel", "off")
    if style in ("wood", "black", "silver"):
        c.blit(bezel(c.get_size(), style), (0, 0))

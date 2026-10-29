"""The cable boxes' chrome, drawn.

Each sprite the Passage and i-Grid skins blit (a page with its text taken
out, a band, a row, a key) is a list of strokes in the sprite's own pixels,
drawn at four times the size and scaled down, so edges and rounded corners
come out clean. The strokes were measured off the boxes' manual frames;
the frames themselves are not in the repo.

A stroke is a tuple:
  ("fill", (x, y, w, h), rgb[, radius])          a flat rectangle
  ("grad", (x, y, w, h), top, bottom[, radius])  a vertical gradient
  ("hgrad", (x, y, w, h), left, right[, radius]) a horizontal gradient
  ("sheen", (x, y, w, h), edge, mid)             horizontal, edge -> mid -> edge
  ("rim", (x, y, w, h), rgb, width[, radius])    an outline inside the rect
  ("hole", (x, y, w, h)[, radius])               cut to transparent
  ("line", (x0, y0, x1, y1), rgb, width)
  ("poly", [(x, y), ...], rgb)
  ("circle", (cx, cy, r), rgb)
  ("text", (cx, cy), s, size, rgb)              bold lettering centred there
Colours are RGB or RGBA (a translucent stroke shades what is under it).
`radius` is one number or (top-left, top-right, bottom-right, bottom-left)."""

import pygame

from ..paths import asset

S = 4                                   # drawn this many times larger, then scaled down


def _rect(r):
    x, y, w, h = r
    return pygame.Rect(x * S, y * S, w * S, h * S)


def _radii(radius):
    if isinstance(radius, (tuple, list)):
        tl, tr, br, bl = (int(v * S) for v in radius)
        return dict(border_top_left_radius=tl, border_top_right_radius=tr, border_bottom_right_radius=br, border_bottom_left_radius=bl)
    return dict(border_radius=int(radius * S))


def _rgba(c):
    return (c[0], c[1], c[2], c[3] if len(c) > 3 else 255)


def _grad(surface, r, a, b, radius=0, horizontal=False):
    strip = pygame.Surface((2, 1) if horizontal else (1, 2), pygame.SRCALPHA)
    strip.set_at((0, 0), _rgba(a))
    strip.set_at((1, 0) if horizontal else (0, 1), _rgba(b))
    g = pygame.transform.smoothscale(strip, r.size)
    if radius:
        mask = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), **_radii(radius))
        g.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surface.blit(g, r.topleft)


def _draw(s, op):
    kind = op[0]
    if kind == "fill":
        radius = op[3] if len(op) > 3 else 0
        c = _rgba(op[2])
        if c[3] < 255:                                      # a shade over what is there
            layer = pygame.Surface(_rect(op[1]).size, pygame.SRCALPHA)
            pygame.draw.rect(layer, c, layer.get_rect(), **(_radii(radius) if radius else {}))
            s.blit(layer, _rect(op[1]).topleft)
        else:
            pygame.draw.rect(s, c, _rect(op[1]), **(_radii(radius) if radius else {}))
    elif kind == "grad":
        _grad(s, _rect(op[1]), op[2], op[3], op[4] if len(op) > 4 else 0)
    elif kind == "hgrad":
        _grad(s, _rect(op[1]), op[2], op[3], op[4] if len(op) > 4 else 0, horizontal=True)
    elif kind == "sheen":
        x, y, w, h = op[1]
        half = w / 2
        _grad(s, _rect((x, y, half, h)), op[2], op[3], horizontal=True)
        _grad(s, _rect((x + half, y, w - half, h)), op[3], op[2], horizontal=True)
    elif kind == "rim":
        radius = op[4] if len(op) > 4 else 0
        pygame.draw.rect(s, _rgba(op[2]), _rect(op[1]), int(op[3] * S), **(_radii(radius) if radius else {}))
    elif kind == "hole":
        radius = op[2] if len(op) > 2 else 0
        pygame.draw.rect(s, (0, 0, 0, 0), _rect(op[1]), **(_radii(radius) if radius else {}))
    elif kind == "line":
        x0, y0, x1, y1 = op[1]
        pygame.draw.line(s, _rgba(op[2]), (x0 * S, y0 * S), (x1 * S, y1 * S), max(1, int(op[3] * S)))
    elif kind == "poly":
        pygame.draw.polygon(s, _rgba(op[2]), [(x * S, y * S) for x, y in op[1]])
    elif kind == "circle":
        cx, cy, r = op[1]
        pygame.draw.circle(s, _rgba(op[2]), (cx * S, cy * S), r * S)
    elif kind == "text":
        cx, cy = op[1]
        f = pygame.font.Font(asset("fonts", "LiberationSans-Bold.ttf"), int(op[3] * S))
        img = f.render(op[2], True, _rgba(op[4]))
        s.blit(img, img.get_rect(center=(cx * S, cy * S)))
    else:
        raise ValueError(kind)


def render(size, ops):
    """The sprite: `ops` drawn at S times `size`, scaled down to it."""
    w, h = size
    s = pygame.Surface((w * S, h * S), pygame.SRCALPHA)
    for op in ops:
        _draw(s, op)
    return pygame.transform.smoothscale(s, (w, h))


# ── Cumcast i-Grid ──────────────────────────────────────────────────────────
# A navy page; a blue panel beside the picture window; steel channel tiles
# with a bright edge, navy cells with a pale rule between rows; a blue
# gradient band along the foot.

IG_NAVY = (1, 51, 103)
IG_CELL = (0, 38, 77)
IG_WIN = (400, 20, 240, 176)            # the picture window


def _ig_head(groove=True):
    """The header and the blue info panel beside the window, with the panel's
    bright lower edge and its shadow onto the page."""
    ops = [("fill", (0, 0, 640, 480), IG_NAVY),
           ("fill", (0, 84, 400, 4), (0, 15, 33)),
           ("grad", (0, 88, 400, 98), (36, 77, 123), (112, 146, 192)),
           ("fill", (0, 186, 400, 2), (117, 155, 200)),
           ("grad", (0, 188, 400, 8), (97, 142, 184), (4, 48, 95))]
    if groove:                                   # the pages whose body starts dark under the shadow
        ops.append(("grad", (0, 194, 400, 5), (0, 8, 32), (0, 42, 86)))
    return ops


def _ig_foot(y, ramp, top, bottom):
    """The foot band: `ramp` rows easing from the page into it, then the
    gradient to the screen's bottom."""
    return [("grad", (0, y, 640, ramp), (17, 59, 101), (100, 148, 188)),
            ("grad", (0, y + ramp, 640, 480 - y - ramp), top, bottom)]


def _ig_rows(y0, pitch, h, n, tile_w, tile, gap):
    """Channel tiles (none when tile_w is 0) and cells, a dark gap with a
    pale rule between rows."""
    ops = []
    for k in range(n):
        y = y0 + pitch * k
        if tile_w:
            ops += [("fill", (0, y, tile_w, h), tile),
                    ("fill", (tile_w, y, 2, h), (232, 246, 255)),
                    ("fill", (tile_w + 2, y, 1, h), (120, 128, 140))]
        ops.append(("fill", (tile_w + 3 if tile_w else 0, y, 640, h), IG_CELL))
        if k < n - 1:
            ops += [("fill", (0, y + h, 640, gap), (8, 18, 34)),
                    ("fill", (tile_w + 3 if tile_w else 0, y + h + 1, 640, 2), (158, 164, 158))]
    return ops


IGRID = {
    "guide.png": ((640, 480), _ig_head(False) + [
        ("fill", (0, 199, 640, 25), (14, 61, 112)),                       # the time bar
        ("poly", [(600, 206), (608, 213), (600, 220)], (205, 218, 232)),   # more hours this way
        ("fill", (0, 224, 640, 2), (4, 2, 8))]
        + _ig_rows(226, 45, 41, 4, 125, (146, 186, 221), 4)
        + _ig_foot(402, 7, (112, 153, 196), (46, 89, 137)) + [("hole", IG_WIN)]),
    "list.png": ((640, 480), _ig_head(False) + [("fill", (0, 224, 640, 2), (4, 2, 8))]
        + _ig_rows(226, 35, 32, 6, 150, (149, 172, 203), 3)
        + _ig_foot(433, 6, (112, 154, 196), (48, 89, 140)) + [("hole", IG_WIN)]),
    "search.png": ((640, 480), _ig_head(False) + [("fill", (0, 224, 640, 2), (4, 2, 8))]
        + _ig_rows(226, 35, 32, 6, 0, None, 3)
        + _ig_foot(433, 6, (112, 154, 196), (48, 89, 140)) + [("hole", IG_WIN)]),
    "page.png": ((640, 480), _ig_head() + [("grad", (0, 442, 640, 6), (0, 46, 95), (0, 11, 27))]
        + _ig_foot(448, 8, (102, 134, 181), (50, 91, 142)) + [("hole", IG_WIN)]),
    "info.png": ((640, 480), _ig_head() + [("grad", (0, 364, 640, 6), (4, 44, 93), (0, 12, 36))]
        + _ig_foot(370, 8, (116, 148, 196), (48, 90, 137)) + [
        ("fill", (60, 379, 36, 36), (6, 36, 80), 7),                       # the BACK key: a navy button
        ("grad", (62, 381, 32, 32), (70, 120, 190), (20, 60, 120), 6),
        ("line", (70, 394, 87, 394), (255, 255, 255), 2.5),               # its arrow: a bar, a hook, a head
        ("line", (86, 394, 86, 404), (255, 255, 255), 2.5),
        ("line", (78, 404, 87, 404), (255, 255, 255), 2.5),
        ("poly", [(64, 394), (73, 388), (73, 400)], (255, 255, 255)),
        ("hole", IG_WIN)]),
    "banner.png": ((640, 128), [
        ("fill", (0, 4, 640, 2), (200, 223, 248)),
        ("grad", (0, 6, 640, 26), (99, 133, 204), (14, 64, 115)),
        ("grad", (0, 32, 640, 4), (11, 56, 98), (10, 30, 50)),
        ("fill", (0, 36, 640, 2), (0, 2, 11)),
        ("fill", (0, 38, 640, 90), (2, 38, 74))]),
    "dialog.png": ((531, 137), [
        ("fill", (0, 0, 531, 137), (8, 40, 81), 7),
        ("rim", (2, 2, 527, 133), (30, 68, 113), 1, 6)]),
    "cap.png": ((268, 38), [
        ("fill", (0, 0, 268, 38), (10, 48, 96), 19),
        ("fill", (1, 1, 266, 36), (165, 182, 202), 18),
        ("fill", (4, 4, 260, 30), (48, 80, 145), 15)]),
    "cap_sel.png": ((266, 38), [
        ("fill", (0, 0, 266, 38), (12, 50, 90), 19),
        ("fill", (1, 1, 264, 36), (190, 200, 190), 18),
        ("fill", (4, 4, 258, 30), (254, 255, 155), 15)]),
    "row_sel.png": ((487, 32), [
        ("fill", (0, 0, 487, 32), (255, 254, 156)),
        ("fill", (0, 0, 1, 32), (21, 22, 14)),
        ("fill", (1, 0, 1, 32), (86, 87, 50))]),
    "tile.png": ((148, 32), [
        ("fill", (0, 0, 148, 32), (149, 183, 218)),
        ("fill", (0, 0, 148, 1), (157, 179, 203)),
        ("fill", (144, 0, 2, 32), (146, 184, 229)),
        ("fill", (147, 0, 1, 32), (184, 208, 227))]),
}

# ── Passage ─────────────────────────────────────────────────────────────────
# A silver page lit from the middle; a cream card with one big rounded corner
# top-left and the picture beside it over a maroon channel strip; panels
# with a light rim, a dark line and an inner shadow, ended square at the
# left and rounded at x 632; lavender headers over a purple grid.

PA_CREAM = (224, 222, 147)
PA_PURPLE = (80, 72, 129)
PA_LAV = (154, 144, 181)
PA_SHADE = (30, 20, 50)                  # the inner shadows' colour, faded by alpha


def _r(radius, d):
    """`radius` shrunk by d for an inset rectangle."""
    if isinstance(radius, (tuple, list)):
        return tuple(max(0, v - d) if v else 0 for v in radius)
    return max(0, radius - d)


def _pa_page(top=175, mid=255, bottom=175, y_mid=250):
    """The silver page: lit at y_mid, darker toward the top and bottom."""
    return [("grad", (0, 0, 640, y_mid), (top,) * 3, (mid,) * 3),
            ("grad", (0, y_mid, 640, 480 - y_mid), (mid,) * 3, (bottom,) * 3)]


def _pa_window(x, y, w, h):
    """The picture window, its left and bottom edges shaded onto the page."""
    return [("hgrad", (x - 6, y, 6, h), (*PA_SHADE, 0), (*PA_SHADE, 170)),
            ("hole", (x, y, w, h))]


def _pa_shadow(x, y, w, h, radius=0, depth=10, alpha=150):
    """An inner shadow along the top and left of a rectangle."""
    return [("grad", (x, y, w, depth), (*PA_SHADE, alpha), (*PA_SHADE, 0), radius),
            ("hgrad", (x, y, depth, h), (*PA_SHADE, alpha), (*PA_SHADE, 0), radius)]


def _pa_card(x=46, y=33, w=274, h=190, radius=(24, 0, 0, 0)):
    """The cream card: a dark outline, the cream lit at the top, an inner
    shadow along its top, left and right, and the echo swoosh."""
    return ([("fill", (x, y, w, h), (96, 96, 72), radius),
             ("grad", (x + 3, y + 3, w - 3, h - 3), PA_CREAM, (224, 213, 129), _r(radius, 3)),
             ("hgrad", (x + w - 14, y + 3, 14, h - 3), (*PA_SHADE, 0), (*PA_SHADE, 120))]
            + _pa_shadow(x + 3, y + 3, w - 3, h - 3, _r(radius, 3), 12, 190) + [
            ("grad", (x + 3, y + h - 8, w - 3, 8), (*PA_SHADE, 0), (*PA_SHADE, 90)),
            ("circle", (283, 70, 22), (60, 100, 185)),                   # the swoosh: two crescents and a ball
            ("circle", (288, 67, 21), (224, 221, 145)),
            ("circle", (288, 76, 13), (130, 170, 225)),
            ("circle", (292, 74, 12), (224, 221, 145)),
            ("circle", (301, 93, 6), (40, 80, 190)),
            ("circle", (299, 91, 2), (200, 220, 255))])


def _pa_strip(y=200, maroon=(89, 19, 30), tab=(156, 144, 188)):
    """The channel strip under the window: maroon, then the clock's lavender
    tab with a slanted join."""
    return [("fill", (320, y, 186, 23), maroon),
            ("hgrad", (320, y, 6, 23), (*PA_SHADE, 160), (*PA_SHADE, 0)),
            ("poly", [(505, y), (640, y), (640, y + 23), (496, y + 23)], tab)]


def _pa_panel(x, y, w, h, body, radius=(0, 8, 8, 0)):
    """A panel: a light rim, a dark line, `body` drawn inside, then an
    inner shadow along its top and left."""
    return ([("fill", (x, y, w, h), (226, 222, 232), radius),
             ("fill", (x + 2, y + 2, 4, h - 4), (62, 56, 72))]
            + body + _pa_shadow(x + 4, y + 2, w - 6, h - 4, _r(radius, 2), 8, 150))


def _pa_header(x, y, w):
    """A lavender header band with the groove under it."""
    return [("grad", (x, y, w, 23), PA_LAV, (160, 148, 191)),
            ("fill", (x, y + 23, w, 2), (90, 82, 100)),
            ("fill", (x, y + 25, w, 1), (162, 156, 175))]


def _pa_guide_body():
    ops = [("fill", (56, 225, 574, 173), PA_PURPLE, (0, 6, 6, 8))] + _pa_header(56, 225, 574) + [
        ("grad", (56, 254, 119, 144), (176, 166, 200), (192, 184, 214), (0, 0, 0, 8)),   # the channel column
        ("hgrad", (175, 254, 6, 143), (*PA_SHADE, 0), (*PA_SHADE, 170))]
    for ry in (282, 311, 340, 369):                                     # the rules between rows
        ops.append(("fill", (56, ry, 574, 2), (170, 163, 200)))
    for dx in (184, 321, 458, 595):                                     # the hour columns' grooves
        ops += [("fill", (dx, 225, 2, 23), (128, 117, 150)), ("fill", (dx + 2, 225, 2, 23), (175, 163, 199))]
    return ops


PASSAGE = {
    "guide.png": ((640, 480), _pa_page() + _pa_card() + _pa_window(320, 0, 320, 200) + _pa_strip()
        + _pa_panel(52, 223, 580, 178, _pa_guide_body(), (0, 8, 8, 10))),
    "info.png": ((640, 480), _pa_page() + _pa_card() + _pa_window(320, 0, 320, 200) + _pa_strip()
        + _pa_panel(52, 223, 580, 183, [("grad", (56, 225, 574, 179), (147, 134, 178), (108, 98, 125), (0, 6, 6, 8))]
                    + _pa_header(56, 225, 574), (0, 8, 8, 10))),
    "search.png": ((640, 480), _pa_page() + _pa_card() + _pa_window(320, 0, 320, 200) + _pa_strip()
        + _pa_panel(52, 223, 580, 181, [("grad", (56, 225, 574, 88), (168, 153, 192), (228, 223, 244), (0, 6, 0, 0)),
                                        ("grad", (56, 313, 574, 89), (228, 223, 244), (147, 135, 168), (0, 0, 6, 8)),
                                        ("fill", (204, 252, 2, 146), (150, 142, 168))]      # the two columns' divider
                    + _pa_header(56, 225, 574), (0, 8, 8, 10))),
    "od.png": ((640, 480), _pa_page(126, 248, 127) + _pa_window(320, 0, 320, 216) + _pa_strip(216, (127, 88, 105), (178, 188, 192)) + [
        ("fill", (0, 42, 300, 46), (52, 52, 52), (0, 23, 23, 0)),                         # the mark's box
        ("grad", (0, 43, 298, 22), (200, 200, 200), (242, 242, 242), (0, 22, 0, 0)),
        ("grad", (0, 65, 298, 22), (242, 242, 242), (190, 190, 190), (0, 0, 22, 0)),
        ("fill", (50, 103, 270, 172), (70, 78, 82), (18, 0, 0, 0)),                       # the list panel
        ("grad", (56, 106, 264, 169), (128, 152, 158), (180, 190, 192), (14, 0, 0, 0))]
        + [op for ry in (162, 199, 236, 273) for op in (("fill", (56, ry, 264, 1), (170, 189, 193)), ("fill", (56, ry + 1, 264, 1), (240, 246, 249)))]
        + _pa_shadow(56, 106, 264, 169, (14, 0, 0, 0), 8, 110) + [
        ("fill", (318, 275, 314, 117), (120, 150, 157), (0, 8, 8, 0)),                   # the details panel, teal
        ("fill", (320, 277, 310, 113), (48, 106, 112), (0, 6, 6, 0)),
        ("grad", (320, 380, 310, 10), (48, 106, 112), (90, 133, 139), (0, 0, 6, 6)),
        ("fill", (318, 391, 314, 1), (212, 216, 219))]
        + _pa_shadow(320, 277, 310, 113, (0, 6, 6, 0), 6, 120)),
    "page.png": ((640, 480), [
        ("grad", (0, 0, 640, 46), (161, 157, 153), (230, 226, 227)),
        ("grad", (0, 46, 640, 24), (228, 224, 224), (202, 198, 199)),
        ("grad", (0, 70, 640, 4), (187, 178, 179), (108, 99, 104)),
        ("grad", (0, 74, 640, 6), (165, 155, 94), (209, 186, 119)),
        ("fill", (0, 80, 640, 108), (223, 198, 131)),
        ("grad", (0, 188, 640, 5), (223, 198, 131), (234, 215, 147)),
        ("grad", (0, 193, 640, 6), (225, 218, 209), (172, 169, 169)),
        ("fill", (0, 199, 640, 16), (178, 173, 177)),
        ("grad", (0, 215, 640, 8), (157, 153, 149), (97, 89, 101)),
        ("grad", (0, 223, 640, 189), (218, 214, 214), (207, 198, 199)),
        ("grad", (0, 412, 640, 68), (207, 198, 199), (173, 169, 168)),
        ("poly", [(440, 413), (640, 413), (640, 434), (430, 434)], (177, 173, 167)),      # the clock's tab
        ("fill", (430, 434, 210, 2), (213, 209, 204))]
        + _pa_panel(52, 223, 580, 189, [("grad", (56, 225, 230, 90), (140, 127, 150), (185, 174, 186), (0, 0, 0, 0)),
                                        ("grad", (56, 315, 230, 95), (185, 174, 186), (150, 140, 152), (0, 0, 0, 8)),
                                        ("fill", (286, 225, 344, 185), (86, 73, 93), (0, 6, 6, 0))], (0, 8, 8, 10))
        + [("fill", (350, 189, 290, 5), (9, 5, 6))] + _pa_window(350, 0, 290, 189)),
    "browse.png": ((640, 480), [
        ("grad", (0, 0, 149, 226), (169, 170, 171), (237, 237, 237), (0, 8, 0, 0)),       # the column
        ("grad", (0, 226, 149, 150), (237, 237, 237), (176, 176, 176)),
        ("hgrad", (144, 0, 5, 376), (*PA_SHADE, 0), (*PA_SHADE, 200)),
        ("fill", (3, 283, 137, 50), (110, 100, 135), 10),                                 # the Browse box
        ("grad", (4, 284, 135, 48), (232, 232, 238), (200, 198, 210), 9),
        ("poly", [(22, 301), (22, 315), (12, 308)], (90, 80, 120)),                       # its four arrows
        ("poly", [(121, 301), (121, 315), (131, 308)], (90, 80, 120)),
        ("poly", [(64, 296), (78, 296), (71, 288)], (90, 80, 120)),
        ("poly", [(64, 320), (78, 320), (71, 328)], (90, 80, 120)),
        ("grad", (0, 366, 640, 4), (202, 203, 203), (179, 179, 182)),                     # the band
        ("grad", (0, 370, 640, 5), (161, 159, 156), (78, 70, 102)),
        ("grad", (0, 375, 640, 53), (111, 101, 141), (204, 196, 219)),
        ("grad", (0, 428, 640, 52), (204, 196, 219), (126, 116, 154))]),
    "banner.png": ((640, 91), [
        ("fill", (0, 2, 640, 82), (205, 205, 205)),
        ("fill", (0, 2, 640, 2), (216, 216, 217)),
        ("grad", (0, 4, 640, 5), (*PA_SHADE, 170), (*PA_SHADE, 0)),
        ("fill", (176, 4, 464, 80), (82, 74, 124), (14, 0, 0, 0)),                        # the title band and body
        ("grad", (178, 30, 462, 26), (163, 153, 194), (200, 195, 217)),
        ("grad", (178, 56, 462, 24), (200, 195, 217), (158, 147, 186)),
        ("poly", [(176, 30), (180, 30), (198, 80), (176, 80)], (82, 74, 124)),
        ("poly", [(576, 70), (590, 77), (576, 84)], (100, 90, 150)),
        ("fill", (0, 80, 640, 2), (191, 188, 196)),
        ("fill", (0, 82, 640, 2), (170, 170, 170)),
        ("fill", (0, 84, 640, 2), (60, 55, 50)),
        ("grad", (0, 86, 640, 4), (60, 55, 50, 160), (60, 55, 50, 0))]),
    "blocked.png": ((240, 122), None),                       # drawn to size by passage_card()
    "dialog.png": ((429, 230), [
        ("fill", (0, 0, 427, 228), (70, 70, 70), 12),
        ("fill", (0, 0, 425, 226), (220, 220, 220), 12),
        ("grad", (2, 2, 422, 223), (145, 145, 145), (162, 162, 162), 11),
        ("fill", (8, 40, 416, 30), (91, 21, 45), (8, 8, 0, 0)),
        ("fill", (8, 40, 416, 3), (60, 28, 39)),
        ("fill", (8, 67, 416, 3), (55, 15, 32)),
        ("fill", (8, 70, 416, 4), (225, 215, 232)),
        ("fill", (8, 74, 416, 119), (100, 95, 110)),
        ("grad", (12, 74, 405, 58), (197, 192, 215), (185, 176, 207)),
        ("fill", (12, 132, 405, 1), (6, 34, 82)),
        ("grad", (12, 133, 405, 57), (210, 201, 220), (172, 162, 199)),
        ("fill", (417, 74, 7, 119), (215, 214, 212)),
        ("fill", (8, 190, 416, 3), (205, 202, 213)),
        ("grad", (3, 193, 422, 32), (164, 164, 164), (148, 148, 148), (0, 0, 10, 10))]),
    "markbox.png": ((301, 51), [
        ("fill", (0, 4, 300, 44), (52, 52, 52), (0, 22, 22, 0)),
        ("grad", (0, 5, 298, 21), (200, 200, 200), (242, 242, 242), (0, 21, 0, 0)),
        ("grad", (0, 26, 298, 21), (242, 242, 242), (190, 190, 190), (0, 0, 21, 0))]),
    "od_sel.png": ((582, 37), [
        ("fill", (8, 0, 574, 37), (42, 104, 106), (0, 8, 8, 0)),
        ("fill", (8, 0, 574, 1), (110, 155, 158)),
        ("poly", [(20, 15), (33, 15), (26, 7)], (225, 200, 70)),
        ("poly", [(20, 21), (33, 21), (26, 29)], (225, 200, 70))]),
    "col_sel.png": ((123, 28), [
        ("fill", (0, 0, 123, 28), PA_PURPLE),
        ("hgrad", (0, 0, 6, 28), (*PA_SHADE, 170), (*PA_SHADE, 0))]),
    "dlg_sel.png": ((405, 26), [
        ("fill", (0, 0, 404, 26), (2, 33, 87)),
        ("fill", (404, 0, 1, 26), (219, 218, 227)),
        ("poly", [(22, 11), (34, 11), (28, 4)], (220, 200, 90)),
        ("poly", [(22, 15), (34, 15), (28, 22)], (220, 200, 90))]),
    "opt_sel.png": ((140, 24), [
        ("fill", (0, 0, 139, 24), (240, 225, 130)),
        ("fill", (139, 0, 1, 24), (56, 43, 69)),
        ("poly", [(2, 11), (14, 11), (8, 4)], (118, 36, 50)),
        ("poly", [(2, 13), (14, 13), (8, 20)], (118, 36, 50))]),
    "options.png": ((140, 192), [
        ("fill", (4, 2, 134, 189), (72, 78, 114), 7),
        ("fill", (5, 3, 132, 187), (86, 111, 157), 6),
        ("fill", (5, 3, 132, 16), (29, 34, 85), (6, 6, 0, 0)),
        ("fill", (5, 19, 132, 1), (74, 84, 126))]),
    "pill.png": ((232, 26), [
        ("fill", (0, 0, 232, 26), (66, 47, 112), 4),
        ("grad", (0, 22, 232, 4), (*PA_SHADE, 0), (*PA_SHADE, 90), (0, 0, 4, 4)),
        ("poly", [(215, 7), (215, 19), (207, 13)], (225, 200, 75)),
        ("poly", [(219, 7), (219, 19), (227, 13)], (225, 200, 75))]),
    "search_sel.png": ((440, 26), [
        ("fill", (0, 0, 440, 26), (78, 74, 125), 3),
        ("hgrad", (0, 0, 10, 26), (231, 223, 243), (78, 74, 125))]),
    "key_box.png": ((96, 46), [
        ("fill", (2, 2, 89, 40), (2, 30, 86), 8),
        ("fill", (5, 5, 83, 34), (222, 218, 238), 6),
        ("grad", (6, 6, 81, 32), (182, 174, 205), (236, 228, 246), 5)]),
    "key_a.png": ((33, 32), [                                            # a yellow triangle
        ("poly", [(16, 2), (32, 30), (0, 30)], (70, 55, 30)),
        ("poly", [(16, 7), (29, 28), (3, 28)], (238, 212, 90)),
        ("text", (16, 20), "A", 14, (40, 30, 20))]),
    "key_b.png": ((30, 32), [                                            # a blue square
        ("fill", (1, 2, 28, 28), (15, 35, 85), 3),
        ("grad", (3, 4, 24, 24), (125, 158, 220), (60, 100, 170), 2),
        ("text", (15, 16), "B", 17, (255, 255, 255))]),
    "key_c.png": ((34, 34), [
        ("circle", (18, 17, 14), (*PA_SHADE, 90)),
        ("circle", (16, 15, 14), (120, 30, 30)),
        ("circle", (16, 15, 12), (222, 70, 70)),
        ("circle", (14, 11, 5), (245, 150, 150)),
        ("text", (16, 16), "C", 15, (255, 255, 255))]),
    "sel.png": ((32, 30), [
        ("circle", (16, 15, 14), (40, 60, 110)),
        ("circle", (16, 15, 12), (110, 150, 205)),
        ("circle", (14, 11, 5), (170, 200, 240)),
        ("text", (16, 16), "SEL", 9, (255, 255, 255))]),
    "volume.png": ((640, 46), [
        ("fill", (0, 4, 640, 38), (40, 40, 40), 19),
        ("grad", (1, 5, 638, 36), (210, 210, 210), (170, 170, 170), 18),
        ("grad", (1, 5, 638, 5), (*PA_SHADE, 150), (*PA_SHADE, 0), 18),
        ("fill", (3, 8, 134, 30), (237, 236, 237), 15),
        ("fill", (144, 19, 484, 7), (106, 106, 106), 3)]),
}

def passage_card(w, h):
    """Passage's blocked-programme card at any size: the grey title band, the
    maroon rule, the light body, a grey foot."""
    body = h - 46 - 23
    return [("fill", (1, 5, w - 11, h - 8), (120, 115, 110), 8),
            ("fill", (2, 6, w - 13, h - 10), (190, 187, 183), 7),
            ("grad", (3, 7, w - 15, 27), (149, 146, 141), (182, 179, 174), (6, 6, 0, 0)),
            ("fill", (3, 34, w - 15, 10), (115, 31, 64)),
            ("fill", (3, 44, w - 15, 2), (190, 188, 185)),
            ("grad", (3, 46, w - 15, body // 2), (201, 200, 196), (214, 215, 209)),
            ("grad", (3, 46 + body // 2, w - 15, body - body // 2), (214, 215, 209), (187, 182, 178)),
            ("fill", (3, h - 23, w - 15, 3), (111, 108, 103)),
            ("grad", (3, h - 20, w - 15, 16), (190, 187, 183), (157, 152, 148), (0, 0, 7, 7))]


PASSAGE["blocked.png"] = ((240, 122), passage_card(240, 122))

CHROME = {"igrid": IGRID, "passage": PASSAGE}


def sprite(skin, name):
    """The drawn sprite, or None when the skin keeps a bitmap for it (the
    brand marks)."""
    spec = CHROME.get(skin, {}).get(name)
    return render(*spec) if spec else None

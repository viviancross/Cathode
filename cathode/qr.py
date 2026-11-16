"""A QR code for a short text (the phone remote's address), without a
library: byte mode, error correction level M, versions 1 to 6 (up to 106
bytes), the mask with the lowest penalty. After Project Nayuki's reference
implementation of the standard (ISO/IEC 18004)."""

from __future__ import annotations

from typing import List

ECC = [0, 10, 16, 26, 18, 24, 16]       # level M: error codewords per block, by version
BLOCKS = [0, 1, 1, 1, 2, 2, 4]          # level M: blocks, by version
MASKS = (lambda x, y: (x + y) % 2, lambda x, y: y % 2, lambda x, y: x % 3, lambda x, y: (x + y) % 3,
         lambda x, y: (x // 3 + y // 2) % 2, lambda x, y: x * y % 2 + x * y % 3,
         lambda x, y: (x * y % 2 + x * y % 3) % 2, lambda x, y: ((x + y) % 2 + x * y % 3) % 2)


def _raw_modules(ver: int) -> int:
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        align = ver // 7 + 2
        n -= (25 * align - 10) * align - 55
    return n


def _data_capacity(ver: int) -> int:
    return _raw_modules(ver) // 8 - ECC[ver] * BLOCKS[ver]


def _mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree: int) -> List[int]:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _mul(root, 0x02)
    return out


def _remainder(data: List[int], div: List[int]) -> List[int]:
    out = [0] * len(div)
    for b in data:
        f = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(div):
            out[i] ^= _mul(coef, f)
    return out


def _codewords(text: bytes, ver: int) -> List[int]:
    cap = _data_capacity(ver)
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in reversed(range(8))]
    for b in text:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    # the blocks, each with its error correction, interleaved
    nblocks, ecc = BLOCKS[ver], ECC[ver]
    raw = _raw_modules(ver) // 8
    nshort, shortlen = nblocks - raw % nblocks, raw // nblocks
    div, blocks, k = _divisor(ecc), [], 0
    for i in range(nblocks):
        dat = data[k:k + shortlen - ecc + (0 if i < nshort else 1)]
        k += len(dat)
        e = _remainder(dat, div)
        if i < nshort:
            dat = dat + [0]
        blocks.append(dat + e)
    return [blk[i] for i in range(len(blocks[0])) for j, blk in enumerate(blocks)
            if i != shortlen - ecc or j >= nshort]


class Code:
    def __init__(self, ver: int):
        self.ver, self.size = ver, ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def put(self, x, y, on):
        self.dark[y][x], self.fixed[y][x] = on, True

    def functions(self):
        n = self.size
        for i in range(n):
            self.put(6, i, i % 2 == 0)
            self.put(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    if 0 <= cx + dx < n and 0 <= cy + dy < n:
                        self.put(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
        if self.ver > 1:
            pos = [6, n - 7]
            for i, ax in enumerate(pos):
                for j, ay in enumerate(pos):
                    if (i, j) in ((0, 0), (0, 1), (1, 0)):
                        continue
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            self.put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)

    def format_bits(self, mask: int):
        data = (0 << 3) | mask                  # level M is 00
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 != 0     # noqa: E731
        n = self.size
        for i in range(6):
            self.put(8, i, bit(i))
        self.put(8, 7, bit(6))
        self.put(8, 8, bit(7))
        self.put(7, 8, bit(8))
        for i in range(9, 15):
            self.put(14 - i, 8, bit(i))
        for i in range(8):
            self.put(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.put(8, n - 15 + i, bit(i))
        self.put(8, n - 8, True)

    def place(self, data: List[int]):
        n, i = self.size, 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    y = n - 1 - vert if (right + 1) & 2 == 0 else vert
                    if not self.fixed[y][x] and i < len(data) * 8:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 != 0
                        i += 1
            right -= 2

    def mask(self, m: int):
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and MASKS[m](x, y) == 0:
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        """Runs of five or more, 2x2 blocks, and the balance of dark and light
        (the finder-alike rule left out: it only breaks ties among masks)."""
        n, p = self.size, 0
        for lines in (self.dark, [list(col) for col in zip(*self.dark)]):
            for row in lines:
                run = 1
                for a, b in zip(row, row[1:]):
                    if a == b:
                        run += 1
                        if run == 5:
                            p += 3
                        elif run > 5:
                            p += 1
                    else:
                        run = 1
        for y in range(n - 1):
            for x in range(n - 1):
                c = self.dark[y][x]
                if c == self.dark[y][x + 1] == self.dark[y + 1][x] == self.dark[y + 1][x + 1]:
                    p += 3
        dark = sum(map(sum, self.dark))
        p += (abs(dark * 20 - n * n * 10) + n * n - 1) // (n * n) * 10
        return p


def encode(text: str) -> List[List[bool]]:
    """The modules, rows of dark (True) and light, quiet zone not included."""
    raw = text.encode("utf-8")
    ver = next((v for v in range(1, 7) if len(raw) + 2 <= _data_capacity(v)), None)
    if ver is None:
        raise ValueError("too long for a small QR code")
    data = _codewords(raw, ver)
    best = None
    for m in range(8):
        q = Code(ver)
        q.functions()
        q.place(data)
        q.mask(m)
        q.format_bits(m)
        score = q.penalty()
        if best is None or score < best[0]:
            best = (score, q)
    return best[1].dark

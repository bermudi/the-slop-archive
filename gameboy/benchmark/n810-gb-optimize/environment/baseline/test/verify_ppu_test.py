#!/usr/bin/env python3
"""Verify the headless screenshot of ppu_test.gb.

Usage: verify_ppu_test.py [PPM]      (default /tmp/ppu_test.ppm)

Asserts EXACT shades in the headless gray palette:
  shade0 = (255,255,255)  shade1 = (170,170,170)
  shade2 = (85,85,85)     shade3 = (0,0,0)

Expected values re-derived from Pan Docs semantics for the ROM built by
gen_ppu_test.py (BGP = OBP0 = 0xE4 identity mapping; tile 1: px0=color3,
px1=color1, px2-7=color0; WX=7 -> window at x>=0; WY=16; SCX=SCY=0).

NOTE on (31,16): it was listed as shade1 in the original task text, but
tile 1 has color 0 at pixel 7, and with WX=7 screen x=31 is pixel 7 of
window-map column 3 (0x9803 = tile 1) -- the BG tile behind it (map
(3,2) = tile 1) also has color 0 at px7. So shade0 is the only value a
correct PPU can show there; the pixel carrying color 1 is x=25, which
is asserted instead.
"""
import sys

PAL = {0: (255, 255, 255), 1: (170, 170, 170), 2: (85, 85, 85), 3: (0, 0, 0)}


def load_ppm(path):
    with open(path, 'rb') as f:
        data = f.read()
    if not data.startswith(b'P6'):
        sys.exit(f"{path}: not a binary P6 PPM")
    pos = 2
    vals = []
    while len(vals) < 3:                       # width, height, maxval
        while pos < len(data) and data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b'#':          # comment line
            while pos < len(data) and data[pos:pos + 1] != b'\n':
                pos += 1
            continue
        s = pos
        while pos < len(data) and not data[pos:pos + 1].isspace():
            pos += 1
        vals.append(int(data[s:pos]))
    pos += 1                                   # single whitespace after maxval
    w, h, maxv = vals
    if maxv != 255:
        sys.exit(f"{path}: unexpected maxval {maxv}")
    raster = data[pos:pos + w * h * 3]
    if len(raster) != w * h * 3:
        sys.exit(f"{path}: truncated raster ({len(raster)} bytes)")
    return w, h, raster


def shade_of(w, h, raster, x, y):
    if not (0 <= x < w and 0 <= y < h):
        sys.exit(f"pixel ({x},{y}) outside {w}x{h} image")
    off = (y * w + x) * 3
    px = (raster[off], raster[off + 1], raster[off + 2])
    for s, rgb in PAL.items():
        if px == rgb:
            return s, px
    return None, px


# (x, y, expected shade, what it proves)
CHECKS = [
    # BG, ly=0: window not yet active (WY=16), SCX/SCY=0, map (0,0)/(1,0)=tile 1
    (0,  0,   3, "BG tile 1 px0 (map 0,0)"),
    (1,  0,   1, "BG tile 1 px1"),
    (2,  0,   0, "BG tile 1 px2"),
    (8,  0,   3, "BG tile 1 px0 (map 1,0)"),
    (9,  0,   1, "BG tile 1 px1"),
    (15, 0,   0, "BG tile boundary: tile 1 px7 = color 0"),
    # Window (WX=7 -> x>=0; win_line = ly-16; window map row 0 col 3 = tile 1)
    (0,  16,  3, "window row0 col0 shares 0x9800=tile 1 -> window is ON "
                 "(BG map (0,2) would be tile 0 = shade0)"),
    (24, 16,  3, "window row0 col3 (0x9803) = tile 1 px0"),
    (25, 16,  1, "window row0 col3 = tile 1 px1"),
    (31, 16,  0, "window tile boundary: tile 1 px7 = color 0"),
    (32, 16,  0, "window map col4 = tile 0"),
    (24, 23,  3, "window line 7 -> map row 0 col 3 px0"),
    # Window over BG: at ly=24 window shows row 1 (col 3 = 0x9823 = tile 0),
    # while BG map (3,3) = tile 1 would give shade3 without the window
    (24, 24,  0, "window over BG: hides BG tile 1 at map (3,3)"),
    # Sprite: screen (16,24), OBP0=0xE4, color 0 transparent
    (16, 24,  3, "sprite px0 (OBP0 color 3)"),
    (17, 24,  1, "sprite px1 (OBP0 color 1)"),
    (23, 24,  0, "sprite px7 transparent -> BG tile 0 shows through"),
    (10, 24,  0, "sprite priority: no sprite at x=10, BG shade 0"),
    # window fills the rest of the frame
    (159, 143, 0, "window fill, bottom-right"),
]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ppu_test.ppm'
    w, h, raster = load_ppm(path)
    print(f"{path}: P6 {w}x{h}")
    failures = 0
    for x, y, want, why in CHECKS:
        got, px = shade_of(w, h, raster, x, y)
        ok = got == want
        print(f"  ({x:3},{y:3}) want shade{want} "
              f"got {got if got is not None else '??'} {px} "
              f"[{'PASS' if ok else 'FAIL'}] {why}")
        if not ok:
            failures += 1
    total = len(CHECKS)
    print(f"{total - failures}/{total} assertions passed")
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

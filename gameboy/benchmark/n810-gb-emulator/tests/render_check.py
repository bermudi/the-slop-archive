#!/usr/bin/env python3
"""render_check.py - content-verified rendering checks for the n810-gb-emulator
verifier. Replaces the old ">2% pixels changed, >=3 colors" heuristic that any
window with a title bar satisfied.

Three subcommands:

  match --fb FB.raw --base BASE.raw --golden GOLDEN.ppm
      Searches the framebuffer dump for the 160x144 golden frame (produced by
      the trusted reference emulator from the per-run challenge ROM). Tolerant
      to integer scales 1..5, arbitrary offsets, letterboxing, arbitrary gray
      palette mapping (incl. inverted BGP), and mild noise -- via Pearson
      correlation on sampled cells. Plus stretch-to-window candidates for
      apps that rescale to the window.

  temporal --base BASE.raw --t1 T1.raw --t2 T2.raw
      Two dumps of the SAME app run (demo.gb scrolls continuously). The app
      window (pixels changed vs desktop baseline) must itself change between
      t1 and t2. Kills static/canned frames.

  selftest
      Adversarial suite for the verifier itself: correct renders at several
      scales/palettes/letterboxes must PASS; empty windows, decorative
      rectangles, title-bar-only, wrong-seed patterns and frozen frames must
      FAIL. No device needed - everything is synthetic.

Stdlib only. Output: one JSON object on stdout; exit 0 = pass.
"""
import argparse
import json
import math
import random
import struct
import sys

W, H = 800, 480
GW, GH = 160, 144


# ---------- loaders ----------------------------------------------------------

def load_raw(path):
    """800x480 RGB565 little-endian -> list of gray bytes."""
    data = open(path, "rb").read()
    if len(data) < W * H * 2:
        raise SystemExit(f"render_check: {path} too small for an fb dump ({len(data)})")
    px = struct.unpack("<%dH" % (W * H), data[: W * H * 2])
    gray = [0] * (W * H)
    for i, v in enumerate(px):
        r = (v >> 11 & 31) * 8
        g = (v >> 5 & 63) * 4
        b = (v & 31) * 8
        gray[i] = (r * 77 + g * 151 + b * 28) >> 8
    return gray


def load_ppm(path):
    """P6 PPM -> list of gray bytes (assumed 160x144). Parses the header
    token-by-token: a naive split() corrupts pixel data containing whitespace
    bytes (0x20 etc.), which 4-level gray pixel values do."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"P6"):
        raise SystemExit(f"render_check: {path} not a binary PPM")
    idx = 2
    vals = []
    while len(vals) < 3:
        while idx < len(data) and data[idx:idx + 1].isspace():
            idx += 1
        if data[idx:idx + 1] == b"#":
            while idx < len(data) and data[idx] != 0x0A:
                idx += 1
            continue
        start = idx
        while idx < len(data) and not data[idx:idx + 1].isspace():
            idx += 1
        vals.append(int(data[start:idx]))
    idx += 1                                  # single whitespace after maxval
    w, h, _maxv = vals
    raw = data[idx: idx + w * h * 3]
    if (w, h) != (GW, GH):
        raise SystemExit(f"render_check: golden must be {GW}x{GH}, got {w}x{h}")
    if len(raw) < w * h * 3:
        raise SystemExit(f"render_check: {path} truncated pixel data")
    out = [0] * (GW * GH)
    for i in range(GW * GH):
        r, g, b = raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]
        out[i] = (r * 77 + g * 151 + b * 28) >> 8
    return out


# ---------- window detection --------------------------------------------------

def changed_bbox(gray, base, margin=24):
    """Bounding box of pixels that differ from the desktop baseline, grown by
    a margin (covers window borders the WM draws after our dump)."""
    x0, y0, x1, y1 = W, H, 0, 0
    any_changed = False
    for y in range(H):
        row = y * W
        for x in range(W):
            if gray[row + x] != base[row + x]:
                any_changed = True
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if not any_changed:
        return None
    return (max(0, x0 - margin), max(0, y0 - margin),
            min(W - 1, x1 + margin), min(H - 1, y1 + margin))


def changed_bbox_exact(gray, base):
    """Same, no margin: the app's own drawn region (incl. WM decorations)."""
    x0, y0, x1, y1 = W, H, 0, 0
    any_changed = False
    for y in range(H):
        row = y * W
        for x in range(W):
            if gray[row + x] != base[row + x]:
                any_changed = True
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return (x0, y0, x1, y1) if any_changed else None


# ---------- correlation --------------------------------------------------------

def pearson(xs, ys):
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sxx = syy = 0.0
    for a, b in zip(xs, ys):
        dx, dy = a - mx, b - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    if sxx < 1e-9 or syy < 1e-9:
        return 0.0
    return sxy / math.sqrt(sxx * syy)


CELLS_SUB = [(j, i) for j in range(0, GH, 8) for i in range(0, GW, 8)]   # 360
CELLS_ALL = [(j, i) for j in range(GH) for i in range(GW)]               # 23040


def sample_cells(gray, cells, x0, y0, sx, sy):
    """Sample one cell per golden pixel: source = (x0 + i*sx, y0 + j*sy)."""
    out = []
    for j, i in cells:
        fx = x0 + (i * sx)
        fy = y0 + (j * sy)
        if fx < 0 or fy < 0 or fx >= W or fy >= H:
            return None
        out.append(gray[fy * W + fx])
    return out


def best_match(gray, base, golden_g, min_r=0.75, min_std=6.0):
    golden_sub = [golden_g[j * GW + i] for j, i in CELLS_SUB]
    golden_all = golden_g                      # CELLS_ALL is dense row-major

    def eval_scale(x0, y0, s, cells, gvals):
        got = sample_cells(gray, cells, x0 + s // 2, y0 + s // 2, s, s)
        if got is None:
            return 0.0, 0.0
        return pearson(gvals, got), 0.0

    def eval_stretch(name, x0, y0, rw, rh):
        nonlocal best
        got = [gray[(y0 + ((2 * j + 1) * rh) // (2 * GH)) * W
                    + x0 + ((2 * i + 1) * rw) // (2 * GW)]
               for j, i in CELLS_ALL]
        r = pearson(golden_all, got)
        if better(r):
            m = sum(got) / len(got)
            std = math.sqrt(sum((v - m) ** 2 for v in got) / len(got))
            best = (r, name, std)
    bbox = changed_bbox(gray, base) if base is not None else (0, 0, W - 1, H - 1)
    if bbox is None:
        return {"pass": False, "reason": "no window (nothing changed vs baseline)",
                "r": 0.0, "std": 0.0, "where": None}
    bx0, by0, bx1, by1 = bbox
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    best = None                                  # (r, where, std)

    def better(r):
        return best is None or abs(r) > abs(best[0])

    # -- stretch candidates over the exact drawn region ---------------------
    # Apps scale the 160x144 surface to the window (any aspect). The drawn
    # region includes WM chrome; peel it with top insets, and handle app-side
    # letterboxing with centered insets (GB 10:9 in an 800x480 window gives
    # e.g. 80px side margins + 24px top/bottom -- asymmetric, so a grid).
    ex = changed_bbox_exact(gray, base) if base is not None else (0, 0, W - 1, H - 1)
    if ex is not None:
        exx0, exy0, exx1, exy1 = ex
        ew, eh = exx1 - exx0 + 1, exy1 - exy0 + 1
        for top in (0, 8, 16, 24, 32, 40, 48, 56):
            if eh - top >= GH and ew >= GW:
                eval_stretch("stretch-top%d" % top, exx0, exy0 + top, ew, eh - top)
        for dx in (0, 16, 32, 48, 64, 80, 96, 112):
            for dy in (0, 8, 16, 24, 32, 48, 64):
                rw2, rh2 = ew - 2 * dx, eh - 2 * dy
                if rw2 >= GW and rh2 >= GH:
                    eval_stretch("stretch-c%d+%d" % (dx, dy),
                                 exx0 + dx, exy0 + dy, rw2, rh2)

    # -- integer scales that fit the 800x480 panel ---------------------------
    for s in (1, 2, 3):
        sw, sh = GW * s, GH * s
        rangex = bw - sw + 1
        rangey = bh - sh + 1
        if rangex <= 0 or rangey <= 0:
            continue
        stride = max(1, int(math.sqrt(rangex * rangey / 2500.0)) or 1)
        coarse = []
        for oy in range(0, rangey, stride):
            for ox in range(0, rangex, stride):
                r, _ = eval_scale(bx0 + ox, by0 + oy, s, CELLS_SUB, golden_sub)
                coarse.append((r, ox, oy))
        coarse.sort(key=lambda t: -abs(t[0]))          # |r|: inverted palettes too
        for r0, ox, oy in coarse[:8]:
            # refine at stride 1 within +-stride
            loc = (0.0, ox, oy)
            for dy in range(-stride, stride + 1):
                for dx in range(-stride, stride + 1):
                    nx, ny = ox + dx, oy + dy
                    if 0 <= nx < rangex and 0 <= ny < rangey:
                        r, _ = eval_scale(bx0 + nx, by0 + ny, s, CELLS_SUB, golden_sub)
                        if abs(r) > abs(loc[0]):
                            loc = (r, nx, ny)
            rf, _ = eval_scale(bx0 + loc[1], by0 + loc[2], s, CELLS_ALL, golden_all)
            if better(rf):
                got = sample_cells(gray, CELLS_ALL,
                                   bx0 + loc[1] + s // 2, by0 + loc[2] + s // 2, s, s)
                m = sum(got) / len(got)
                std = math.sqrt(sum((v - m) ** 2 for v in got) / len(got))
                best = (rf, "scale%d@+%d+%d" % (s, bx0 + loc[1], by0 + loc[2]), std)

    r, where, std = best if best else (0.0, None, 0.0)
    return {"pass": bool(abs(r) >= min_r and std >= min_std),
            "r": round(r, 4), "std": round(std, 2), "where": where,
            "bbox": [bx0, by0, bx1, by1]}


# ---------- temporal -----------------------------------------------------------

def temporal_check(base, t1, t2, min_frac=0.05, min_window=0.02):
    A = [i for i in range(W * H) if t1[i] != base[i]]
    if len(A) < min_window * W * H:
        return {"pass": False, "reason": "no window", "window_frac": round(len(A) / (W * H), 4),
                "move_frac": 0.0}
    moved = sum(1 for i in A if t2[i] != t1[i])
    frac = moved / len(A)
    return {"pass": bool(frac >= min_frac),
            "window_frac": round(len(A) / (W * H), 4), "move_frac": round(frac, 4)}


# ---------- synthetic fb helpers (selftest) ------------------------------------

def synth_desktop(seed=1):
    rnd = random.Random(seed)
    return [128 + (x * 7 + y * 3) % 24 + rnd.randint(-2, 2)
            for y in range(H) for x in range(W)]


def synth_window(screen_shades, x0, y0, s, palette=(255, 170, 85, 0), titlebar=True):
    """RGB565 framebuffer (as gray) with the golden screen pasted at integer
    scale s; optional 24px fake title bar above; letterbox background = 96."""
    fb = synth_desktop()
    top = y0 - 24 if titlebar else y0
    for y in range(max(0, top), min(H, y0 + GH * s)):
        for x in range(max(0, x0), min(W, x0 + GW * s)):
            fb[y * W + x] = 96
    if titlebar:
        for y in range(max(0, y0 - 24), min(H, y0)):
            for x in range(max(0, x0), min(W, x0 + GW * s)):
                fb[y * W + x] = 30 + (x // 40) % 3 * 60
    for j in range(GH):
        for i in range(GW):
            g = palette[screen_shades[j * GW + i]]
            for dy in range(s):
                for dx in range(s):
                    y, x = y0 + j * s + dy, x0 + i * s + dx
                    if 0 <= y < H and 0 <= x < W:
                        fb[y * W + x] = g
    return fb


def synth_stretch(screen_shades, x0, y0, rw, rh, palette=(255, 170, 85, 0)):
    fb = synth_desktop()
    for y in range(rh):
        for x in range(rw):
            i = (x * GW) // rw
            j = (y * GH) // rh
            fb[(y0 + y) * W + x0 + x] = palette[screen_shades[j * GW + i]]
    return fb


def to_raw(gray):
    """gray bytes -> RGB565 raw dump (gray replicated to channels)."""
    out = bytearray(W * H * 2)
    for i, g in enumerate(gray):
        r5 = g >> 3
        g6 = g >> 2
        b5 = g >> 3
        v = (r5 << 11) | (g6 << 5) | b5
        struct.pack_into("<H", out, i * 2, v)
    return bytes(out)


def golden_grays_from_shades(shades, palette=(255, 170, 85, 0)):
    return [palette[s] for s in shades]


def selftest(min_r=0.75):
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import mkchallenge as mk

    results = []

    def check(name, cond, info=""):
        results.append((name, bool(cond), info))
        print(("  %-42s %s  %s" % (name, "PASS" if cond else "FAIL", info)))

    seed = 42
    shades = mk.screen(seed)
    palette_default = (255, 170, 85, 0)
    golden = golden_grays_from_shades(shades)
    wrong = golden_grays_from_shades(mk.screen(43))

    print("match - honest renders must pass:")
    letterbox = synth_desktop()
    lb_shades = mk.screen(seed)
    for y in range(24, 456):                       # 640x432 centered in 800x480
        for x in range(80, 720):
            letterbox[y * W + x] = 60
    for y in range(432):
        srow = (y * GH // 432) * GW
        for x in range(640):
            letterbox[(24 + y) * W + 80 + x] = palette_default[lb_shades[srow + (x * GW // 640)]]
    for name, fb in [
        ("scale2 @+100,+60",            synth_window(shades, 100, 60, 2)),
        ("scale3 @+200,+30 inverted",   synth_window(shades, 200, 30, 3, palette=(0, 85, 170, 255))),
        ("scale3 @+40,+20 +titlebar",   synth_window(shades, 40, 20, 3)),
        ("scale1 @+300,+150",           synth_window(shades, 300, 150, 1, titlebar=False)),
        ("stretch 640x432 @+80,+24",    synth_stretch(shades, 80, 24, 640, 432)),
        ("letterboxed fullscreen",      letterbox),
    ]:
        res = best_match(fb, synth_desktop(), golden, min_r=min_r)
        check(name, res["pass"], f"r={res['r']} at {res['where']}")

    print("match - non-emulating submissions must fail:")
    rect = synth_desktop()
    for (rx, ry, rw2, rh2, g) in ((120, 100, 200, 120, 200), (340, 100, 200, 120, 60),
                                  (560, 100, 200, 120, 20)):
        for y in range(ry, ry + rh2):
            for x in range(rx, rx + rw2):
                rect[y * W + x] = g
    for name, fb in [
        ("three solid rectangles",      rect),
        ("titlebar + gray interior",    synth_window([0] * (GW * GH), 100, 60, 3)),
        ("wrong seed (43 vs 42)",       synth_window(mk.screen(43), 100, 60, 3)),
    ]:
        res = best_match(fb, synth_desktop(), golden, min_r=min_r)
        check(name, not res["pass"], f"r={res['r']}")

    print("temporal - honest scroll must pass, frozen frames must fail:")
    base = synth_desktop()
    t1 = synth_window(mk.screen(seed), 200, 80, 3)                 # demo frame k
    scrolled = bytearray(mk.screen(seed))
    scrolled[10 * GW:] = scrolled[: (GH - 10) * GW]                # shift rows
    t2 = synth_window(bytes(scrolled), 200, 80, 3)
    r = temporal_check(base, t1, t2)
    check("scrolling content", r["pass"], f"move_frac={r['move_frac']}")
    r = temporal_check(base, t1, t1)
    check("frozen frame", not r["pass"], f"move_frac={r['move_frac']}")

    clock = list(t1)
    for y in range(4, 12):                                          # tiny clock tick
        for x in range(700, 760):
            clock[y * W + x] ^= 0x10
    r = temporal_check(base, t1, clock)
    check("clock-tick only", not r["pass"], f"move_frac={r['move_frac']}")

    n_pass = sum(1 for _, ok, _ in results if ok)
    print(f"\nselftest: {n_pass}/{len(results)} checks pass "
          f"(threshold r>={min_r})")
    return n_pass == len(results)


# ---------- cli ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("match")
    m.add_argument("--fb", required=True)
    m.add_argument("--base", required=True)
    m.add_argument("--golden", required=True)
    m.add_argument("--min-r", type=float, default=0.75)

    t = sub.add_parser("temporal")
    t.add_argument("--base", required=True)
    t.add_argument("--t1", required=True)
    t.add_argument("--t2", required=True)
    t.add_argument("--min-frac", type=float, default=0.05)

    sub.add_parser("selftest")

    a = ap.parse_args()
    if a.cmd == "selftest":
        sys.exit(0 if selftest() else 1)
    if a.cmd == "match":
        res = best_match(load_raw(a.fb), load_raw(a.base), load_ppm(a.golden), a.min_r)
    else:
        res = temporal_check(load_raw(a.base), load_raw(a.t1), load_raw(a.t2), a.min_frac)
    print(json.dumps(res))
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""frame_check.py - normalized comparison of GB LCD frame dumps (P6 PPM).

Each image's palette is normalized to shade indices by luminance rank, so a
different choice of DMG greens/greys is fine — the *content* must match.

Usage:
  frame_check.py match A.ppm B.ppm   exit 0 iff same dims and >=98% of pixels
                                   map to the same shade index
  frame_check.py anim A.ppm B.ppm    exit 0 iff B differs from A on >=5% of
                                   pixels AND B has >=2 distinct shades AND
                                   B's modal shade covers <=99% (non-blank —
                                   demo.gb legitimately hits ~97% background
                                   at some scroll phases)

Diagnostics on stderr; verdict = exit code.
"""
import sys
from collections import Counter


def read_ppm(path):
    data = open(path, "rb").read()
    if not data.startswith(b"P6"):
        raise ValueError("not a P6 PPM")
    toks = []
    i = 2
    while len(toks) < 3:
        while i < len(data) and data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            while i < len(data) and data[i:i + 1] != b"\n":
                i += 1
            continue
        j = i
        while j < len(data) and not data[j:j + 1].isspace():
            j += 1
        toks.append(data[i:j])
        i = j
    i += 1
    w, h, mx = int(toks[0]), int(toks[1]), int(toks[2])
    if mx != 255:
        raise ValueError("maxval != 255")
    px = data[i:i + w * h * 3]
    if len(px) != w * h * 3:
        raise ValueError("truncated pixel data")
    return w, h, [px[k:k + 3] for k in range(0, len(px), 3)]


def shades(px):
    order = sorted(set(px), key=lambda c: c[0] * 299 + c[1] * 587 + c[2] * 114)
    lut = {c: i for i, c in enumerate(order)}
    return [lut[c] for c in px], len(order)


def main():
    mode, pa, pb = sys.argv[1], sys.argv[2], sys.argv[3]
    wa, ha, xa = read_ppm(pa)
    wb, hb, xb = read_ppm(pb)
    if (wa, ha) != (wb, hb):
        print(f"frame_check: dims differ {wa}x{ha} vs {wb}x{hb}", file=sys.stderr)
        return 1
    sa, ca = shades(xa)
    sb, cb = shades(xb)
    n = len(sa)
    same = sum(1 for i in range(n) if sa[i] == sb[i])
    frac_same = same / n
    frac_diff = 1.0 - frac_same
    modal_b = Counter(sb).most_common(1)[0][1] / n

    if mode == "match":
        print(f"frame_check match: {frac_same:.4f} same, shades a={ca} b={cb}",
              file=sys.stderr)
        return 0 if frac_same >= 0.98 else 1
    if mode == "anim":
        ok = frac_diff >= 0.05 and cb >= 2 and modal_b <= 0.99
        print(f"frame_check anim: {frac_diff:.4f} differ, shades b={cb}, "
              f"modal_b={modal_b:.3f}", file=sys.stderr)
        return 0 if ok else 1
    print(f"frame_check: unknown mode {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""mkchallenge.py - generate a per-run challenge DMG ROM whose screen can only
be produced by actually executing the ROM's CPU.

Why: the old renders_content check (">2% pixels changed, >=3 colors") is
passed by any window with a title bar. This ROM closes that hole:

  * tile patterns and the tilemap do NOT exist in the ROM image - the code
    computes them at runtime from a seed-dependent PRNG (b = 41*b + inc,
    inc = 2*seed+1; second plane byte = rot3 of the next output). Blitting
    ROM contents cannot reproduce the screen; only executing ~30 distinct
    opcodes can.
  * the pattern is high-entropy and seed-dependent, so a canned frame for
    one variant is worthless for the next run's variant.
  * a 4-byte serial signature (XOR checksum of the computed tiles) is
    emitted on startup, killing printf-style canned "Passed" output in
    headless mode the same way.

Ground truth is double-derived: this file contains an independent Python
model of the expected screen, and the verifier additionally renders the
ROM with the trusted reference emulator (tests/ref/). Both must agree
byte-for-byte or the verifier refuses to score (instrument-validity guard).

Hand-assembled LR35902 in the style of dmg810's mkdemo.py / mkbench.py.
No toolchain needed.
"""
import argparse
import struct

LOGO = bytes([
 0xCE,0xED,0x66,0x66,0xCC,0x0D,0x00,0x0B,0x03,0x73,0x00,0x83,0x00,0x0C,0x00,0x0D,
 0x00,0x08,0x11,0x1F,0x88,0x89,0x00,0x0E,0xDC,0xCC,0x6E,0xE6,0xDD,0xDD,0xD9,0x99,
 0xBB,0xBB,0x67,0x63,0x6E,0x0E,0xEC,0xCC,0xDD,0xDC,0x99,0x9F,0xBB,0xB9,0x33,0x3E])

def gen_macro(inc):
    # registers while generating: B = PRNG state, result in A
    # advances b: b = b*41 + inc (mod 256)
    #   a=b; a<<=5 -> e; a=b; a<<=3; a+=e; a+=b; a+=inc; b=a
    # inc is the SEED (odd, = 2*seed+1): the increment -- not the initial
    # state -- is what varies per run. A full-period LCG seeded by initial
    # state yields one universal sequence rotated (same tiles for every
    # seed); varying the increment yields genuinely different sequences.
    return bytes([0x78, 0x87, 0x87, 0x87, 0x87, 0x87,   # ld a,b; add a,a x5
                  0x5F,                                # ld e,a
                  0x78, 0x87, 0x87, 0x87,              # ld a,b; add a,a x3
                  0x83,                                # add a,e
                  0x80,                                # add a,b
                  0xC6, inc & 0xFF,                    # add a,INC
                  0x47])                               # ld b,a

def build_rom(seed):
    assert 0 <= seed <= 255
    inc = (2 * seed + 1) & 0xFF        # odd increment -> full period 256
    GEN = gen_macro(inc)
    rom = bytearray(0x8000)
    rom[0x100] = 0x00; rom[0x101] = 0xC3; rom[0x102] = 0x50; rom[0x103] = 0x01
    rom[0x104:0x104+48] = LOGO
    rom[0x134:0x134+10] = b"CHALLENGE!"
    rom[0x147] = 0x00; rom[0x148] = 0x00; rom[0x149] = 0x00
    rom[0x14A] = 0x01; rom[0x14B] = 0x33; rom[0x14C] = 0x00

    out = []; labels = {}; patches = []
    BASE = 0x150
    def L(n): labels[n] = len(out)
    def B(*bs):
        for b in bs: out.append(b & 0xFF)
    def JR(cond, target):           # cond 0x18/0x20/0x28
        B(cond, 0x00); patches.append((len(out)-1, target))
    def addr(lbl): return BASE + labels[lbl]

    # --- init ---
    B(0xAF)                    # xor a
    B(0xE0, 0x0F)              # ldh (IF),a
    B(0xE0, 0x40)              # ldh (LCDC),a  - LCD off while filling VRAM
    B(0x31, 0xFE, 0xFF)        # ld sp,0xfffe
    B(0x06, seed)              # ld b,SEED     - PRNG state; the seed also
                               #                 enters via inc (2*seed+1):
                               #                 state contributes 41^n*seed
                               #                 (odd coeff) -> full 8-bit
                               #                 sensitivity, not 7

    # --- tiles: 16 tiles x 8 rows x 2 planes at 0x8000 (256 bytes) ---
    B(0x21, 0x00, 0x80)        # ld hl,0x8000
    B(0x0E, 16)                # ld c,16       - tiles remaining
    L("tileloop")
    B(0x16, 8)                 # ld d,8        - rows remaining
    L("rowloop")
    out.extend(GEN)            # plane0 byte = gen()
    B(0x22)                    # ld (hl+),a
    out.extend(GEN)            # advance PRNG again...
    B(0x07, 0x07, 0x07)        # rlca x3 == rot3(a)
    B(0x22)                    # ld (hl+),a    - plane1 byte = rot3(gen())
    B(0x15)                    # dec d
    JR(0x20, "rowloop")
    B(0x0D)                    # dec c
    JR(0x20, "tileloop")

    # --- tilemap: 1024 entries, idx = gen() & 0x0F ---
    # NOTE: termination compares HL against 0x9C00 (0x9800+1024) because GEN
    # clobbers E -- DE cannot hold the loop counter.
    B(0x21, 0x00, 0x98)        # ld hl,0x9800
    L("maploop")
    out.extend(GEN)
    B(0xE6, 0x0F)              # and a,0x0F
    B(0x22)                    # ld (hl+),a
    B(0x7C)                    # ld a,h
    B(0xFE, 0x9C)              # cp 0x9C
    JR(0x20, "maploop")
    B(0x7D)                    # ld a,l
    B(0xFE, 0x00)              # cp 0
    JR(0x20, "maploop")

    # --- one OBJ sprite over the background ---
    # An emulator that never implements sprites still renders the BG frame
    # perfectly — so the golden MUST contain one. Sprite 0 at OAM[0]:
    # screen (72,48), tile 5 (already computed above), no priority/flip.
    # DMG rule, attr=0: non-zero sprite pixels always cover the BG.
    B(0x3E, 0x40, 0xEA, 0x00, 0xFE)  # ld a,64;  ld (0xFE00),a   ; OAM y
    B(0x3E, 0x50, 0xEA, 0x01, 0xFE)  # ld a,80;  ld (0xFE01),a   ; OAM x
    B(0x3E, 0x05, 0xEA, 0x02, 0xFE)  # ld a,5;   ld (0xFE02),a   ; tile idx
    B(0xAF,       0xEA, 0x03, 0xFE)  # xor a;    ld (0xFE03),a   ; attr=0
    B(0x3E, 0xE4, 0xE0, 0x48)        # obp0=0xE4 (identity mapping)

    # --- display on ---
    B(0x3E, 0xE4, 0xE0, 0x47)  # bgp=0xE4 (identity mapping)
    B(0xAF, 0xE0, 0x42)        # scy=0
    B(0xE0, 0x43)              # scx=0
    B(0x3E, 0x93, 0xE0, 0x40)  # lcdc=0x93 (LCD+BG+OBJ 8x8 on)

    # --- serial signature: 'C', g1, ~g1, g2, ~g2, 'K' ---
    # g1/g2 are the next two PRNG outputs after the 1280 consumed by the
    # fill (tiles 256 + map 1024). NOT a checksum: every byte this ROM
    # computes is an affine function of the seed mod 256, and any
    # additive/xor checksum over an affine stream proved seed-degenerate
    # (empirically constant). Two consecutive raw outputs jointly carry
    # the increment and cannot be produced without executing the code.
    # One byte per vblank (real DMG serial takes 4096 cycles per byte).
    out.extend(GEN)            # g1 -> A
    B(0x4F)                    # ld c,a
    out.extend(GEN)            # g2 -> A
    B(0x57)                    # ld d,a
    sig_bytes = [
        (0x43, bytes([0x3E, 0x43])),                 # 'C' imm
        (None, bytes([0x79])),                       # ld a,c
        (None, bytes([0x79, 0xEE, 0xFF])),           # ld a,c; xor ~
        (None, bytes([0x7A])),                       # ld a,d
        (None, bytes([0x7A, 0xEE, 0xFF])),           # ld a,d; xor ~
        (0x4B, bytes([0x3E, 0x4B])),                 # 'K' imm
    ]
    for n, (val, load) in enumerate(sig_bytes):
        out.extend(load)
        B(0xE0, 0x01)                              # ldh (SB),a
        B(0x3E, 0x81, 0xE0, 0x02)                  # ld a,0x81; ldh (SC),a
        L(f"vb{n}")
        B(0xF0, 0x44, 0xFE, 0x90)                  # ldh a,(LY); cp 144
        JR(0x20, f"vb{n}")                         # wait for vblank

    # --- freeze (static screen from here) ---
    B(0x18, 0xFE)              # jr $

    code = bytearray(out)
    for pos, target in patches:
        t = addr(target); pc_next = BASE + pos + 1
        off = t - pc_next
        assert -128 <= off <= 127, (target, off)
        code[pos] = off & 0xFF
    assert BASE + len(code) < 0x0F00, len(code)
    rom[BASE:BASE+len(code)] = code

    # header checksums
    chk = 0
    for a in range(0x134, 0x14D): chk = (chk - rom[a] - 1) & 0xFF
    rom[0x14D] = chk
    gs = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E] = gs >> 8; rom[0x14F] = gs & 0xFF
    return bytes(rom)


# ---- independent Python model of what the ROM must produce ------------------

def _gen(state):
    return None  # replaced below; kept for readability of the mirror

def stream(seed, n=1282):
    """Raw PRNG outputs the ROM consumes: 256 for tiles, 1024 for the map,
    then the two signature bytes g1, g2."""
    inc = (2 * seed + 1) & 0xFF
    st = seed                      # state AND increment both carry the seed
    out = []
    for _ in range(n):
        st = (st * 41 + inc) & 0xFF
        out.append(st)
    return out

def model(seed):
    """Mirror of the ROM's computation. Returns (tiles, tilemap, signature)."""
    def rot3(v):
        return ((v << 3) | (v >> 5)) & 0xFF
    s = stream(seed, 1282)
    tiles = []
    for i in range(256):
        v = s[i]
        tiles.append(v if i % 2 == 0 else rot3(v))
    tilemap = [v & 0x0F for v in s[256:1280]]
    g1, g2 = s[1280], s[1281]
    sig = bytes([0x43, g1, g1 ^ 0xFF, g2, g2 ^ 0xFF, 0x4B])
    return tiles, tilemap, sig

def screen(seed, w=160, h=144):
    """Expected framebuffer: shade 0..3 per pixel (BGP=OBP0=0xE4 -> identity).
    Includes the OAM sprite: tile 5 at screen (72,48), attr 0 — non-zero
    sprite pixels cover the BG (OBP0 identity, so sprite keeps its color)."""
    tiles, tilemap, _ = model(seed)
    px = bytearray(w * h)
    for y in range(h):
        trow = tilemap[(y // 8) * 32:(y // 8) * 32 + 32]
        for x in range(w):
            t = trow[x // 8]
            bit = 7 - (x % 8)
            b0 = tiles[t * 16 + (y % 8) * 2]
            b1 = tiles[t * 16 + (y % 8) * 2 + 1]
            px[y * w + x] = (((b1 >> bit) & 1) << 1) | ((b0 >> bit) & 1)
    # sprite overlay: tile 5, 8x8, at screen (72,48)
    for row in range(8):
        b0 = tiles[5 * 16 + row * 2]
        b1 = tiles[5 * 16 + row * 2 + 1]
        for col in range(8):
            bit = 7 - col
            c = (((b1 >> bit) & 1) << 1) | ((b0 >> bit) & 1)
            if c:
                px[(48 + row) * w + 72 + col] = c
    return px

def golden_ppm(seed):
    """P6 PPM using the same gray palette as the reference emulator's
    plat_headless.c, so the two can be compared byte-for-byte."""
    pal = bytes([0xFF, 0xFF, 0xFF, 0xAA, 0xAA, 0xAA, 0x55, 0x55, 0x55, 0x00, 0x00, 0x00])
    px = screen(seed)
    out = bytearray(b"P6\n160 144\n255\n")
    for s in px:
        out += pal[s * 3:s * 3 + 3]
    return bytes(out)

def signature(seed):
    _, _, sig = model(seed)
    return sig


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--rom", required=True)
    ap.add_argument("--golden", help="write expected-frame PPM here")
    ap.add_argument("--serial", help="write expected signature bytes here")
    a = ap.parse_args()
    open(a.rom, "wb").write(build_rom(a.seed))
    if a.golden: open(a.golden, "wb").write(golden_ppm(a.seed))
    if a.serial: open(a.serial, "wb").write(signature(a.seed))
    print(f"wrote {a.rom} (seed={a.seed})")

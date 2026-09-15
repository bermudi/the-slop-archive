#!/usr/bin/env python3
"""mkbench.py v2 — generate the bench.gb fixed-workload ROM family.

v1's tick was a constant '*'. Any binary that printed '*' on a timer scored
full fps without emulating a single instruction. v2 binds every tick to
emulated state instead:

    byte_n = LCG_n(seed) XOR DIV_at_vblank_n

* LCG_n — b = 41*b + (2*seed+1), advanced once per frame (same generator
  mkchallenge.py proved full-period). Content binding: the byte can only
  be produced by executing the ROM's own code, and the seed (hence the
  stream) is fresh per scoring run.
* DIV (FF04, 16384 Hz) read at a fixed point just after vblank detection.
  Timing binding: DIV advances 274.3125 counts per 70224-cycle frame, so
  the byte stream is pinned to real frame length. Shortening the emulated
  frame (the "2x PPU" cheat) changes DIV's progression and the stream
  diverges from golden within ~2 frames.

Scoring counts the longest prefix of the run's serial output that matches
the golden stream from the trusted reference core (tests/ref), tolerant to
+-TOL on the DIV-derived component (TOL=4 == +-1024 T-cycles: absorbs
instruction-batching jitter in legitimately optimized builds while still
rejecting any persistent frame-length error > ~0.3%, which accumulates).

The public dev variant is seed 0 (environment/roms/bench.gb). Scoring uses
private seeds generated per run. This file lives in tests/ (verifier-side):
agents see the ROM, not the generator.

Per-frame workload is unchanged from v1 (scroll + 40 sprites + OAM/VRAM
writes + joypad read) plus the LCG and DIV work, so baseline anchors stay
comparable.
"""
import argparse

LOGO = bytes([
 0xCE,0xED,0x66,0x66,0xCC,0x0D,0x00,0x0B,0x03,0x73,0x00,0x83,0x00,0x0C,0x00,0x0D,
 0x00,0x08,0x11,0x1F,0x88,0x89,0x00,0x0E,0xDC,0xCC,0x6E,0xE6,0xDD,0xDD,0xD9,0x99,
 0xBB,0xBB,0x67,0x63,0x6E,0x0E,0xEC,0xCC,0xDD,0xDC,0x99,0x9F,0xBB,0xB9,0x33,0x3E])

def gen_macro(inc):
    # b = b*41 + inc (mod 256). Result in A, state in B. Uses A/B/E only.
    return bytes([0x78, 0x87, 0x87, 0x87, 0x87, 0x87,   # ld a,b; add a,a x5
                  0x5F,                                 # ld e,a
                  0x78, 0x87, 0x87, 0x87,               # ld a,b; add a,a x3
                  0x83,                                 # add a,e
                  0x80,                                 # add a,b
                  0xC6, inc & 0xFF,                     # add a,INC
                  0x47])                                # ld b,a

def build(seed):
    assert 0 <= seed <= 255
    inc = (2 * seed + 1) & 0xFF
    GEN = gen_macro(inc)
    rate = 1 + (seed % 7)            # seeded scroll speed 1..7 px/frame
    y0 = (seed * 5) % 128
    x0 = (seed * 11) % 152
    m0 = ((seed * 3) + 1) & 0xFF     # tile0 plane xor bytes
    m1 = ((seed * 7) + 3) & 0xFF

    rom = bytearray(0x8000)
    rom[0x100] = 0x00; rom[0x101] = 0xC3; rom[0x102] = 0x50; rom[0x103] = 0x01
    rom[0x104:0x104+48] = LOGO
    rom[0x134:0x134+10] = b"BENCH42" + bytes([0x21 + (seed % 90)]) + b"\0\0"
    rom[0x147] = 0x00; rom[0x148] = 0x00; rom[0x149] = 0x00
    rom[0x14A] = 0x01; rom[0x14B] = 0x33; rom[0x14C] = 0x00

    out = []; labels = {}; patches = []
    BASE = 0x150
    def L(n): labels[n] = len(out)
    def B(*bs):
        for b in bs: out.append(b & 0xFF)
    def JR(cond, target):
        B(cond, 0x00); patches.append((len(out)-1, target))
    def addr(lbl): return BASE + labels[lbl]

    # --- init ---
    B(0xAF)                    # xor a
    B(0xE0, 0x0F)              # ldh (IF),a
    B(0xE0, 0x40)              # ldh (LCDC),a — LCD off while filling OAM
    B(0x31, 0xFE, 0xFF)        # ld sp,0xfffe
    # (LCG state B is loaded AFTER the fill loops below — they use B as a
    # counter and would destroy the seed. Model mirrors: first tick byte is
    # LCG^1(seed).)
    # copy 32 bytes tile data 0x600 -> 0x8000 (0x300 would collide with code)
    B(0x21, 0x00, 0x06); B(0x11, 0x00, 0x80); B(0x01, 0x20, 0x00)
    L("cp")
    B(0x2A, 0x12, 0x13, 0x0B, 0x78, 0xB1)
    JR(0x20, "cp")
    # fill bg map 0x9800 with alternating tiles 0/1
    B(0x21, 0x00, 0x98); B(0x06, 0x04)
    L("o")
    B(0x0E, 0x00); B(0xAF)
    L("i")
    B(0x22, 0x3C, 0xE6, 0x01, 0x0D)
    JR(0x20, "i")
    B(0x05)
    JR(0x20, "o")
    # fill OAM: 40 sprites, seeded offsets (workload identical to v1)
    for i in range(40):
        y = 16 + (y0 + i * 3) % 128
        x = 8 + (x0 + i * 4) % 152
        oam = 0xFE00 + i * 4
        B(0x3E, y); B(0xEA, oam & 0xFF, oam >> 8)
        B(0x3E, x); B(0xEA, (oam+1) & 0xFF, (oam+1) >> 8)
        B(0x3E, 1); B(0xEA, (oam+2) & 0xFF, (oam+2) >> 8)
        B(0xAF);    B(0xEA, (oam+3) & 0xFF, (oam+3) >> 8)
    B(0x3E, 0xE4, 0xE0, 0x47)  # bgp = 0xE4 (identity)
    B(0xAF, 0xE0, 0x42)        # scy = 0
    B(0x3E, (seed * 37) & 0xFF, 0xE0, 0x43)  # scx = seeded start phase
    B(0x3E, 0x93, 0xE0, 0x40)  # lcdc: on + sprites
    B(0x06, seed)              # ld b,SEED — LCG state; nothing after this
                               # touches B, so it survives into the frame loop

    # --- per-frame loop ---
    L("frame")
    B(0xF0, 0x44, 0xFE, 0x90)  # ldh a,(LY); cp 144
    JR(0x20, "frame")          # wait for vblank
    # tick byte = LCG(seed) XOR DIV-at-vblank
    out.extend(GEN)            # A = LCG_n, state stays in B
    B(0x4F)                    # ld c,a
    B(0xF0, 0x04)              # ldh a,(DIV)
    B(0xA9)                    # xor c
    B(0xE0, 0x01)              # ldh (SB),a
    B(0x3E, 0x81)              # ld a,0x81
    B(0xE0, 0x02)              # ldh (SC),a — start transfer
    # frame tile at map[0]: visual per-frame counter (LCG & 7)
    B(0x78)                    # ld a,b
    B(0xE6, 0x07)              # and 7
    B(0xEA, 0x00, 0x98)        # ld (0x9800),a — VRAM write during vblank
    # scroll
    B(0xF0, 0x43)              # ldh a,(SCX)
    B(0xC6, rate)              # add a,RATE
    B(0xE0, 0x43)              # ldh (SCX),a
    # keep joypad + OAM-write paths warm (same as v1)
    B(0xF0, 0x00)              # ldh a,(P1)
    B(0xFA, 0x01, 0xFE)        # ld a,(0xFE01)
    B(0x3C)                    # inc a
    B(0xEA, 0x01, 0xFE)        # ld (0xFE01),a — oam[0].x++
    # wait for vblank end, then next frame
    L("vend")
    B(0xF0, 0x44, 0xFE, 0x90)  # ldh a,(LY); cp 144
    JR(0x28, "vend")           # jr Z -> still 144, keep waiting
    JR(0x18, "frame")

    code = bytearray(out)
    for pos, target in patches:
        t = addr(target); pc_next = BASE + pos + 1
        off = t - pc_next
        assert -128 <= off <= 127, (target, off)
        code[pos] = off & 0xFF
    assert BASE + len(code) < 0x600, len(code)
    rom[BASE:BASE+len(code)] = code

    # tile 0: seeded 2px horizontal-ish stripes (scroll makes them march)
    for r in range(8):
        rom[0x600 + r*2]     = (0xAA if r % 2 == 0 else 0x55) ^ m0
        rom[0x600 + r*2 + 1] = (0xAA if r % 2 == 0 else 0x55) ^ m1
    # tile 1: sprite — single diagonal column bit
    for r in range(8):
        rom[0x610 + r*2]     = (1 << (7 - r)) & 0xFF
        rom[0x610 + r*2 + 1] = (1 << (7 - r)) & 0xFF

    chk = 0
    for a in range(0x134, 0x14D): chk = (chk - rom[a] - 1) & 0xFF
    rom[0x14D] = chk
    gs = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E] = gs >> 8; rom[0x14F] = gs & 0xFF
    return bytes(rom)


# ---- independent Python model of the content component ----------------------

def lcg_stream(seed, n):
    """LCG bytes L_0..L_{n-1} as emitted by the per-frame GEN macro."""
    inc = (2 * seed + 1) & 0xFF
    st = seed
    out = bytearray()
    for _ in range(n):
        st = (st * 41 + inc) & 0xFF
        out.append(st)
    return bytes(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("-o", "--rom", default="bench.gb")
    ap.add_argument("--lcg", help="write expected LCG byte stream here")
    ap.add_argument("--frames", type=int, default=4096,
                    help="length of the LCG stream to emit (>= scored frames)")
    a = ap.parse_args()
    open(a.rom, "wb").write(build(a.seed))
    if a.lcg:
        open(a.lcg, "wb").write(lcg_stream(a.seed, a.frames))
    print(f"wrote {a.rom} (seed={a.seed}, rate={1 + a.seed % 7})")

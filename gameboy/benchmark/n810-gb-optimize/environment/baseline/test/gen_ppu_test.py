#!/usr/bin/env python3
"""Generate ppu_test.gb: PPU verification ROM (BG / window / sprite).

Programs the PPU directly, then parks in a halt loop. The headless
screenshot (frame 5) must show, against the gray palette
(0=white .. 3=black):

  - tile 1 at BG map (0,0) and (1,0): visible at ly=0, x=0..15
    (px0=shade3, px1=shade1, px7=shade0)
  - tile 1 at BG map (3,2) (0x9843): sits behind the window at
    ly=16..23, x=24..31 (WX=7 covers the full line), and its px0
    would peek out at (24,24) if the window were not overdrawn there
  - window tilemap entry (3,0) (0x9803) = tile 1: window row 0 shows
    it at x=24..31; window row 0 col 0 shares 0x9800 = tile 1, so
    (0,16) is shade3 only if the window really renders
  - one sprite (OAM 0: sy=40 sx=24 tile=1 attr=0) at screen (16,24)

Expected shades are asserted by test/verify_ppu_test.py.

Assembled by emitting raw opcode bytes, same style as gen_conformance.py.

NOTE: tile 1 rows are lo=0xC0, hi=0x80. Pan Docs bitplanes are MSB-first
(lo = low plane, hi = high plane), so hi=0x80 (not 0x40) is what makes
pixel x0 = color 3 and x1 = color 1; 0xC0/0x40 would decode to
x0=1, x1=3 and contradict the assertion list.
"""
rom = bytearray(b'\x00' * 0x8000)
code = bytearray()
fixups = []          # (pos_in_code, target_label)
labels = {}

def emit(*bs):
    for b in bs:
        code.append(b & 0xFF)

def word(v):
    return [v & 0xFF, (v >> 8) & 0xFF]

def label(name):
    labels[name] = len(code)

def jmp(op, name):
    fixups.append((len(code) + 1, name))
    if op in (0x18, 0x20, 0x28, 0x30, 0x38):
        emit(op, 0)                          # jr: ONE signed operand byte
    else:
        emit(op, 0, 0)

# --- entry ---
emit(0x00)                       # nop @0100
fixups.append((len(code) + 1, 'main')); emit(0xC3)  # jp main
emit(0x00, 0x00)
emit(0x00, 0x00)

# ---- main -------------------------------------------------------------
label('main')
emit(0xF3)                                   # di
emit(0x3E, 0x00); emit(0xE0, 0x40)           # ld a,0 ; ldh (40),a  LCD off
emit(0x3E, 0xE4); emit(0xE0, 0x47)           # ld a,$E4 ; ldh (47),a  BGP
emit(0x3E, 0xE4); emit(0xE0, 0x48)           # ld a,$E4 ; ldh (48),a  OBP0

# tile 1 at 0x8010: 8 rows of lo=0xC0, hi=0x80 (px0=col3, px1=col1, px2-7=col0)
emit(0x21); emit(*word(0x8010))              # ld hl,$8010
for _ in range(8):
    emit(0x3E, 0xC0); emit(0x22)             # ld a,$C0 ; ld (hl+),a
    emit(0x3E, 0x80); emit(0x22)             # ld a,$80 ; ld (hl+),a

# BG tilemap 0x9800: tile 1 at (0,0), (1,0) and (3,2) [= 0x9800 + 2*32 + 3]
emit(0x21); emit(*word(0x9800)); emit(0x36, 0x01)   # ld hl,$9800 ; ld (hl),1
emit(0x21); emit(*word(0x9801)); emit(0x36, 0x01)
emit(0x21); emit(*word(0x9800 + 2 * 32 + 3)); emit(0x36, 0x01)

# window tilemap 0x9800: tile 1 at (3,0)
emit(0x21); emit(*word(0x9803)); emit(0x36, 0x01)

# WY (FF4A) = 0x10, WX (FF4B) = 0x07 (window at x>=0 from ly=16 down)
emit(0x3E, 0x10); emit(0xE0, 0x4A)           # ld a,$10 ; ldh (4A),a
emit(0x3E, 0x07); emit(0xE0, 0x4B)           # ld a,$07 ; ldh (4B),a

# OAM FE00: sy=40, sx=24, tile=1, attr=0 (screen position 16,24)
emit(0x21); emit(*word(0xFE00))              # ld hl,$FE00
emit(0x36, 40); emit(0x2C)                   # ld (hl),40 ; inc l
emit(0x36, 24); emit(0x2C)                   # ld (hl),24 ; inc l
emit(0x36, 0x01); emit(0x2C)                 # ld (hl),1  ; inc l
emit(0x36, 0x00)                             # ld (hl),0  (attr)

# LCD on: LCDC (FF40) = 0xB3 = 1011 0011
#   LCD on, BG on, OBJ on, OBJ 8x8, BG+window tile data $8000,
#   BG map $9800, window on, window map $9800
emit(0x3E, 0xB3); emit(0xE0, 0x40)           # ld a,$B3 ; ldh (40),a

label('halt')
emit(0x18, 0xFE)                             # jr -2

# ---- place code into rom at 0x0150 ----
start = 0x0150
rom[start:start + len(code)] = code
for pos, tgt in fixups:
    addr = start + labels[tgt]
    rel = addr - (start + pos + 1)
    if rom[start + pos - 1] in (0x18, 0x20, 0x28, 0x30, 0x38):
        rom[start + pos] = rel & 0xFF          # jr operand sits AT pos
    else:
        rom[start + pos:start + pos + 2] = word(addr)

rom[0x0100] = 0x00
rom[0x0101:0x0104] = bytes([0xC3, 0x50, 0x01])
rom[0x0147] = 0x00                           # ROM only
open('test/roms/ppu_test.gb', 'wb').write(bytes(rom))
print(f"built ppu_test.gb: {len(code)} bytes of code @0x0150, 32KB ROM-only")

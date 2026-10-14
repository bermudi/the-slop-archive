#!/usr/bin/env python3
"""mkachallenge.py - per-run AUDIO challenge ROM: plays a seed-dependent
sequence of pulse tones on channel 1. The only way to produce the right
sound is to emulate the APU; a canned WAV or silence fails the spectral
check, and the tone order/frequencies change every run.

Layout: 4 tones x (30 frames on / 10 frames gap) from a fixed table of 8
frequencies (2048-divider family, all safely above the APU's own lowpass).
The generator also emits the expected tone schedule as JSON so the
verifier's Goertzel check knows exactly when each tone sounds.

Ground truth is double-derived like the video challenge: the vendored
reference core's APU (tests/ref/plat_wav.c) must itself pass the same
spectral check on the same ROM or the rung is refused as invalid
instrument.

Hand-assembled LR35902. No toolchain needed.
"""
import argparse
import json
import struct

LOGO = bytes([
 0xCE,0xED,0x66,0x66,0xCC,0x0D,0x00,0x0B,0x03,0x73,0x00,0x83,0x00,0x0C,0x00,0x0D,
 0x00,0x08,0x11,0x1F,0x88,0x89,0x00,0x0E,0xDC,0xCC,0x6E,0xE6,0xDD,0xDD,0xD9,0x99,
 0xBB,0xBB,0x67,0x63,0x6E,0x0E,0xEC,0xCC,0xDD,0xDC,0x99,0x9F,0xBB,0xB9,0x33,0x3E])

GB_FPS = 59.7275
ON_FRAMES = 30
GAP_FRAMES = 10
N_TONES = 4

# 8 candidate fundamental frequencies (Hz), ~a minor third or more apart so
# a Goertzel check at these exact values discriminates cleanly.
FREQS = [220.0, 277.0, 349.0, 440.0, 554.0, 698.0, 880.0, 1109.0]

def freq_reg(hz):
    """DMG pulse/wave freq register: f_hz = 131072 / (2048 - reg)."""
    return 2048 - round(131072.0 / hz)

def build_rom(seed, tones_hz):
    assert 0 <= seed <= 255
    rom = bytearray(0x8000)
    rom[0x100] = 0x00; rom[0x101] = 0xC3; rom[0x102] = 0x50; rom[0x103] = 0x01
    rom[0x104:0x104+48] = LOGO
    rom[0x134:0x134+10] = b"ACHALLENGE"
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
    B(0xE0, 0xFF)              # ldh (IE),a   — IE at 0xFFFF, interrupts off
    B(0x31, 0xFE, 0xFF)        # ld sp,0xfffe
    B(0x3E, 0x91, 0xE0, 0x40)  # lcdc=0x91 (LCD+BG on; BG all tile0 = white)

    # --- APU bring-up: power on, master vol, route ch1 -> both outputs ---
    B(0x3E, 0x80, 0xE0, 0x26)  # NR52 = 0x80 (power on)
    B(0x3E, 0x77, 0xE0, 0x24)  # NR50 = 0x77 (max output level)
    B(0x3E, 0x11, 0xE0, 0x25)  # NR51 = 0x11 (ch1 -> left+right)

    for k, hz in enumerate(tones_hz):
        reg = freq_reg(hz)
        # ch1: 50% duty, vol 15 no envelope, trigger
        B(0x3E, 0x80, 0xE0, 0x11)          # NR11 duty 50%, len off
        B(0x3E, 0xF0, 0xE0, 0x12)          # NR12 vol=15, env off
        B(0x3E, reg & 0xFF, 0xE0, 0x13)    # NR13 freq lo
        B(0x3E, 0x80 | (reg >> 8), 0xE0, 0x14)  # NR14 trigger + hi
        # hold ON_FRAMES vblanks
        B(0x06, ON_FRAMES)                 # ld b,ON_FRAMES
        L(f"wa{k}")
        B(0xF0, 0x44, 0xFE, 0x90)          # ldh a,(LY); cp 144
        JR(0x20, f"wa{k}")                 # wait for vblank
        L(f"wb{k}")
        B(0xF0, 0x44, 0xFE, 0x90)
        JR(0x28, f"wb{k}")                 # wait for vblank end
        B(0x05)                            # dec b
        JR(0x20, f"wa{k}")
        # silence
        B(0xAF, 0xE0, 0x12)                # NR12 = 0 (DAC off)
        B(0x06, GAP_FRAMES)                # ld b,GAP_FRAMES
        L(f"ga{k}")
        B(0xF0, 0x44, 0xFE, 0x90)
        JR(0x20, f"ga{k}")
        L(f"gb{k}")
        B(0xF0, 0x44, 0xFE, 0x90)
        JR(0x28, f"gb{k}")
        B(0x05)
        JR(0x20, f"ga{k}")

    B(0x18, 0xFE)              # jr $ — done, silence forever

    code = bytearray(out)
    for pos, target in patches:
        t = addr(target); pc_next = BASE + pos + 1
        off = t - pc_next
        assert -128 <= off <= 127, (target, off)
        code[pos] = off & 0xFF
    assert BASE + len(code) < 0x0F00, len(code)
    rom[BASE:BASE+len(code)] = code

    chk = 0
    for a in range(0x134, 0x14D): chk = (chk - rom[a] - 1) & 0xFF
    rom[0x14D] = chk
    gs = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E] = gs >> 8; rom[0x14F] = gs & 0xFF
    return bytes(rom)

def schedule(seed):
    """Deterministic tone picks from the seed; returns (hz list, spec)."""
    tones_hz = [FREQS[(seed * 7 + k * 3 + (seed >> 4)) & 7] for k in range(N_TONES)]
    tones = []
    for k, hz in enumerate(tones_hz):
        t0 = k * (ON_FRAMES + GAP_FRAMES) / GB_FPS
        t1 = t0 + ON_FRAMES / GB_FPS
        tones.append({"hz": hz, "on": round(t0, 4), "off": round(t1, 4)})
    spec = {"rate": 44100, "n_frames": N_TONES * (ON_FRAMES + GAP_FRAMES),
            "all_hz": FREQS, "tones": tones, "seed": seed}
    return tones_hz, spec

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--rom", required=True)
    ap.add_argument("--tones", help="write expected tone schedule JSON here")
    a = ap.parse_args()
    tones_hz, spec = schedule(a.seed)
    open(a.rom, "wb").write(build_rom(a.seed, tones_hz))
    if a.tones:
        open(a.tones, "w").write(json.dumps(spec, indent=2))
    print(f"wrote {a.rom} (seed={a.seed}, tones={tones_hz})")

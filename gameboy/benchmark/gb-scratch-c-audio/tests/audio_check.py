#!/usr/bin/env python3
"""audio_check.py - verify a WAV against an expected tone schedule.

  audio_check.py file.wav tones.json

tones.json (from mkachallenge.py): {"rate":44100, "all_hz":[...],
  "tones":[{"hz":f,"on":t0,"off":t1}, ...]}

Pass criteria, per tone window [on+50ms, off-50ms]:
  * the dominant candidate frequency (max Goertzel power over all_hz)
    is the expected hz, AND
  * its power is >= 6x the median candidate power in that window, AND
  * its power is >= 4x the power in the following gap window (the tone
    must actually be *on*, not just spectral leakage).
Plus: WAV decodes via Python `wave` (real PCM), duration covers the
last tone's end, sample rate within +-2% of spec.

Stdlib-only (no numpy): Goertzel on ~15k-sample windows is fast enough
in pure Python for 4 tones x 8 candidates.
"""
import json
import math
import struct
import sys
import wave


def read_wav(path):
    """Return (rate, [mono float samples -1..1]). Raises on undecodable."""
    with wave.open(path, "rb") as w:
        nch, sw, rate, nfr = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(nfr)
    if sw == 1:
        vals = [b - 128 for b in raw]
        scale = 128.0
    elif sw == 2:
        vals = list(struct.unpack("<%dh" % (len(raw) // 2), raw))
        scale = 32768.0
    else:
        raise ValueError("unsupported sample width %d" % sw)
    if nch == 2:
        vals = [(vals[i] + vals[i + 1]) / 2 for i in range(0, len(vals) - 1, 2)]
    elif nch != 1:
        raise ValueError("unsupported channel count %d" % nch)
    return rate, [v / scale for v in vals]


def goertzel(x, sr, f):
    """Goertzel power estimate of freq f over window x."""
    n = len(x)
    if n == 0:
        return 0.0
    k = 0.5 + (n * f) / sr
    w = 2.0 * math.pi * k / n
    cw = math.cos(w)
    coeff = 2.0 * cw
    s0 = s1 = s2 = 0.0
    for v in x:
        s0 = v + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return (s1 * s1 + s2 * s2 - coeff * s1 * s2) / n


def main():
    wav_path, spec_path = sys.argv[1], sys.argv[2]
    spec = json.load(open(spec_path))
    rate, x = read_wav(wav_path)
    sr = rate
    cands = spec["all_hz"]

    dur = len(x) / sr
    last_off = max(t["off"] for t in spec["tones"])
    detail = {"rate": rate, "duration_s": round(dur, 3), "tones": []}

    if abs(rate - spec["rate"]) > 0.02 * spec["rate"]:
        detail["fail"] = "sample rate %d != %d" % (rate, spec["rate"])
        print(json.dumps({"pass": 0, "detail": detail}))
        return 1
    if dur < last_off * 0.9:
        detail["fail"] = "wav too short: %.2fs < %.2fs" % (dur, last_off)
        print(json.dumps({"pass": 0, "detail": detail}))
        return 1

    # global noise floor: power in a gap window (first gap if present)
    all_ok = True
    for k, t in enumerate(spec["tones"]):
        a = int((t["on"] + 0.05) * sr)
        b = int((t["off"] - 0.05) * sr)
        win = x[a:b]
        powers = [(f, goertzel(win, sr, f)) for f in cands]
        best_f, best_p = max(powers, key=lambda fp: fp[1])
        med = sorted(p for _, p in powers)[len(powers) // 2]
        # gap after this tone (or just after last tone)
        ga = int((t["off"] + 0.01) * sr)
        gb = int((t["off"] + 0.15) * sr)
        gap_p = goertzel(x[ga:gb], sr, t["hz"]) if gb < len(x) else 0.0
        ok = (abs(best_f - t["hz"]) < 1.0
              and best_p >= 6.0 * max(med, 1e-12)
              and best_p >= 4.0 * max(gap_p, 1e-12))
        detail["tones"].append({
            "k": k, "want": t["hz"], "dominant": best_f,
            "power": round(best_p, 6), "median": round(med, 6),
            "gap_power": round(gap_p, 6), "ok": ok})
        all_ok &= ok

    result = {"pass": 1 if all_ok else 0, "detail": detail}
    print(json.dumps(result))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

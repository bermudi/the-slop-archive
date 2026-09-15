#!/usr/bin/env python3
"""stream_match.py — verified scoring of bench.gb serial streams.

Every emitted byte is  LCG_n ^ DIV_n . A run gets credit for frame n only if
its byte decomposes (against the known LCG stream) into a DIV value within
TOL of the golden DIV value at that frame.

  * Wrong content (fake ticker, canned bytes, wrong seed): the LCG component
    is wrong, which survives only by coincidence ~3% per byte -> a garbage
    stream stops within ~30 bytes.
  * Wrong frame length (frame-halving, overclocked PPU): DIV drifts by
    err*274/256 counts per frame and leaves the +-TOL window almost
    immediately; any persistent error > ~0.3% eventually accumulates past it.
  * Legitimate optimizations: instruction batching shifts the DIV read point
    by at most a few hundred cycles = <1 count; TOL=4 (1024 T-cycles)
    absorbs that without absorbing timing cheats.

Subcommands:
  match RX GOLD LCG [--tol N]   print matched-prefix length
  guard GOLD LCG                instrument-validity check on the golden
                               stream itself (is the reference emulator's
                               DIV advancing at hardware rate?)
  selftest                      adversarial suite — run after any change
"""
import sys

TOL = 4


def match_prefix(rx: bytes, gold: bytes, lcg: bytes, tol=TOL) -> int:
    n = 0
    for r, g, l in zip(rx, gold, lcg):
        d_gold = g ^ l
        d_rx = r ^ l
        diff = (d_rx - d_gold) & 0xFF
        dist = min(diff, 256 - diff)
        if dist > tol:
            break
        n += 1
    return n


def div_slope_ok(gold: bytes, lcg: bytes) -> bool:
    """Golden DIV bytes must advance at the hardware rate: 70224/256 =
    274.3125 counts/frame = 18.3125 mod 256 per byte. Guards a broken
    reference emulator (or a mismatched ROM/LCG pair) before scoring."""
    divs = [g ^ l for g, l in zip(gold, lcg)]
    if len(divs) < 64:
        return False
    deltas = [(b - a) & 0xFF for a, b in zip(divs, divs[1:])]
    if any(d < 16 or d > 21 for d in deltas):
        return False
    mean = sum(deltas) / len(deltas)
    return 18.0 <= mean <= 18.6


def _read(p):
    with open(p, "rb") as f:
        return f.read()


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "match":
        rx, gold, lcg = (_read(p) for p in argv[2:5])
        tol = TOL
        if "--tol" in argv:
            tol = int(argv[argv.index("--tol") + 1])
        print(match_prefix(rx, gold, lcg, tol))
        return 0
    if cmd == "guard":
        gold, lcg = _read(argv[2]), _read(argv[3])
        ok = div_slope_ok(gold, lcg)
        print("OK" if ok else "BAD-INSTRUMENT")
        return 0 if ok else 4
    if cmd == "selftest":
        return selftest()
    print(__doc__)
    return 2


def selftest():
    import os
    import random
    random.seed(1234)
    tmp = "/tmp/stream_match.selftest"
    os.makedirs(tmp, exist_ok=True)

    seed = 7
    inc = (2 * seed + 1) & 0xFF
    st = seed
    lcg = bytearray()
    div = bytearray()
    c = 12345  # cycles at first read, arbitrary but fixed
    for i in range(2000):
        st = (st * 41 + inc) & 0xFF
        lcg.append(st)
        c += 70224
        div.append(((c // 256) + 97) & 0xFF)  # +97: read offset within frame
    lcg = bytes(lcg)
    gold = bytes(a ^ b for a, b in zip(lcg, div))

    def m(rx, tol=TOL):
        return match_prefix(rx, gold, lcg, tol)

    # 1. honest stream matches fully
    assert m(gold) == 2000, "honest stream must fully match"
    # 2. fake '*' ticker dies immediately-ish
    assert m(b"*" * 2000) < 40, "constant ticker must not match"
    # 3. random garbage dies immediately-ish
    assert m(os.urandom(2000)) < 40, "garbage must not match"
    # 4. correct content, frozen DIV (cached/replayed timing) drifts out
    frozen = bytes(l ^ div[0] for l in lcg)
    assert m(frozen) < 8, "frozen DIV must fail fast"
    # 5. frame-halver: DIV advances 137 counts/frame -> fails within ~2
    half = bytearray()
    c = 12345
    for i in range(2000):
        c += 35112
        half.append(((c // 256) + 97) & 0xFF)
    halver = bytes(a ^ b for a, b in zip(lcg, half))
    assert m(halver) <= 3, "frame-halver must fail within 2 frames"
    # 6. 1% frame-length error accumulates past tolerance by frame ~2
    slow = bytearray()
    c = 12345
    for i in range(2000):
        c += 69524
        slow.append(((c // 256) + 97) & 0xFF)
    one_pct = bytes(a ^ b for a, b in zip(lcg, slow))
    assert m(one_pct) <= 4, "1% timing error must fail fast"
    # 7. benign per-frame jitter (batched PPU sync) within tolerance passes
    jit = bytearray()
    for i in range(2000):
        jit.append((div[i] + random.randint(-3, 3)) & 0xFF)
    jittered = bytes(a ^ b for a, b in zip(lcg, jit))
    assert m(jittered) == 2000, "small jitter must not break honest runs"
    # 8. large jitter is still rejected (tolerance is not vacuous)
    jit2 = bytearray()
    for i in range(2000):
        jit2.append((div[i] + random.choice([-9, -7, 7, 9])) & 0xFF)
    big = bytes(a ^ b for a, b in zip(lcg, jit2))
    assert m(big) == 0, "large jitter must be rejected"
    # 9. guard accepts the honest golden, rejects a halver golden
    assert div_slope_ok(gold, lcg)
    halver_gold = halver  # bytes aligned with same lcg
    assert not div_slope_ok(halver_gold, lcg)
    print("selftest: all adversarial cases behave as designed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

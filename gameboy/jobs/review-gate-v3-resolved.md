# Pending: fresh-context review of gate v3 — COMPLETED, findings addressed

Review completed 2026-09-16 (resumed session, 1m20s). Full report:
/tmp/delegate-output-resume_01a0a756-6323d151c35175f6b76541d547fcf1d9.md
(copies of the findings below are the durable record).

## Findings and resolutions

1. **BLOCKER — ROM trust fix was dead code in deployment.** Harbor uploads
   only `tests/` into the container ($ENVD never exists there; agent is
   root), so the verifier silently graded from agent-writable
   /opt/n810/roms. FIXED: verifier ROMs now live in tests/roms/ (uploaded
   with the verifier, same-name-overwrite pristine); no fallback; missing
   ROM aborts scoring. campaign.sh stages from the same tests/roms.
2. **MAJOR — Track A denominator coupled to returned lines.** Empty suite
   + passing challenge = test_roms 1.0. FIXED: denominator = suite.tsv
   rows + 1, missing results count as failures, P clamped to rows.
3. **MAJOR — planted ref sources survive harbor's merge-copy** and were
   compiled into the golden core. FIXED: ref/SOURCES.txt lists the exact
   .c set; both verifiers refuse to build if ref/*.c != SOURCES.txt
   (exit 4) and compile exactly the listed files.
4. MINOR — manifest/suite.tsv/cap drift → silent false-zero. FIXED:
   cross-checked at scoring start; drift aborts (exit 3).
5. MINOR — stderr merged into verdict haystack. FIXED: suite_run.sh reads
   stdout only. (`Done` narrowing vs NOTES documented in DESIGN.md.)
6. MINOR — unbounded suite ssh; wedged build eats verifier budget. FIXED:
   timeout 900s (B) / 600s (A); timeout grades fail-closed, reward.json
   still written.
7. MINOR — doc said min-across-variants, code took max. FIXED: code now
   takes min (matches the frozen spec).
8. MINOR hygiene — (a) runner now emits the documented `#diag` line
   (parsers accept both); (b,c,d) noted, not actioned (temp cleanup, fixed
   WORK in Track A, verifier bench-lock) — cosmetic, serialized harness.

## Extra hardening from finding 1's root cause

Device-side staging uses unpredictable dir/binary names (the agent had
SSH all run: fixed paths could be pre-planted with stub ROMs or
chattr-frozen). Confirmed on device post-fix: 6/6 + `#diag trap.gb 1`
under the new runner — frozen manifest remains valid (ref emits nothing
on stderr, so the narrowed predicate changes nothing for honest builds).

Verified-correct per reviewer (no action): score.py arithmetic + all 9
selftest vectors (hand-recomputed), rpartition parsing, Track A weight
sum = 1.00, mode-aware semantics vs NOTES.md.


## Reviewer prompt (copy-paste into a fresh reviewer agent)

You are reviewing a just-implemented change to a benchmark verifier
(adversarial review, fresh context — the implementer cannot approve their
own work).

Repo: /home/daniel/build/llm-benchmarking/gameboy. Review the last two
commits (471a47d and e777962): `git log --oneline -3` then
`git show 471a47d` and `git show e777962`. Relevant context files (read
them): benchmark/DESIGN.md (Track B section, "Gate v3"),
benchmark/n810-gb-optimize/tests/{suite.tsv,suite_run.sh,score.py,campaign.sh,selftest_gate.sh,baseline_manifest.json,test.sh},
benchmark/n810-gb-emulator/tests/{suite.tsv,suite_run.sh,test.sh},
gb810/test/NOTES.md (sections 1.4, 1.8, 2 — grading semantics).

What the change is supposed to do:
1. Replace a count-based correctness gate (pass fraction >= 0.8) with
   preservation-by-name: a measured manifest (baseline_manifest.json, from a
   20x on-device campaign) lists which ROMs the reference core passes; any
   of those failing in a submission zeroes ALL speed credit. New fixes are
   counted separately.
2. trap.gb moved out of the scored suite to diagnostic-only (it speaks the
   mooneye ld b,b exit protocol — no serial output ever — so a black-box
   serial runner cannot grade it).
3. Overspeed hard line: app fps > 59.7275*1.02 zeroes the app speed term.
4. Verifier stages ROMs from a harness-staged (non-agent-writable)
   directory instead of agent-writable /opt/n810/roms inside the task
   container.
5. Track A mirrors the mode-aware per-ROM grading.

Attack it as if you were a cheating agent AND audit it as a skeptical
benchmark author:
- Can the new gate be gamed? (count-parity trades, manifest tampering,
  partial suite staging, ssh output forgery, scoring arithmetic)
- Are there fail-open paths? (missing files, empty outputs, set -u unset
  vars, mktemp collisions, the ROMDIR fallback to /opt/n810/roms)
- Are the semantics of mode-aware grading correct per NOTES.md? (want
  substring + exit 0; trap = silent + clean exit)
- Is score.py's arithmetic right? Check the selftest vectors against the
  formula 0.30*vroms + speed-if-correct, speed = 0.50*app_imp +
  0.20*emu_imp, overspeed zeroes app_imp.
- Shell quoting hazards (the "06-ld r,r.gb" space), the rpartition parsing,
  tab-separated suite.tsv correctness.
- Anything that changes Track A scoring semantics in a way that breaks its
  documented ladder (weights sum, challenge-sig counting).
- Real bugs only — flag style nits separately if at all.

Report: numbered findings, each with severity (BLOCKER / MAJOR / MINOR),
file:line, and a concrete failure scenario. If you find no blockers, say so
explicitly. Do not fix anything — report only.

## State at cancel time (all committed)

- Manifest measured: 6/6 ROMs 100% over 20 device runs, no flaky, trap.gb
  diagnostic clean 20/20. hl-ref sha256
  a4d2ba84362ae80047b3753d6d4482950f9b2124b049ec997a9ec13df7d755c2.
- selftest_gate.sh: 24 assertions, all green.
- Both verifiers syntax-clean; no stale references (m_roms, micro dir,
  /opt/n810/roms in verifier paths).

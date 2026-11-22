#!/usr/bin/env python3
"""Task 03 calibration harness placeholder.

The runner is intentionally not populated before the real self-update patch
exists. Calibration must include base, gold, one structurally different
100-point implementation, several deliberate partials, and one invalid
regression-breaking patch. See README.md.
"""

from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DIR = TASK_DIR / "solution" / "reference"
EXPECTED: dict[str, tuple[str, int | None]] = {}


def main() -> int:
    if not REFERENCE_DIR.exists() or not EXPECTED:
        print("AUTHORING: calibration waits for the real reference and hidden suite")
        return 2
    raise NotImplementedError("construct calibrated partials with the real gold")


if __name__ == "__main__":
    raise SystemExit(main())

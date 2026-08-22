# Reference solution — pending

No golden patch exists yet. This is deliberate: Task 03 comes from a real
missing Stitch capability, not from a fabricated benchmark-only
implementation.

After the production implementation is complete and review-proven:

1. choose the exact final commit/range and record it in `task.toml`;
2. generate `solution.patch` as the binary-safe curated-base-to-final diff;
3. copy only the changed final files into `reference/`;
4. write hidden tests against that implementation and an alternative
   structurally different implementation;
5. generate the frozen manifest and calibrate partial solutions.

Nothing under `solution/` is copied into the agent environment or used during
grading.

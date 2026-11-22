# Hidden self-update contract tests — pending

No hidden tests are authored before the real implementation exists. Write
them with the reference, not from an imagined internal design.

## Test only public behavior

Inject one integration-test target at `tests/self_update_contract.rs`. Launch
the compiled `stitch` binary and a deterministic loopback HTTP server selected
through `STITCH_UPDATE_BASE_URL`. Do not import private updater symbols or
assert module/file/helper names.

The suite must cover every prompt requirement:

- no repository required; no dotfile access or mutation;
- latest stable discovery and semver no-op/no-downgrade behavior;
- x86_64 and aarch64 artifact selection (run the latter under the verifier
  image's qemu-aarch64 toolchain; do not require a production test override);
- exact checksum-sidecar validation;
- malformed metadata/checksum/archive and wrong artifact rejection;
- archive traversal, links, duplicate/missing/unexpected entries;
- atomic replacement, executable mode, and failure preservation;
- concurrent updater serialization and changed-underfoot protection;
- HTTP/status/truncation/filesystem/permission failures;
- human and JSON stdout/stderr/exit contracts;
- override failure never falls back to GitHub.

The hidden suite may create fake executable copies and fixture archives under
its temporary directory. It must never replace the verifier's `/app` binary
or contact a live service.

Every weighted test must fail on the curated base and pass on the reference.
Preservation tests carry zero points but gate validity. Also write one
alternative implementation with a different module split; it must score 100.

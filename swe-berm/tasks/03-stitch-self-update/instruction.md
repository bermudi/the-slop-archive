# Add safe self-update to Stitch

Stitch is a Linux-only Rust CLI for managing dotfiles. Its release workflow
already publishes two binaries to GitHub Releases:

- `stitch-vX.Y.Z-x86_64-unknown-linux-gnu.tar.gz`
- `stitch-vX.Y.Z-aarch64-unknown-linux-gnu.tar.gz`

Each archive has a same-named `.sha256` sidecar. Stitch currently tells users
to download, verify, unpack, and install these files manually. Add a
`stitch self-update` command that performs that release-binary update safely.

## Required behavior

- The command is global: it must work without a Stitch repository or
  configuration and must never inspect or mutate the user's dotfiles.
- Discover the latest stable release, compare it to the running package
  version, and report an honest no-op when Stitch is already current. Never
  downgrade when the remote version is older.
- Support Stitch's two published Linux architectures (`x86_64` and
  `aarch64`). Reject unsupported OS/architecture combinations before
  downloading an artifact.
- Download the matching archive and its published SHA-256 sidecar. Treat the
  release metadata, checksum text, and archive as untrusted input:
  malformed versions, malformed/ambiguous checksums, wrong filenames,
  checksum mismatches, unsafe archive entries, missing binaries, and
  unexpected archive contents must fail without changing the installed
  executable.
- Replace the executable atomically in its existing directory. Preserve a
  usable executable mode. A failed download, validation, extraction, write,
  sync, or replacement must leave the previous executable runnable and must
  not leave a second executable selected as current.
- Do not invoke `sudo`, a shell, `curl`, `tar`, or another package manager.
  If the executable cannot be replaced because of permissions, fail with a
  useful message and non-zero exit.
- Concurrent self-update processes must not interleave installation. One may
  complete and the other may then observe the installed result; neither may
  corrupt the executable or silently replace a different update.
- Follow Stitch's existing output contract. Human output goes to stdout on
  success and stderr on failure. `--json self-update` emits one valid JSON
  envelope on stdout with no stray output; failures use Stitch's typed,
  branchable error reporting and non-zero exit status.
- Network and filesystem failures must surface with enough context to debug;
  do not swallow them. Do not log archive bytes or other unbounded response
  bodies.

## Deterministic release-source seam

The production default is the official `bermudi/stitch` GitHub repository API
root (`https://api.github.com/repos/bermudi/stitch`). The update client must
also honor `STITCH_UPDATE_BASE_URL`, whose value replaces that API root. This
is an operator mirror/test seam, not a persisted setting.

Fetch `<base>/releases/latest` and consume the GitHub-compatible JSON release
shape (`tag_name`, `draft`, `prerelease`, and the assets' `name` plus
`browser_download_url`). Download only the two exact matching named assets
from the URLs in that response. After an override is set, neither metadata nor
assets may fall back to GitHub when the override response fails or is
incomplete.

The test environment has no external network. Verify your implementation
against a local HTTP server through this override. Do not special-case
localhost, fixture versions, or test filenames.

## Scope

- Do not add background update checks, startup network calls, auto-update,
  channels, prerelease selection, downgrade flags, or update configuration.
- Do not change the release artifact naming convention or workflow.
- Do not change dotfile config/state schemas.
- Source builds and package-manager installs do not need special detection:
  update the executable returned by the operating system when it can be
  replaced safely, otherwise report the permission/filesystem failure.

## Repository conventions

- Rust 2024, Linux only, no `unsafe`.
- Keep the existing suite green.
- Run `cargo fmt --check`, `cargo clippy --locked --all-targets
  --all-features -- -D warnings`, and `cargo test --locked`.
- The sandbox has no network. `ureq`, `tar`, `flate2`, and `semver` are
  cached for optional offline use; add only what you need with Cargo's
  offline mode.
- Commit your implementation when done.

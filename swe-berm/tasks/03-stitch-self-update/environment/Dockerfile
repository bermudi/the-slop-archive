FROM rust:1.97-bookworm

# Python scores the deterministic libtest ledger. Git is used for isolated
# patch collection/application. CA roots are needed by the production updater,
# though grading serves releases from loopback only.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates python3 gcc-aarch64-linux-gnu qemu-user \
 && rm -rf /var/lib/apt/lists/*

# The held-out suite runs the architecture-selection contract under qemu as
# well as natively, rather than inspecting implementation constants.
RUN rustup target add aarch64-unknown-linux-gnu

# Seed a small, pinned set of optional update dependencies into Cargo's cache
# while image builds still have network. The graded container is no-network;
# agents may add only what is already cached or implement with the stdlib.
WORKDIR /opt/update-deps
COPY update-deps/Cargo.toml update-deps/Cargo.lock ./
COPY update-deps/src ./src
RUN cargo fetch --locked

WORKDIR /app
COPY stitch ./

# Fetch and compile the exact base dependency graph during image construction.
RUN cargo fetch --locked \
 && cargo test --locked --no-run

# The snapshot contains no future Git history or reference solution.
RUN git config --global --add safe.directory /app \
 && git init \
 && git config user.email "task@harbor.local" \
 && git config user.name "harbor" \
 && git config core.hooksPath /dev/null \
 && git add . \
 && git commit -m "base: stitch v0.14.2 (self-update absent)" \
 && git tag base \
 && git branch -M main \
 && ! grep -Riq "self.update" src tests

CMD ["/bin/bash"]

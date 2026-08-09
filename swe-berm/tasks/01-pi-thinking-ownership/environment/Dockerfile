FROM oven/bun:1.2.21

# System deps for git operations
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the bundle snapshot (base state at 7f00c6a)
# Context is the environment/ directory (Harbor sets CONTEXT_DIR=environment)
COPY pi-packages ./pi-packages

# Install deps at build time (network allowed during build)
WORKDIR /app/pi-packages/bermudis-pi-goodies
RUN bun install --frozen-lockfile 2>&1 | tail -20

# Back to repo root and turn it into a git repo at base
WORKDIR /app
RUN git config --global --add safe.directory /app \
 && git init \
 && git config user.email "task@harbor.local" \
 && git config user.name "harbor" \
 && git config core.hooksPath /dev/null \
 && git add . \
 && git commit -m "base: bermudis-pi-goodies at 7f00c6a" \
 && git tag base \
 && git branch -M main

# Sanity: show base state is the buggy dual-ownership version
RUN grep -q "ALL_LEVELS" pi-packages/bermudis-pi-goodies/fixed-defaults.ts && echo "base: dual-ownership present" || (echo "base snapshot wrong"; exit 1)

CMD ["/bin/bash"]

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ clang make cmake meson ninja-build pkg-config \
        libsdl2-dev python3 python3-pil \
        ca-certificates curl file binutils gdb strace \
    && rm -rf /var/lib/apt/lists/*

COPY docs/ /opt/gb/docs/
COPY roms/ /opt/gb/roms/

# Custom model providers for the in-container pi agent (upstream pi knows
# neither kilo nor commandcode). Auth arrives via the apiKeyEnv env var at
# run time (--ae).
RUN mkdir -p /root/.pi/agent
COPY pi-models.json /root/.pi/agent/models.json

# Devin CLI refuses non-interactive runs in an untrusted workspace, and env
# overrides don't reach the harbor-run command (verified 2026-11). Pre-trust
# /work via the CLI's own trust store. Inert for other agents.
RUN mkdir -p /root/.local/share/devin/cli \
    && printf '{"trusted_paths":["/work"]}\n' \
        > /root/.local/share/devin/cli/trusted_workspaces.json

RUN mkdir -p /work/dist /logs/verifier
WORKDIR /work

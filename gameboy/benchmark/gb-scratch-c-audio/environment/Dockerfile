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

RUN mkdir -p /work/dist /logs/verifier
WORKDIR /work

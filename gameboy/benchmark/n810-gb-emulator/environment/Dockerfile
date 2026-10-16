FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        openssh-client python3 python3-pil gcc make ca-certificates \
        binutils llvm curl file \
    && rm -rf /var/lib/apt/lists/*

# N810 access: dedicated throwaway key, device on isolated network.
COPY ssh/n810_rsa /etc/n810/key
RUN chmod 600 /etc/n810/key && mkdir -p /root/.ssh && printf 'Host n810\n  HostName 192.168.0.100\n  User user\n  IdentityFile /etc/n810/key\n  HostKeyAlgorithms +ssh-rsa\n  PubkeyAcceptedAlgorithms +ssh-rsa\n  KexAlgorithms +diffie-hellman-group14-sha1\n  MACs +hmac-sha1\n  Ciphers +aes128-cbc\n  StrictHostKeyChecking no\n  UserKnownHostsFile /dev/null\n' > /root/.ssh/config

COPY tools/n810-* /usr/local/bin/
RUN chmod +x /usr/local/bin/n810-*

COPY tools/HARNESS.md /opt/n810/HARNESS.md
COPY roms/ /opt/n810/roms/
COPY docs/ /opt/n810/docs/

RUN mkdir -p /work/dist /logs/verifier
WORKDIR /work

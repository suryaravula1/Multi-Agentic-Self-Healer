FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd \
    systemd-sysv \
    procps \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Minimal fake service environment for sandboxed recovery drills
RUN mkdir -p /var/log /run/systemd/system /etc/systemd/system \
    && echo "[Unit]\nDescription=Sandbox nginx\nAfter=network.target\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/true\n\n[Install]\nWantedBy=multi-user.target" > /etc/systemd/system/nginx.service \
    && touch /var/log/syslog /var/log/kern.log

WORKDIR /sandbox
CMD ["/bin/bash"]

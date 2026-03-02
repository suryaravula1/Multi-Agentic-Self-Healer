# Minimal systemd-in-Docker lab for injecting recoverable failures.
# Not a full VM — enough to generate real journald logs and test recovery flows.

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    systemd \
    systemd-sysv \
    dbus \
    curl \
    procps \
    iproute2 \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Fake app services for failure injection drills
RUN mkdir -p /opt/lab /var/log/lab

COPY lab/services/demo-app.service /etc/systemd/system/demo-app.service
COPY lab/services/cache-sidecar.service /etc/systemd/system/cache-sidecar.service
COPY lab/inject/ /opt/lab/inject/
RUN chmod +x /opt/lab/inject/*.sh

# systemd as PID 1 requires this stripped-down setup in containers
RUN systemctl enable demo-app.service cache-sidecar.service || true

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]

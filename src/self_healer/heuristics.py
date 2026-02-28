"""Rule-based fallback when LLM is unavailable — deterministic heuristics."""

from __future__ import annotations

import re

from self_healer.models.schemas import (
    DiagnosisResult,
    LogEvent,
    LogParseResult,
    LogSource,
    RecoveryPlan,
    RecoveryStep,
    RiskLevel,
    Severity,
)


def _detect_source(logs: str) -> LogSource:
    has_kernel = bool(re.search(r"\b(kernel|oom|segfault|Call Trace)\b", logs, re.I))
    has_systemd = bool(re.search(r"\b(systemd|\.service|\.target)\b", logs, re.I))
    if has_kernel and has_systemd:
        return LogSource.MIXED
    if has_kernel:
        return LogSource.KERNEL
    if has_systemd:
        return LogSource.SYSTEMD
    return LogSource.UNKNOWN


def _extract_signatures(logs: str) -> list[str]:
    patterns = [
        r"Out of memory: Kill process \d+ \(([^)]+)\)",
        r"Failed to start ([\w@.-]+\.service)",
        r"No space left on device",
        r"start job .* running for .* ([\w@.-]+\.service)",
        r"Main process exited, code=exited, status=\d+",
        r"Killed process \d+ \(([^)]+)\)",
        r"connect ECONNREFUSED",
        r"Dependency ([\w@.-]+\.service) failed",
    ]
    signatures: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, logs):
            signatures.append(match.group(0))
    return list(dict.fromkeys(signatures))[:10]


def _severity_for_line(line: str) -> Severity:
    lower = line.lower()
    if any(k in lower for k in ("panic", "oom", "killed process", "failed to start")):
        return Severity.CRITICAL
    if any(k in lower for k in ("error", "failed", "no space")):
        return Severity.HIGH
    if "warn" in lower:
        return Severity.MEDIUM
    return Severity.LOW


def parse_logs_heuristic(logs: str, source_hint: LogSource = LogSource.UNKNOWN) -> LogParseResult:
    source = source_hint if source_hint != LogSource.UNKNOWN else _detect_source(logs)
    signatures = _extract_signatures(logs)

    events: list[LogEvent] = []
    for line in logs.splitlines():
        stripped = line.strip()
        if not stripped or len(stripped) < 10:
            continue
        if not any(k in stripped.lower() for k in ("error", "fail", "oom", "killed", "panic", "warn")):
            continue
        ts_match = re.match(r"^(\w{3}\s+\d{1,2}\s+[\d:.]+)", stripped)
        events.append(
            LogEvent(
                timestamp=ts_match.group(1) if ts_match else None,
                source="kernel" if "kernel" in stripped.lower() else "systemd",
                message=stripped[:500],
                severity=_severity_for_line(stripped),
            )
        )

    summary = f"Detected {len(signatures)} error signature(s) across {len(events)} notable log lines."
    return LogParseResult(
        source=source,
        events=events[:20],
        error_signatures=signatures,
        summary=summary,
        confidence=0.75 if signatures else 0.4,
    )


def diagnose_heuristic(parse_result: LogParseResult) -> DiagnosisResult:
    text = " ".join(parse_result.error_signatures).lower()

    if "out of memory" in text or "killed process" in text:
        return DiagnosisResult(
            root_cause="Memory exhaustion triggered the OOM killer, terminating critical processes",
            failure_category="oom",
            affected_components=["memory", "affected processes"],
            evidence=parse_result.error_signatures[:3],
            confidence=0.85,
            recommended_actions=[
                "Identify memory-heavy processes",
                "Restart affected services",
                "Consider increasing swap or memory limits",
            ],
        )

    if "no space left on device" in text:
        return DiagnosisResult(
            root_cause="Filesystem is full, blocking writes and causing service failures",
            failure_category="disk_full",
            affected_components=["disk", "journald", "affected services"],
            evidence=parse_result.error_signatures[:3],
            confidence=0.9,
            recommended_actions=[
                "Check disk usage",
                "Truncate or rotate large log files",
                "Restart failed services after freeing space",
            ],
        )

    service_match = re.search(r"([\w@.-]+\.service)", text)
    service = service_match.group(1) if service_match else "unknown.service"

    if "failed to start" in text or "main process exited" in text:
        return DiagnosisResult(
            root_cause=f"Service {service} failed to start or crashed unexpectedly",
            failure_category="service_failure",
            affected_components=[service],
            evidence=parse_result.error_signatures[:3],
            confidence=0.8,
            recommended_actions=[
                f"Inspect journal for {service}",
                f"Reset failed state and restart {service}",
            ],
        )

    if "start job" in text and "running" in text:
        return DiagnosisResult(
            root_cause="systemd dependency deadlock — a start job is blocking boot/startup ordering",
            failure_category="deadlock",
            affected_components=["systemd", service],
            evidence=parse_result.error_signatures[:3],
            confidence=0.75,
            recommended_actions=[
                "Identify blocking unit",
                "Reset failed units",
                "Restart dependency chain",
            ],
        )

    if "econnrefused" in text or "dependency" in text and "failed" in text:
        dep = "redis.service" if "redis" in text else service
        return DiagnosisResult(
            root_cause=f"Upstream dependency {dep} is unavailable, causing {service} to fail",
            failure_category="service_failure",
            affected_components=[dep, service],
            evidence=parse_result.error_signatures[:3],
            confidence=0.82,
            recommended_actions=[
                f"Restart {dep}",
                f"Verify connectivity then restart {service}",
            ],
        )

    return DiagnosisResult(
        root_cause="Unable to determine root cause from available log signatures",
        failure_category="unknown",
        affected_components=[],
        evidence=parse_result.error_signatures[:3],
        confidence=0.3,
        recommended_actions=["Manual investigation required"],
    )


def plan_recovery_heuristic(diagnosis: DiagnosisResult) -> RecoveryPlan:
    steps: list[RecoveryStep] = []

    if diagnosis.failure_category == "disk_full":
        steps = [
            RecoveryStep(
                order=1,
                command="df -h",
                rationale="Confirm disk usage before remediation",
                expected_outcome="Disk usage report",
                risk_level=RiskLevel.LOW,
            ),
            RecoveryStep(
                order=2,
                command="truncate -s 0 /var/log/syslog",
                rationale="Free space by truncating large syslog",
                expected_outcome="Disk space recovered",
                risk_level=RiskLevel.HIGH,
                rollback_command=None,
            ),
            RecoveryStep(
                order=3,
                command="systemctl daemon-reload",
                rationale="Reload systemd after disk recovery",
                expected_outcome="systemd state refreshed",
                risk_level=RiskLevel.LOW,
            ),
        ]
    elif diagnosis.failure_category == "oom":
        service = diagnosis.affected_components[-1] if diagnosis.affected_components else "nginx"
        if ".service" not in service:
            service = "nginx"
        steps = [
            RecoveryStep(
                order=1,
                command="free -h",
                rationale="Verify current memory state",
                expected_outcome="Memory usage report",
                risk_level=RiskLevel.LOW,
            ),
            RecoveryStep(
                order=2,
                command=f"systemctl restart {service}",
                rationale="Restart OOM-affected service",
                expected_outcome=f"{service} running again",
                risk_level=RiskLevel.LOW,
                rollback_command=f"systemctl stop {service}",
            ),
        ]
    elif diagnosis.failure_category == "deadlock":
        service = next((c for c in diagnosis.affected_components if ".service" in c), "nginx.service")
        steps = [
            RecoveryStep(
                order=1,
                command=f"systemctl reset-failed {service}",
                rationale="Clear failed state from blocking unit",
                expected_outcome="Unit no longer in failed state",
                risk_level=RiskLevel.LOW,
            ),
            RecoveryStep(
                order=2,
                command=f"systemctl start {service}",
                rationale="Start the blocked service",
                expected_outcome=f"{service} active",
                risk_level=RiskLevel.LOW,
            ),
        ]
    else:
        service = next((c for c in diagnosis.affected_components if ".service" in c), "nginx.service")
        steps = [
            RecoveryStep(
                order=1,
                command=f"journalctl -u {service} -n 50 --no-pager",
                rationale="Gather recent service logs",
                expected_outcome="Recent journal entries",
                risk_level=RiskLevel.LOW,
            ),
            RecoveryStep(
                order=2,
                command=f"systemctl restart {service}",
                rationale="Attempt service recovery",
                expected_outcome=f"{service} running",
                risk_level=RiskLevel.LOW,
            ),
        ]

    high_risk = any(s.risk_level == RiskLevel.HIGH for s in steps)
    return RecoveryPlan(
        steps=steps,
        blast_radius="Limited to targeted service and log files; sandboxed execution",
        requires_human_approval=high_risk or diagnosis.confidence < 0.7,
        estimated_success_rate=0.4 if diagnosis.confidence >= 0.7 else 0.2,
    )

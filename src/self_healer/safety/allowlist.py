"""Deterministic safety constraints for recovery command validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Commands that are never permitted, even in sandbox.
BLOCKED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("recursive delete on root", re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*\s+)?(/|/\*|/\.\*)", re.I)),
    ("disk overwrite", re.compile(r"\b(dd|shred|wipefs)\b", re.I)),
    ("kernel module unload", re.compile(r"\b(rmmod|modprobe\s+-r)\b", re.I)),
    ("firewall flush", re.compile(r"\b(iptables\s+-F|nft\s+flush)\b", re.I)),
    ("user/password mutation", re.compile(r"\b(userdel|passwd|chpasswd)\b", re.I)),
    ("remote code fetch pipe", re.compile(r"\b(curl|wget)\b.*\|\s*(ba)?sh", re.I)),
    ("privilege escalation", re.compile(r"\b(sudo\s+su|chmod\s+[0-7]*777\s+/)\b", re.I)),
    ("fork bomb", re.compile(r":\(\)\s*\{", re.I)),
    ("shell redirect to device", re.compile(r">\s*/dev/(sd|nvme|vd)[a-z]", re.I)),
]

# Recovery operations permitted when they match exactly one prefix.
ALLOWED_COMMAND_PREFIXES: tuple[str, ...] = (
    "systemctl restart ",
    "systemctl start ",
    "systemctl stop ",
    "systemctl reset-failed ",
    "systemctl daemon-reload",
    "journalctl ",
    "df ",
    "du ",
    "free ",
    "sync",
    "echo ",
    "cat /proc/",
    "cat /sys/",
    "ls ",
    "lsblk ",
    "find /var/log ",
    "truncate -s 0 ",
    "rm /var/log/",
    "rm -f /var/log/",
    "rm /tmp/",
    "rm -f /tmp/",
    "mkdir -p /tmp/",
    "touch /tmp/",
    "ip link show",
    "ip addr show",
    "ss -",
    "dmesg ",
    "sysctl ",
)

# High-risk but sometimes necessary — require explicit approval.
HIGH_RISK_PREFIXES: tuple[str, ...] = (
    "systemctl stop ",
    "truncate -s 0 ",
    "rm /var/log/",
    "rm -f /var/log/",
)


@dataclass(frozen=True)
class CommandCheck:
    allowed: bool
    risk_level: str
    reason: str


def normalize_command(command: str) -> str:
    return " ".join(command.strip().split())


def check_command(command: str) -> CommandCheck:
    normalized = normalize_command(command)

    if not normalized:
        return CommandCheck(False, "blocked", "Empty command")

    if ";" in normalized or "&&" in normalized or "||" in normalized or "|" in normalized:
        return CommandCheck(False, "blocked", "Compound/piped commands are not permitted")

    if "`" in normalized or "$(" in normalized:
        return CommandCheck(False, "blocked", "Command substitution is not permitted")

    for label, pattern in BLOCKED_PATTERNS:
        if pattern.search(normalized):
            return CommandCheck(False, "blocked", f"Blocked pattern: {label}")

    matched_prefix = next(
        (prefix for prefix in ALLOWED_COMMAND_PREFIXES if normalized.startswith(prefix)),
        None,
    )
    if matched_prefix is None:
        return CommandCheck(False, "blocked", "Command not on recovery allowlist")

    risk = "high" if any(normalized.startswith(p) for p in HIGH_RISK_PREFIXES) else "low"
    return CommandCheck(True, risk, "Allowed recovery command")


def is_plan_fully_approved(commands: list[str]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for command in commands:
        result = check_command(command)
        if not result.allowed:
            reasons.append(f"{command!r}: {result.reason}")
    return (len(reasons) == 0, reasons)

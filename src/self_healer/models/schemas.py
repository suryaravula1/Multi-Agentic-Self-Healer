from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineStage(str, Enum):
    PARSE = "parse"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    SAFETY = "safety"
    EXECUTE = "execute"
    COMPLETE = "complete"
    FAILED = "failed"


class LogSource(str, Enum):
    KERNEL = "kernel"
    SYSTEMD = "systemd"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RiskLevel(str, Enum):
  LOW = "low"
  MEDIUM = "medium"
  HIGH = "high"
  BLOCKED = "blocked"


class HealRequest(BaseModel):
    logs: str = Field(..., min_length=1, description="Raw kernel/systemd log text")
    source_hint: LogSource = LogSource.UNKNOWN
    auto_execute: bool | None = Field(
        default=None,
        description="Override global auto_execute; when false, only plan is returned",
    )
    context: dict[str, Any] = Field(default_factory=dict)


class LogEvent(BaseModel):
    timestamp: str | None = None
    source: str
    message: str
    severity: Severity = Severity.MEDIUM


class LogParseResult(BaseModel):
    source: LogSource
    events: list[LogEvent]
    error_signatures: list[str]
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)


class DiagnosisResult(BaseModel):
    root_cause: str
    failure_category: str
    affected_components: list[str]
    evidence: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    recommended_actions: list[str]


class RecoveryStep(BaseModel):
    order: int
    command: str
    rationale: str
    expected_outcome: str
    risk_level: RiskLevel = RiskLevel.LOW
    rollback_command: str | None = None


class RecoveryPlan(BaseModel):
    steps: list[RecoveryStep]
    blast_radius: str
    requires_human_approval: bool
    estimated_success_rate: float = Field(ge=0.0, le=1.0)


class SafetyVerdict(BaseModel):
    approved: bool
    blocked_steps: list[int] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    sanitized_steps: list[RecoveryStep] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    step_order: int
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    success: bool


class HealResponse(BaseModel):
    request_id: str
    stage_reached: PipelineStage
    parse: LogParseResult | None = None
    diagnosis: DiagnosisResult | None = None
    plan: RecoveryPlan | None = None
    safety: SafetyVerdict | None = None
    executions: list[ExecutionResult] = Field(default_factory=list)
    resolved: bool = False
    message: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

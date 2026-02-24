from __future__ import annotations

from self_healer.models.schemas import RecoveryPlan, RecoveryStep, RiskLevel, SafetyVerdict
from self_healer.safety.allowlist import check_command, normalize_command


class SafetyGateAgent:
    """Deterministic safety validator — no LLM, purely rule-based."""

    name = "safety_gate"

    def run(self, plan: RecoveryPlan) -> SafetyVerdict:
        sanitized: list[RecoveryStep] = []
        blocked_steps: list[int] = []
        reasons: list[str] = []

        for step in sorted(plan.steps, key=lambda s: s.order):
            normalized = normalize_command(step.command)
            check = check_command(normalized)

            if not check.allowed:
                blocked_steps.append(step.order)
                reasons.append(f"Step {step.order}: {check.reason}")
                continue

            risk = RiskLevel(check.risk_level) if check.risk_level in {r.value for r in RiskLevel} else RiskLevel.LOW
            sanitized.append(
                step.model_copy(update={"command": normalized, "risk_level": risk})
            )

            if step.rollback_command:
                rollback_check = check_command(normalize_command(step.rollback_command))
                if not rollback_check.allowed:
                    reasons.append(f"Step {step.order} rollback blocked: {rollback_check.reason}")

        has_high_risk = any(s.risk_level == RiskLevel.HIGH for s in sanitized)
        approved = len(blocked_steps) == 0 and len(sanitized) > 0

        if has_high_risk or plan.requires_human_approval:
            approved = False
            if has_high_risk:
                reasons.append("Plan contains high-risk steps — human approval required")
            if plan.requires_human_approval:
                reasons.append("Planner flagged plan for human approval")

        return SafetyVerdict(
            approved=approved,
            blocked_steps=blocked_steps,
            reasons=reasons,
            sanitized_steps=sanitized,
        )

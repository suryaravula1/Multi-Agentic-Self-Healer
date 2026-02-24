from __future__ import annotations

import json

from self_healer.agents.base import BaseAgent
from self_healer.config import settings
from self_healer.models.schemas import DiagnosisResult, RecoveryPlan
from self_healer.safety.prompts import RECOVERY_PLANNER_PROMPT


class RecoveryPlannerAgent(BaseAgent):
    name = "recovery_planner"

    def run(self, diagnosis: DiagnosisResult, parse_summary: str) -> RecoveryPlan:
        prompt = RECOVERY_PLANNER_PROMPT.format(max_steps=settings.max_recovery_steps)
        user_content = (
            f"Log summary: {parse_summary}\n\n"
            f"Diagnosis:\n{json.dumps(diagnosis.model_dump(), indent=2)}"
        )
        raw = self._call_llm(prompt, user_content)
        plan = self._parse_json(raw, RecoveryPlan)

        if len(plan.steps) > settings.max_recovery_steps:
            plan.steps = plan.steps[: settings.max_recovery_steps]

        return plan

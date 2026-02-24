from __future__ import annotations

import json

from self_healer.agents.base import BaseAgent
from self_healer.models.schemas import DiagnosisResult, LogParseResult
from self_healer.safety.prompts import DIAGNOSTICIAN_PROMPT


class DiagnosticianAgent(BaseAgent):
    name = "diagnostician"

    def run(self, parse_result: LogParseResult) -> DiagnosisResult:
        user_content = (
            "Parsed log analysis:\n"
            f"{json.dumps(parse_result.model_dump(), indent=2)}"
        )
        raw = self._call_llm(DIAGNOSTICIAN_PROMPT, user_content)
        return self._parse_json(raw, DiagnosisResult)

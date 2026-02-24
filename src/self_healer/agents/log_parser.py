from __future__ import annotations

from self_healer.agents.base import BaseAgent
from self_healer.models.schemas import LogParseResult, LogSource
from self_healer.safety.prompts import LOG_PARSER_PROMPT


class LogParserAgent(BaseAgent):
    name = "log_parser"

    def run(self, logs: str, source_hint: LogSource = LogSource.UNKNOWN) -> LogParseResult:
        user_content = f"Source hint: {source_hint.value}\n\n--- LOGS ---\n{logs[:50000]}"
        raw = self._call_llm(LOG_PARSER_PROMPT, user_content)
        return self._parse_json(raw, LogParseResult)

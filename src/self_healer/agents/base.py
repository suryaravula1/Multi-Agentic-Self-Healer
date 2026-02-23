from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import structlog
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from self_healer.config import settings

logger = structlog.get_logger()
T = TypeVar("T", bound=BaseModel)


class AgentError(Exception):
    pass


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, client: OpenAI | None = None) -> None:
        self._client = client

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
            )
        return self._client

    def _call_llm(self, system_prompt: str, user_content: str) -> str:
        logger.info("agent.llm_call", agent=self.name)
        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if not content:
            raise AgentError(f"{self.name}: empty LLM response")
        return content

    def _parse_json(self, raw: str, model: type[T]) -> T:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AgentError(f"{self.name}: invalid JSON from LLM") from exc
        try:
            return model.model_validate(data)
        except ValidationError as exc:
            raise AgentError(f"{self.name}: schema validation failed: {exc}") from exc

    @abstractmethod
    def run(self, **kwargs: Any) -> BaseModel:
        ...

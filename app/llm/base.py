# app/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(ABC):
    @abstractmethod
    def send(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> LLMResponse:
        """Send messages to the LLM and return a normalised response."""
        ...

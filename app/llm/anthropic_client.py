# app/llm/anthropic_client.py
import json
import os
from anthropic import Anthropic
from app.llm.base import LLMClient, LLMResponse, ToolCall


class AnthropicClient(LLMClient):
    def __init__(self) -> None:
        self._client: Anthropic | None = None
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5")

    def _get_client(self) -> Anthropic:
        if self._client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
            self._client = Anthropic(api_key=api_key)
        return self._client

    def send(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> LLMResponse:
        # Anthropic accepts tools in its native {name, description, input_schema} shape directly.
        response = self._get_client().messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=messages,  # type: ignore[arg-type]
            tools=tools if tools else [],  # type: ignore[arg-type]
        )

        text: str | None = None
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,  # already a dict from Anthropic SDK
                    )
                )

        return LLMResponse(text=text, tool_calls=tool_calls)

# app/llm/openai_client.py
import json
import os
from openai import OpenAI
from app.llm.base import LLMClient, LLMResponse, ToolCall
from app.tools.schemas import to_openai_tool


class OpenAIClient(LLMClient):
    def __init__(self) -> None:
        self._client: OpenAI | None = None
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    def _get_client(self) -> OpenAI:
        if self._client is None:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
            self._client = OpenAI(api_key=api_key)
        return self._client

    def send(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> LLMResponse:
        oai_tools = [to_openai_tool(t) for t in tools]

        # OpenAI puts the system prompt as a message with role="system"
        full_messages = [{"role": "system", "content": system}] + messages

        response = self._get_client().chat.completions.create(
            model=self._model,
            messages=full_messages,  # type: ignore[arg-type]
            tools=oai_tools if oai_tools else None,  # type: ignore[arg-type]
            tool_choice="auto" if oai_tools else None,
        )

        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(
            text=message.content,
            tool_calls=tool_calls,
        )

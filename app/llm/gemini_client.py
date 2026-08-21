# app/llm/gemini_client.py
"""
Gemini LLM client using the google-genai SDK.

Message format stored in session.messages for Gemini sessions:
  User text:          {"role": "user",  "parts": [{"text": "..."}]}
  Model text:         {"role": "model", "parts": [{"text": "..."}]}
  Model tool call:    {"role": "model", "parts": [{"function_call": {"name": "...", "args": {...}}}]}
  Tool result:        {"role": "user",  "parts": [{"function_response": {"name": "...", "response": {...}}}]}
"""
import os
from google import genai
from google.genai import types
from app.llm.base import LLMClient, LLMResponse, ToolCall


class GeminiClient(LLMClient):
    def __init__(self) -> None:
        self._client: genai.Client | None = None
        self._model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

    def _get_client(self) -> genai.Client:
        if self._client is None:
            api_key = os.environ.get("GEMINI_API_KEY", "")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
            self._client = genai.Client(api_key=api_key)
        return self._client

    # ------------------------------------------------------------------
    # Convert stored dict messages -> google-genai Content objects
    # ------------------------------------------------------------------
    @staticmethod
    def _to_contents(messages: list[dict]) -> list[types.Content]:
        contents: list[types.Content] = []
        for msg in messages:
            # If we stored the raw Gemini Content object (as a types.Content),
            # use it directly — this preserves thought_signature in function_call parts.
            if "_gemini_raw" in msg:
                contents.append(msg["_gemini_raw"])
                continue

            role = "model" if msg["role"] == "assistant" else msg["role"]
            parts: list[types.Part] = []

            if "content" in msg and isinstance(msg["content"], str):
                parts.append(types.Part.from_text(text=msg["content"]))
            elif "parts" in msg:
                for p in msg["parts"]:
                    if "text" in p:
                        parts.append(types.Part.from_text(text=p["text"]))
                    elif "function_call" in p:
                        fc = p["function_call"]
                        parts.append(
                            types.Part.from_function_call(
                                name=fc["name"],
                                args=fc["args"],
                            )
                        )
                    elif "function_response" in p:
                        fr = p["function_response"]
                        parts.append(
                            types.Part.from_function_response(
                                name=fr["name"],
                                response=fr["response"],
                            )
                        )

            if parts:
                contents.append(types.Content(role=role, parts=parts))
        return contents

    # ------------------------------------------------------------------
    # Convert our provider-neutral tool schemas -> Gemini FunctionDeclarations
    # ------------------------------------------------------------------
    @staticmethod
    def _to_gemini_tools(tools: list[dict]) -> list[types.Tool]:
        if not tools:
            return []
        declarations = [
            types.FunctionDeclaration(
                name=t["name"],
                description=t["description"],
                parameters=t["input_schema"],
            )
            for t in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    # ------------------------------------------------------------------
    def send(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str,
    ) -> LLMResponse:
        contents = self._to_contents(messages)
        gemini_tools = self._to_gemini_tools(tools)

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=gemini_tools if gemini_tools else None,
        )

        import time
        max_retries = 5
        base_delay = 4.0
        response = None

        for attempt in range(max_retries):
            try:
                response = self._get_client().models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as e:
                err_str = str(e)
                if ("RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "quota" in err_str.lower()) and attempt < max_retries - 1:
                    wait_time = base_delay * (attempt + 1)
                    time.sleep(wait_time)
                else:
                    raise

        text: str | None = None
        tool_calls: list[ToolCall] = []

        candidate = response.candidates[0] if response.candidates else None
        if candidate:
            # Store the raw Content so it can be echoed back verbatim next turn.
            self._last_raw_content = candidate.content

            for part in candidate.content.parts:
                if hasattr(part, "text") and part.text:
                    text = part.text
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    # Gemini returns args as a MapComposite; cast to plain dict
                    tool_calls.append(
                        ToolCall(
                            id=f"gemini-{fc.name}-{len(tool_calls)}",
                            name=fc.name,
                            arguments=dict(fc.args),
                        )
                    )
        else:
            self._last_raw_content = None

        return LLMResponse(text=text, tool_calls=tool_calls)

    @property
    def last_raw_content(self) -> types.Content | None:
        """The raw Content from the last send() call — used by main.py to store it verbatim."""
        return getattr(self, "_last_raw_content", None)

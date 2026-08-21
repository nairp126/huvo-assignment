# app/main.py
"""
FastAPI application — routes and the core agent loop.
"""
import json
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app.llm.base import LLMClient, LLMResponse
from app.models import (
    AnalyticsOutput,
    ChatRequest,
    ChatResponse,
    SessionEndRequest,
    SessionStartResponse,
)
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.session_store import create_session, get_session_or_raise, save_session
from app.tools.handlers import dispatch_tool
from app.tools.schemas import TOOLS
from app.analytics import compute_analytics

# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def _build_llm_client() -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "anthropic":
        from app.llm.anthropic_client import AnthropicClient
        return AnthropicClient()
    if provider == "gemini":
        from app.llm.gemini_client import GeminiClient
        return GeminiClient()
    from app.llm.openai_client import OpenAIClient
    return OpenAIClient()


_llm: LLMClient = _build_llm_client()

# ---------------------------------------------------------------------------
# Markdown-stripping safety net (per 06_CODING_RULES.md)
# Applied to every text output before it reaches the client.
# ---------------------------------------------------------------------------
_MD_PATTERNS = [
    re.compile(r"^#{1,6}\s+", re.MULTILINE),          # headings
    re.compile(r"\*{1,3}(.+?)\*{1,3}"),               # bold/italic
    re.compile(r"`{1,3}[^`]*`{1,3}"),                 # inline code / code blocks
    re.compile(r"^\s*[-*+]\s+", re.MULTILINE),        # unordered lists
    re.compile(r"^\s*\d+\.\s+", re.MULTILINE),        # ordered lists
    re.compile(r"[^\x00-\x7F]", re.UNICODE),          # placeholder — keep for emoji strip below
]
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U00002000-\U0000206F]+",
    re.UNICODE,
)


def strip_markdown_artifacts(text: str) -> str:
    """Remove markdown syntax and emojis from agent text output."""
    if not text:
        return text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = _EMOJI_PATTERN.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------
_MAX_TOOL_ITERATIONS = 3

# Message format helpers — keeps provider differences inside the LLM clients
# while the loop stores messages in a neutral dict format.

def _build_tool_result_messages_openai(tool_call_id: str, name: str, result: dict) -> list[dict]:
    """OpenAI expects tool result as a separate message with role='tool'."""
    return [{"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": json.dumps(result)}]


def _build_assistant_tool_call_message_openai(tool_calls) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in tool_calls
        ],
    }


def _build_tool_result_messages_anthropic(tool_call_id: str, result: dict) -> list[dict]:
    """Anthropic expects tool result inside a user message with role='tool'."""
    return [{
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": json.dumps(result),
            }
        ],
    }]


def _build_assistant_tool_call_message_anthropic(response_text: str | None, tool_calls) -> dict:
    content = []
    if response_text:
        content.append({"type": "text", "text": response_text})
    for tc in tool_calls:
        content.append({
            "type": "tool_use",
            "id": tc.id,
            "name": tc.name,
            "input": tc.arguments,
        })
    return {"role": "assistant", "content": content}


# --- Gemini message helpers -------------------------------------------------
# Gemini uses role="model" for assistant turns and stores content as "parts" lists.

def _build_user_message_gemini(text: str) -> dict:
    return {"role": "user", "parts": [{"text": text}]}


def _build_assistant_text_message_gemini(text: str) -> dict:
    return {"role": "model", "parts": [{"text": text}]}


def _build_assistant_tool_call_message_gemini(response_text: str | None, tool_calls) -> dict:
    parts = []
    if response_text:
        parts.append({"text": response_text})
    for tc in tool_calls:
        parts.append({"function_call": {"name": tc.name, "args": tc.arguments}})
    return {"role": "model", "parts": parts}


def _build_tool_result_messages_gemini(tool_name: str, result: dict) -> list[dict]:
    """Gemini tool results go back as a user message with function_response parts."""
    return [{
        "role": "user",
        "parts": [{"function_response": {"name": tool_name, "response": result}}],
    }]


def run_agent_loop(session, user_message: str) -> str:
    """
    Core agent loop (01_ARCHITECTURE.md section 3).
    Appends user message, calls LLM, executes tool calls, loops (max 3x),
    returns final plain-text response.
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    # 1. Append user message in the correct format for this provider
    if provider == "gemini":
        session.messages.append(_build_user_message_gemini(user_message))
    else:
        session.messages.append({"role": "user", "content": user_message})

    final_text = ""
    for iteration in range(_MAX_TOOL_ITERATIONS + 1):
        response: LLMResponse = _llm.send(
            messages=session.messages,
            tools=TOOLS,
            system=SYSTEM_PROMPT,
        )

        if not response.tool_calls:
            # Plain text response — we are done.
            final_text = strip_markdown_artifacts(response.text or "")
            if provider == "gemini":
                session.messages.append(_build_assistant_text_message_gemini(final_text))
            else:
                session.messages.append({"role": "assistant", "content": final_text})
            break

        # 3. Append assistant tool-call message in provider format
        if provider == "anthropic":
            session.messages.append(
                _build_assistant_tool_call_message_anthropic(response.text, response.tool_calls)
            )
        elif provider == "gemini":
            # Store the raw Content object so thought_signature in function_call
            # parts is preserved and echoed back verbatim on the next turn.
            from app.llm.gemini_client import GeminiClient
            raw = _llm.last_raw_content if isinstance(_llm, GeminiClient) else None  # type: ignore[attr-defined]
            if raw is not None:
                session.messages.append({"_gemini_raw": raw})
            else:
                session.messages.append(
                    _build_assistant_tool_call_message_gemini(response.text, response.tool_calls)
                )
        else:
            session.messages.append(
                _build_assistant_tool_call_message_openai(response.tool_calls)
            )

        for tc in response.tool_calls:
            result = dispatch_tool(
                name=tc.name,
                arguments=tc.arguments,
                session_lead_info=session.lead_info,
                session=session,
            )

            # Log every tool call
            session.tool_call_log.append({
                "tool": tc.name,
                "arguments": tc.arguments,
                "result": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            if provider == "anthropic":
                for msg in _build_tool_result_messages_anthropic(tc.id, result):
                    session.messages.append(msg)
            elif provider == "gemini":
                for msg in _build_tool_result_messages_gemini(tc.name, result):
                    session.messages.append(msg)
            else:
                for msg in _build_tool_result_messages_openai(tc.id, tc.name, result):
                    session.messages.append(msg)

        if iteration == _MAX_TOOL_ITERATIONS:
            # Runaway guard: cap reached — return whatever text we have
            final_text = strip_markdown_artifacts(response.text or "I need a moment to process that.")
            break

    return final_text


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Northstar Homes AI Sales Agent")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/session/start", response_model=SessionStartResponse)
async def session_start() -> SessionStartResponse:
    session = create_session()
    save_session(session)
    return SessionStartResponse(session_id=session.session_id)


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    try:
        session = get_session_or_raise(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.ended:
        raise HTTPException(status_code=400, detail="Session has ended")

    # DND short-circuit — deterministic safety net before touching the LLM
    if session.opted_out:
        return ChatResponse(
            response="You have already asked not to be contacted. We have honoured that request and will not reach out again.",
            ended=True,
        )

    response_text = run_agent_loop(session, req.message)
    save_session(session)

    return ChatResponse(response=response_text, ended=session.ended)


@app.post("/session/end")
async def session_end(req: SessionEndRequest) -> dict:
    try:
        session = get_session_or_raise(req.session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    session.ended = True
    save_session(session)
    return {"status": "ended", "session_id": req.session_id}


@app.get("/analytics/{session_id}", response_model=AnalyticsOutput)
async def get_analytics(session_id: str) -> AnalyticsOutput:
    try:
        session = get_session_or_raise(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")

    analytics = compute_analytics(session, _llm)
    save_session(session)  # persist the analytics cache
    return analytics

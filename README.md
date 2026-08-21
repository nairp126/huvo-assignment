# Northstar Homes AI Sales Agent

Built for the Huvo AI Forward Deployed Engineer assignment.

## What this is
A text-based AI sales agent for a fictional real-estate project (Northstar One, Sector 79, Gurugram), backed by FastAPI, that qualifies leads, handles objections, books site visits, and hands off to a human when needed — with a system prompt explicitly designed to also work unmodified on a voice channel.

## How to run
```bash
git clone <repo-url>
cd huvo-assignment
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY or ANTHROPIC_API_KEY, and set LLM_PROVIDER
uvicorn app.main:app --reload
```
Open `http://localhost:8000`.

## Design approach
- **One prompt, two channels.** The system prompt bans markdown, lists, and emojis, forces short turns, and requires numbers to be spoken naturally — rules that make it work unchanged on both chat and a hypothetical voice call, rather than maintaining separate prompts.
- **Actions are tool calls, not prose.** Booking, escalation, opt-out, and callback scheduling all go through explicit tool calls (`book_site_visit`, `escalate_to_human`, `log_dnd_optout`, `schedule_callback`), so the system never has to trust the model's own claim that something happened.
- **Provider-agnostic LLM client.** A single interface supports both OpenAI and Anthropic tool-calling, selected via `LLM_PROVIDER` in `.env` — swapping providers touches no application code.
- **Analytics from ground truth where possible.** Deterministic fields (booking status, opt-out, callback time) are read straight from the tool-call log; only judgment calls (interest level, objections, summary) go back through the model, and even those are forced through a tool call rather than freeform JSON parsing.
- **`strip_markdown_artifacts()` guard.** Every text response is passed through a regex-based markdown stripper before reaching the client — belt-and-suspenders on the voice-safety requirement.
- **DND short-circuit.** If a session has `opted_out=True`, `/chat` returns a fixed compliance message before touching the LLM — a deterministic safety net on top of the prompt instruction.

## Key assumptions
- This is a text-based demo standing in for a voice channel — the prompt is designed to also work read aloud, but no real STT/TTS is wired up.
- Site visit slots are simulated via a small hardcoded table, including one deliberately full slot (2026-08-23 at 11 AM) to exercise the booking-failure path.
- Session state is in-memory and single-process.

## Known limitations
- In-memory sessions do not survive a server restart and will not scale past one process — documented tradeoff, not an oversight. Production would move to Redis-backed sessions and Postgres for persistence.
- No real telephony/STT/TTS integration.
- The qualitative analytics fields (interest level, objections, summary) depend on model judgment, not a fully deterministic rule.

## AI tools used
Antigravity (Google DeepMind) used for architecture planning and code generation. All output reviewed and tested manually.

## Test cases
See `tests/test_cases.md`.

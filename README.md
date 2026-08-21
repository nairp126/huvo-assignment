# Northstar Homes AI Sales Agent

Built for the Huvo AI Assignment.

> [!NOTE]
> **Testing & Model Verification Note**: Due to API budget constraints, all live test suite runs and recorded transcripts were conducted using **Google Gemini (`gemini-3.5-flash-lite`)**. The application is fully provider-agnostic and includes complete, production-ready client adapters for **OpenAI (`gpt-4o`)** and **Anthropic (`claude-opus-4-5`)**, which can be enabled by updating `LLM_PROVIDER` in `.env`.

---

## 1. What This Is

A production-grade, voice-ready conversational AI sales assistant (*Riya*) for a fictional real-estate project (**Northstar One**, Sector 79, Gurugram). Backed by **FastAPI (Python 3.11+)**, the agent qualifies prospective homebuyers, handles price and hesitation objections, schedules callbacks, books site visits with conflict recovery, and executes deterministic human escalations and DND opt-outs.

The core design philosophy is **channel-agnostic by construction**: a single, strictly grounded system prompt operates seamlessly across both text chat and real-time voice call pipelines without forks or modifications.

---

## 2. Architecture & Design Rationale

```
┌──────────────────────────────────────────────────────────┐
│              Browser UI / Voice Gateway                  │
└────────────────────────────┬─────────────────────────────┘
                             │  HTTP POST /chat
                             ▼
┌──────────────────────────────────────────────────────────┐
│                   FastAPI Application                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ DND Deterministic Short-Circuit Guard              │  │
│  └─────────────────────────┬──────────────────────────┘  │
│                            ▼                             │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Multi-Turn Agent Loop (Max 3 Tool Iterations)      │  │
│  └───────┬───────────────────────────────▲────────────┘  │
│          │ Messages + Tools              │ Tool Results  │
│          ▼                               │               │
│  ┌───────────────┐               ┌───────┴────────────┐  │
│  │  LLM Client   │               │   Tool Handlers    │  │
│  │ (OpenAI /     │               │ - capture_lead     │  │
│  │  Anthropic /  │               │ - check_avail      │  │
│  │  Gemini)      │               │ - book_visit       │  │
│  └───────────────┘               │ - callback / dnd   │  │
│                                  │ - human_escalate   │  │
│                                  └────────────────────┘  │
│                            │                             │
│                            ▼                             │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Regex Voice Sanitizer (strip_markdown_artifacts)   │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────┘
                             │  State Update
                             ▼
┌──────────────────────────────────────────────────────────┐
│     In-Memory Session Store (Lead Info + Tool Log)       │
└──────────────────────────────────────────────────────────┘
```

### Core Architectural Decisions

1. **One Prompt, Two Channels**: The system prompt prohibits markdown, headers, bullet points, and emojis while enforcing short turns (1–3 sentences) and phonetic number rendering (*"one crore thirty-five lakh"*). A secondary regex sanitizer (`strip_markdown_artifacts`) provides defense-in-depth on outgoing text.
2. **Actions Are Tool Calls, Not Prose**: State mutations (qualifying leads, checking slots, confirming bookings, logging DND, and human escalation) are executed exclusively through structured tool calls.
3. **Provider-Agnostic LLM Layer**: Unified `LLMClient` abstraction supporting **OpenAI (`gpt-4o`)**, **Anthropic (`claude-opus-4-5`)**, and **Google Gemini (`gemini-3.5-flash-lite`)** via native tool-calling. Swapping providers requires only modifying `LLM_PROVIDER` in `.env`.
4. **Hybrid Analytics Pipeline**: Deterministic fields (`configuration`, `budget`, `site_visit_status`, `dnd_opt_out`, `follow_up`) are extracted directly from `session.tool_call_log` ground truth. Qualitative fields (`interest_level`, `summary`, `objections_raised`) are derived via a secondary LLM call forced through the `emit_analytics` tool.

---

## 3. How to Run

### Prerequisites
- Python 3.11+
- API key for OpenAI, Anthropic, or Google Gemini

### Installation & Startup

```bash
# 1. Clone the repository
git clone <repo-url>
cd huvo-assignment

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and set your API key and provider (e.g. LLM_PROVIDER=gemini)

# 4. Start the FastAPI server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **`http://localhost:8000`** in your browser to interact with Riya and inspect real-time analytics.

---

## 4. API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/session/start` | Initializes a new `SessionState` and returns `{ session_id }`. |
| `POST` | `/chat` | Core agent loop. Checks DND status, calls LLM, dispatches tools, and returns `{ response, ended }`. |
| `POST` | `/session/end` | Marks a session as concluded. |
| `GET` | `/analytics/{session_id}` | Computes and returns structured `AnalyticsOutput` (cached per session). |
| `GET` | `/` | Serves the lightweight web chat client and live analytics viewer. |

---

## 5. Tool Schemas Overview

The agent is equipped with 6 operational tools:
- `capture_lead_info(field, value)`: Progressively stores lead qualification attributes (`configuration`, `budget`, `purpose`, `timeline`, `name`, `phone`).
- `check_site_visit_availability(date, time_slot)`: Checks the schedule table. Deliberately simulates slot congestion (*23 August 11 AM*) to exercise alternate slot suggestions (*3 PM Saturday* or *11 AM Sunday*).
- `book_site_visit(date, time_slot, customer_name, customer_phone)`: Issues a confirmed booking reference (`NSH-XXXXXXXX`).
- `schedule_callback(preferred_datetime, reason)`: Records customer-requested callback times.
- `log_dnd_optout(reason)`: Marks session as opted-out and engages deterministic safety filters.
- `escalate_to_human(reason, details)`: Creates an escalation ticket (`ESC-XXXXXX`) for complex negotiation, complaints, or explicit representative requests.

---

## 6. Key Assumptions & Production Trade-offs

| Component | Assignment Implementation | Production Architecture |
|---|---|---|
| **Session State** | In-memory Python dictionary | Redis for distributed multi-process session caching |
| **Data Persistence** | Session duration | PostgreSQL for lead records, bookings, and transcript logs |
| **Voice Channel** | Voice-first text generation protocol | WebRTC / LiveKit / Twilio telephony with streaming STT (Deepgram) & TTS (Cartesia/ElevenLabs) |
| **Callback Execution** | Tool logging & state flag | Asynchronous job queues (Celery / Temporal) with CRM webhooks |
| **Analytics Storage** | On-demand computation with in-memory caching | Kafka / EventBridge stream to Snowflake / ClickHouse data warehouse |

---

## 7. Test Cases & Verification

All 9 required evaluation scenarios (Happy Path, Price Objection, Callback, DND Opt-Out, Unknown Inquiries, Booking Failure Recovery, Human Handoff, Uninterested Exit, and Mid-Conversation Code-Switching) were executed against the live server. Verbatim transcripts and pass verifications are documented in [`tests/test_cases.md`](tests/test_cases.md).

---

## 8. AI Tools Used

Antigravity (Google DeepMind) was utilized for architecture planning, test suite execution, and code generation. All prompt logic, tool schemas, and backend implementations were manually validated and tested against live LLM providers.


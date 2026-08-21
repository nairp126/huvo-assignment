# app/analytics.py
"""
Analytics derivation per 04_ANALYTICS_SPEC.md.
- Deterministic fields: read straight from tool_call_log.
- Qualitative fields (interest_level, objections_raised, summary):
  one second LLM call via emit_analytics tool.
"""
import json
from app.models import SessionState, AnalyticsOutput
from app.tools.schemas import EMIT_ANALYTICS_TOOL, to_openai_tool
from app.prompts.system_prompt import SYSTEM_PROMPT


def _derive_deterministic(session: SessionState) -> dict:
    """Read all deterministic fields from tool_call_log."""
    log = session.tool_call_log

    # Lead info
    lead = session.lead_info
    config = lead.get("configuration", "undecided")
    if "2" in config.lower():
        config_interest = "2BHK"
    elif "3" in config.lower():
        config_interest = "3BHK"
    else:
        config_interest = "undecided"

    purpose_raw = lead.get("purpose", "").lower()
    if "invest" in purpose_raw:
        purpose = "investment"
    elif purpose_raw in ("own use", "end use", "end-use", "self use", "self"):
        purpose = "end-use"
    elif purpose_raw:
        purpose = "end-use"
    else:
        purpose = "unknown"

    # Site visit
    site_visit_status = "not_offered"
    site_visit_datetime: str | None = None
    for entry in log:
        if entry["tool"] == "book_site_visit":
            result = entry.get("result", {})
            if result.get("status") == "confirmed":
                site_visit_status = "booked"
                site_visit_datetime = f"{result.get('date', '')} {result.get('time_slot', '')}".strip()
            else:
                site_visit_status = "failed"
        elif entry["tool"] == "check_site_visit_availability" and site_visit_status == "not_offered":
            # Availability was checked — visit was at least offered
            result = entry.get("result", {})
            if not result.get("available", True):
                site_visit_status = "failed"
            else:
                site_visit_status = "declined"  # available but not booked yet

    # Callback / follow-up
    follow_up_required = False
    follow_up_datetime: str | None = None
    for entry in log:
        if entry["tool"] == "schedule_callback":
            follow_up_required = True
            follow_up_datetime = entry.get("result", {}).get("preferred_datetime")

    # DND
    dnd_opt_out = session.opted_out or any(e["tool"] == "log_dnd_optout" for e in log)

    # Escalation
    escalated_to_human = False
    escalation_reason: str | None = None
    for entry in log:
        if entry["tool"] == "escalate_to_human":
            escalated_to_human = True
            escalation_reason = entry.get("arguments", {}).get("reason")

    return {
        "configuration_interest": config_interest,
        "budget_indicated": lead.get("budget"),
        "purpose": purpose,
        "timeline": lead.get("timeline"),
        "site_visit_status": site_visit_status,
        "site_visit_datetime": site_visit_datetime,
        "follow_up_required": follow_up_required,
        "follow_up_datetime": follow_up_datetime,
        "dnd_opt_out": dnd_opt_out,
        "escalated_to_human": escalated_to_human,
        "escalation_reason": escalation_reason,
    }


def _derive_qualitative(session: SessionState, llm_client) -> dict:
    """
    Second LLM call forced through emit_analytics tool so it cannot
    return malformed JSON or commentary.
    """
    # Build clean human-readable transcript
    transcript_lines = []
    for msg in session.messages:
        if "_gemini_raw" in msg:
            continue
        role = msg.get("role", "unknown")
        if "content" in msg and msg["content"]:
            transcript_lines.append(f"{role.upper()}: {msg['content']}")
        elif "parts" in msg:
            for p in msg["parts"]:
                if "text" in p:
                    transcript_lines.append(f"{role.upper()}: {p['text']}")

    transcript_text = "\n".join(transcript_lines)
    tool_log_text = json.dumps(session.tool_call_log, ensure_ascii=False)

    prompt_message = {
        "role": "user",
        "content": (
            "Analyse the following sales conversation transcript and tool call log "
            "for a real-estate project (Northstar One, Gurugram). "
            "Call emit_analytics with your assessment.\n\n"
            f"TRANSCRIPT:\n{transcript_text}\n\n"
            f"TOOL CALL LOG:\n{tool_log_text}"
        ),
    }

    from app.llm.base import LLMResponse
    response: LLMResponse = llm_client.send(
        messages=[prompt_message],
        tools=[EMIT_ANALYTICS_TOOL],
        system="You are an analytics assistant. Call emit_analytics with your assessment.",
    )

    # The model MUST use the tool; extract the arguments.
    for tc in response.tool_calls:
        if tc.name == "emit_analytics":
            return {
                "interest_level": tc.arguments.get("interest_level", "cold"),
                "objections_raised": tc.arguments.get("objections_raised", []),
                "summary": tc.arguments.get("summary", ""),
            }

    # Fallback if the model didn't use the tool (should not happen in practice)
    return {
        "interest_level": "cold",
        "objections_raised": [],
        "summary": response.text or "No summary available.",
    }


def compute_analytics(session: SessionState, llm_client) -> AnalyticsOutput:
    """Build and cache AnalyticsOutput for a session."""
    if session.analytics_cache is not None:
        return AnalyticsOutput(**session.analytics_cache)

    deterministic = _derive_deterministic(session)
    qualitative = _derive_qualitative(session, llm_client)

    output = AnalyticsOutput(
        session_id=session.session_id,
        **deterministic,
        **qualitative,
    )

    # Cache on session so repeated GET calls don't re-invoke the LLM
    session.analytics_cache = output.model_dump()
    return output

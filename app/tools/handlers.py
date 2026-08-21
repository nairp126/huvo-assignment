# app/tools/handlers.py
"""
Tool execution logic. All handlers are pure functions with typed inputs/outputs,
independently testable without spinning up FastAPI.
"""
import uuid
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Site-visit slot table
# Keyed by "date|time_slot" (normalised to lowercase).
# DELIBERATELY includes one full slot to exercise the booking-failure path.
# ---------------------------------------------------------------------------
_FULL_SLOTS: set[str] = {
    "2026-08-23|11 am",   # Saturday 11 AM — intentionally unavailable
}

_ALTERNATIVE_SLOTS: list[dict] = [
    {"date": "2026-08-23", "time_slot": "3 PM"},
    {"date": "2026-08-24", "time_slot": "11 AM"},
    {"date": "2026-08-25", "time_slot": "11 AM"},
    {"date": "2026-08-25", "time_slot": "4 PM"},
]


def _slot_key(date: str, time_slot: str) -> str:
    return f"{date.strip().lower()}|{time_slot.strip().lower()}"


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_capture_lead_info(
    session_lead_info: dict,
    field: str,
    value: str,
) -> dict:
    """Update the session lead_info dict and return a confirmation."""
    session_lead_info[field] = value
    return {"status": "recorded", "field": field, "value": value}


def handle_check_site_visit_availability(date: str, time_slot: str) -> dict:
    """Return availability plus two alternative slots."""
    key = _slot_key(date, time_slot)
    available = key not in _FULL_SLOTS
    # Return alternatives that are NOT the requested slot itself.
    alternatives = [
        s for s in _ALTERNATIVE_SLOTS
        if _slot_key(s["date"], s["time_slot"]) != key
    ][:2]
    return {"available": available, "alternatives": alternatives}


def handle_book_site_visit(
    date: str,
    time_slot: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Simulate confirming a booking. Always succeeds if called (availability check is upstream)."""
    booking_id = f"NSH-{uuid.uuid4().hex[:8].upper()}"
    return {
        "status": "confirmed",
        "booking_id": booking_id,
        "date": date,
        "time_slot": time_slot,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
    }


def handle_schedule_callback(preferred_datetime: str, reason: str = "") -> dict:
    return {
        "status": "scheduled",
        "preferred_datetime": preferred_datetime,
        "reason": reason,
    }


def handle_log_dnd_optout(reason: str = "") -> dict:
    """
    Sets opted_out on the session — the caller (agent loop in main.py) is
    responsible for writing session.opted_out = True after seeing this result.
    """
    return {
        "status": "recorded",
        "message": "Customer opted out. No further contact.",
        "reason": reason,
    }


def handle_escalate_to_human(reason: str, details: str = "") -> dict:
    ticket_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
    return {
        "status": "escalated",
        "ticket_id": ticket_id,
        "reason": reason,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch_tool(
    name: str,
    arguments: dict,
    session_lead_info: dict,
    session: object,  # SessionState — typed loosely to avoid circular import
) -> dict:
    """Route a tool call to its handler and return the result dict."""
    if name == "capture_lead_info":
        return handle_capture_lead_info(
            session_lead_info,
            field=arguments["field"],
            value=arguments["value"],
        )
    elif name == "check_site_visit_availability":
        return handle_check_site_visit_availability(
            date=arguments["date"],
            time_slot=arguments["time_slot"],
        )
    elif name == "book_site_visit":
        return handle_book_site_visit(
            date=arguments["date"],
            time_slot=arguments["time_slot"],
            customer_name=arguments["customer_name"],
            customer_phone=arguments["customer_phone"],
        )
    elif name == "schedule_callback":
        return handle_schedule_callback(
            preferred_datetime=arguments["preferred_datetime"],
            reason=arguments.get("reason", ""),
        )
    elif name == "log_dnd_optout":
        result = handle_log_dnd_optout(reason=arguments.get("reason", ""))
        session.opted_out = True  # deterministic safety net
        return result
    elif name == "escalate_to_human":
        return handle_escalate_to_human(
            reason=arguments["reason"],
            details=arguments.get("details", ""),
        )
    else:
        return {"error": f"Unknown tool: {name}"}

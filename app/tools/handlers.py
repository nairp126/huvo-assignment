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


def _is_full_slot(date: str, time_slot: str) -> bool:
    d = date.strip().lower()
    t = time_slot.strip().lower()
    # Matches '2026-08-23|11 am', '23 august|11 am', 'saturday 23 august|11 am', etc.
    is_aug_23 = ("2026-08-23" in d) or ("23" in d and "aug" in d)
    is_11_am = ("11" in t and ("am" in t or "subah" in t or "morning" in t)) or (t == "11") or ("11:00" in t)
    return is_aug_23 and is_11_am


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
    available = not _is_full_slot(date, time_slot)
    # Return 2 distinct alternatives from the predefined table
    alternatives = [
        s for s in _ALTERNATIVE_SLOTS
        if not _is_full_slot(s["date"], s["time_slot"])
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
    try:
        if name == "capture_lead_info":
            field = str(arguments.get("field", ""))
            value = str(arguments.get("value", ""))
            if not field or not value:
                return {"status": "error", "message": "Missing required field or value"}
            return handle_capture_lead_info(session_lead_info, field=field, value=value)
        elif name == "check_site_visit_availability":
            date = str(arguments.get("date", ""))
            time_slot = str(arguments.get("time_slot", ""))
            return handle_check_site_visit_availability(date=date, time_slot=time_slot)
        elif name == "book_site_visit":
            date = str(arguments.get("date", ""))
            time_slot = str(arguments.get("time_slot", ""))
            customer_name = str(arguments.get("customer_name", "Customer"))
            customer_phone = str(arguments.get("customer_phone", ""))
            return handle_book_site_visit(
                date=date,
                time_slot=time_slot,
                customer_name=customer_name,
                customer_phone=customer_phone,
            )
        elif name == "schedule_callback":
            preferred_datetime = str(arguments.get("preferred_datetime", ""))
            reason = str(arguments.get("reason", ""))
            return handle_schedule_callback(
                preferred_datetime=preferred_datetime,
                reason=reason,
            )
        elif name == "log_dnd_optout":
            result = handle_log_dnd_optout(reason=str(arguments.get("reason", "")))
            session.opted_out = True  # deterministic safety net
            return result
        elif name == "escalate_to_human":
            reason = str(arguments.get("reason", "requested_human"))
            details = str(arguments.get("details", ""))
            return handle_escalate_to_human(
                reason=reason,
                details=details,
            )
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        return {"status": "error", "error": f"Tool execution failed: {str(e)}"}


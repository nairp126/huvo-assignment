# app/tools/schemas.py
"""
Tool schemas in Anthropic-native shape {name, description, input_schema}.
openai_client.py re-wraps these via to_openai_tool(); no duplicate definitions.
"""
from typing import Any


def to_openai_tool(tool: dict) -> dict:
    """Convert Anthropic-shape tool schema to OpenAI function-calling shape."""
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "capture_lead_info",
        "description": "Record a piece of qualifying information the customer has shared.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["configuration", "budget", "purpose", "timeline", "name", "phone"],
                },
                "value": {"type": "string"},
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "check_site_visit_availability",
        "description": "Check whether a requested date/time slot for a site visit is available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "e.g. '2026-08-23' or 'this Saturday'",
                },
                "time_slot": {
                    "type": "string",
                    "description": "e.g. '11 AM' or 'afternoon'",
                },
            },
            "required": ["date", "time_slot"],
        },
    },
    {
        "name": "book_site_visit",
        "description": "Confirm a site visit booking once a slot is known to be available.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "time_slot": {"type": "string"},
                "customer_name": {"type": "string"},
                "customer_phone": {"type": "string"},
            },
            "required": ["date", "time_slot", "customer_name", "customer_phone"],
        },
    },
    {
        "name": "schedule_callback",
        "description": "Record a preferred callback time when the customer asks to be contacted later.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_datetime": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["preferred_datetime"],
        },
    },
    {
        "name": "log_dnd_optout",
        "description": "Record that the customer has asked not to be contacted again.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "optional — why they opted out",
                },
            },
            "required": [],
        },
    },
    {
        "name": "escalate_to_human",
        "description": "Hand the conversation off to a human sales representative.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": [
                        "requested_human",
                        "complaint",
                        "complex_negotiation",
                        "repeated_confusion",
                        "other",
                    ],
                },
                "details": {"type": "string"},
            },
            "required": ["reason"],
        },
    },
]

# Analytics-only tool — not exposed to the sales agent during conversation.
EMIT_ANALYTICS_TOOL: dict[str, Any] = {
    "name": "emit_analytics",
    "description": "Return structured analytics for a completed sales conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "interest_level": {
                "type": "string",
                "enum": ["hot", "warm", "cold"],
            },
            "objections_raised": {
                "type": "array",
                "items": {"type": "string"},
            },
            "summary": {"type": "string"},
        },
        "required": ["interest_level", "objections_raised", "summary"],
    },
}

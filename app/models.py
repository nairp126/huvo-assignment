# app/models.py
from pydantic import BaseModel, Field
from typing import Any


class SessionState(BaseModel):
    session_id: str
    messages: list[dict] = Field(default_factory=list)
    lead_info: dict[str, str] = Field(default_factory=dict)
    tool_call_log: list[dict[str, Any]] = Field(default_factory=list)
    opted_out: bool = False
    ended: bool = False
    analytics_cache: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str
    ended: bool


class SessionStartResponse(BaseModel):
    session_id: str


class SessionEndRequest(BaseModel):
    session_id: str


class AnalyticsOutput(BaseModel):
    session_id: str
    configuration_interest: str  # "2BHK" | "3BHK" | "undecided"
    budget_indicated: str | None
    purpose: str  # "end-use" | "investment" | "unknown"
    timeline: str | None
    interest_level: str  # "hot" | "warm" | "cold"
    objections_raised: list[str]
    site_visit_status: str  # "booked" | "failed" | "not_offered" | "declined"
    site_visit_datetime: str | None
    follow_up_required: bool
    follow_up_datetime: str | None
    dnd_opt_out: bool
    escalated_to_human: bool
    escalation_reason: str | None
    summary: str

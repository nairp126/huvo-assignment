# app/session_store.py
import uuid
from app.models import SessionState

_store: dict[str, SessionState] = {}


def create_session() -> SessionState:
    session_id = str(uuid.uuid4())
    session = SessionState(session_id=session_id)
    _store[session_id] = session
    return session


def get_session(session_id: str) -> SessionState | None:
    return _store.get(session_id)


def get_session_or_raise(session_id: str) -> SessionState:
    session = get_session(session_id)
    if session is None:
        raise KeyError(f"Session not found: {session_id}")
    return session


def save_session(session: SessionState) -> None:
    _store[session.session_id] = session

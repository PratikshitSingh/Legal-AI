"""API Gateway stub for Streamlit MVP.

Production (per architecture diagram): HTTPS routing, JWT validation, forwards
legal queries with session_id to the query orchestrator.
"""

from agent import LegalChat

import db
from auth import ensure_db, get_current_user

_chats: dict[str, LegalChat] = {}


def validate_jwt(token: str | None) -> bool:
    # MVP: accept all requests; production validates JWT from Auth Service
    return True


def get_chat(session_id: str, *, hydrate: bool = True) -> LegalChat:
    if session_id not in _chats:
        chat = LegalChat(session_id=session_id)
        if hydrate:
            messages = db.get_session_messages(session_id)
            if messages:
                chat.load_history_from_db(messages)
        _chats[session_id] = chat
    return _chats[session_id]


def clear_chat_cache(session_id: str | None = None) -> None:
    if session_id:
        _chats.pop(session_id, None)
    else:
        _chats.clear()


def route_query(
    question: str,
    session_id: str,
    jwt: str | None = None,
) -> str:
    """Route user query through RAG pipeline with tracing.
    
    Best practice: Include user context (from get_current_user) in tracing
    for audit trails and user-level analytics.
    
    Args:
        question: User's question
        session_id: Session identifier for grouping interactions
        jwt: JWT token (MVP: unused; production validates auth)
    
    Returns:
        Assistant's answer with tracing recorded in LangFuse
    """
    if not validate_jwt(jwt):
        raise PermissionError("Invalid or missing JWT")
    
    ensure_db()
    db.log_message(session_id, "user", question)
    
    chat = get_chat(session_id)
    user_id = get_current_user() or "anonymous"
    
    # Pass user_id to include in tracing context
    answer = chat.ask(question, user_id=user_id)
    
    db.log_message(session_id, "assistant", answer)
    return answer

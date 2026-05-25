"""API Gateway stub for Streamlit MVP.

Production (per architecture diagram): HTTPS routing, JWT validation, forwards
legal queries with session_id to the query orchestrator.
"""

from agent import LegalChat

import db
import jwt_utils
from auth import ensure_db, get_current_user, get_current_user_id

_chats: dict[str, LegalChat] = {}


def validate_jwt(token: str | None) -> tuple[str | None, bool]:
    """
    Validate JWT access token.
    
    Args:
        token: JWT token string or None
    
    Returns:
        (user_id, is_valid) tuple
        - user_id: UUID of user if valid, None otherwise
        - is_valid: True if token is valid, False otherwise
    
    Example:
        user_id, is_valid = validate_jwt(token)
        if not is_valid:
            raise PermissionError("Invalid token")
    """
    if not token:
        return None, False

    try:
        user_id = jwt_utils.validate_access_token(token)
        return user_id, True
    except jwt_utils.jwt.InvalidTokenError:
        return None, False


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
    
    Best practice: Include user context (from JWT token) in tracing
    for audit trails and user-level analytics.
    
    Args:
        question: User's question
        session_id: Session identifier for grouping interactions
        jwt: JWT access token (validates user owns this session)
    
    Returns:
        Assistant's answer with tracing recorded in LangFuse
    
    Raises:
        PermissionError: If JWT is invalid
    """
    # Validate JWT token
    user_id, is_valid = validate_jwt(jwt)
    if not is_valid:
        raise PermissionError("Invalid or missing JWT token")
    
    # Verify user owns the session
    session_user_id = db.get_session_user_id(session_id)
    if session_user_id and session_user_id != user_id:
        raise PermissionError("User does not own this session")
    
    ensure_db()
    db.log_message(session_id, "user", question)
    
    chat = get_chat(session_id)
    
    # Pass user_id to include in tracing context
    answer = chat.ask(question, user_id=user_id or "anonymous")
    
    db.log_message(session_id, "assistant", answer)
    return answer

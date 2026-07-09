"""Chat service: validates the caller, owns agent instances, routes queries.

This is the seam between the UI and the RAG agent — JWT validation, session
ownership checks, message persistence, and agent caching all happen here so
pages never talk to the agent or the message log directly.
"""

from legal_ai import db
from legal_ai.agent.agent import LegalChat
from legal_ai.auth import jwt_utils

# Process-global agent cache, keyed by chat session. Under Streamlit this is
# shared by every user of the server process; entries are evicted only via
# clear_chat_cache (sign-out, new chat, chat switch).
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
    jurisdiction_ids: list[str] | None = None,
) -> str:
    """Route user query through RAG pipeline with optional jurisdiction filtering.

    Best practice: Include user context (from JWT token) in tracing
    for audit trails and user-level analytics.

    Args:
        question: User's question
        session_id: Session identifier for grouping interactions
        jwt: JWT access token (validates user owns this session)
        jurisdiction_ids: Optional list of jurisdiction IDs to filter results by.
                         If None, searches all jurisdictions.

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

    db.ensure_db()

    # Hydrate the chat from the DB BEFORE logging the new question; otherwise
    # the question is loaded into history from the DB and then added again by
    # the chain, duplicating it in the LLM context on resumed sessions.
    chat = get_chat(session_id)
    db.add_session_message(session_id, "user", question)

    # If jurisdiction_ids provided, pass jurisdiction context to the chat
    if jurisdiction_ids:
        # Note: full retriever-level filtering would be integrated into
        # LegalChat; for now the jurisdiction context is appended to the
        # question as a prompt annotation.
        context_info = f"[Filtered to jurisdictions: {', '.join(jurisdiction_ids)}]"
        enhanced_question = f"{question}\n{context_info}"
        answer = chat.ask(enhanced_question, user_id=user_id or "anonymous")
    else:
        # Pass user_id to include in tracing context
        answer = chat.ask(question, user_id=user_id or "anonymous")

    db.add_session_message(session_id, "assistant", answer)
    return answer

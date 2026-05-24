"""Auth layer: Streamlit sign-in + Neon Postgres session persistence."""

import uuid

import streamlit as st

import db

_db_initialized = False


def ensure_db() -> None:
    global _db_initialized
    if not _db_initialized:
        db.init_db()
        _db_initialized = True


def is_signed_in() -> bool:
    return bool(st.session_state.get("legal_ai_user"))


def get_current_user() -> str | None:
    return st.session_state.get("legal_ai_user")


def sign_in(username: str) -> None:
    name = (username or "").strip()
    if not name:
        raise ValueError("Enter a username to continue.")
    st.session_state.legal_ai_user = name
    ensure_db()


def sign_out() -> None:
    for key in (
        "legal_ai_user",
        "legal_ai_session_id",
        "messages",
        "selected_session_id",
    ):
        st.session_state.pop(key, None)


def get_or_create_session_id() -> str:
    ensure_db()
    if "legal_ai_session_id" not in st.session_state:
        st.session_state.legal_ai_session_id = str(uuid.uuid4())
    db.upsert_session(
        st.session_state.legal_ai_session_id,
        get_current_user() or "anonymous",
    )
    return st.session_state.legal_ai_session_id


def start_new_chat() -> str:
    """New session for the current user; clears in-memory UI messages."""
    session_id = str(uuid.uuid4())
    st.session_state.legal_ai_session_id = session_id
    st.session_state.messages = []
    st.session_state.selected_session_id = session_id
    user = get_current_user()
    if user:
        db.upsert_session(session_id, user)
    return session_id


def switch_to_session(session_id: str) -> None:
    st.session_state.legal_ai_session_id = session_id
    st.session_state.selected_session_id = session_id
    user = get_current_user()
    if user:
        db.upsert_session(session_id, user)


def list_past_chats() -> list[dict]:
    user = get_current_user()
    if not user:
        return []
    ensure_db()
    return db.get_user_sessions(user)

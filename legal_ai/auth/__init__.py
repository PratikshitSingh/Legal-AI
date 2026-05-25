"""Authentication package."""

__all__ = [
    "ensure_db",
    "is_signed_in",
    "get_current_user_id",
    "get_current_user",
    "set_auth_tokens",
    "request_magic_link",
    "verify_magic_link_token",
    "refresh_access_token_if_needed",
    "sign_out",
    "get_or_create_session_id",
    "start_new_chat",
    "switch_to_session",
    "list_past_chats",
]

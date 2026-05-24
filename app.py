import logging
import os

logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import streamlit as ST

import utils as Utils
from auth import (
    get_or_create_session_id,
    get_current_user,
    is_signed_in,
    list_past_chats,
    sign_in,
    sign_out,
    start_new_chat,
    switch_to_session,
)
from db import get_session_messages
from gateway import clear_chat_cache, route_query


CHAT_UI_KEY = "chat1"


def load_ui_messages(session_id: str) -> None:
    rows = get_session_messages(session_id)
    ST.session_state.messages = [
        {"id": CHAT_UI_KEY, "role": row["role"], "content": row["content"]}
        for row in rows
    ]


def render_sign_in() -> None:
    ST.subheader("Sign in")
    ST.caption("Your username scopes past chats — only your sessions are listed.")
    with ST.form("sign_in_form"):
        username = ST.text_input("Username", placeholder="e.g. alex@firm.com")
        submitted = ST.form_submit_button("Continue")
    if submitted:
        try:
            sign_in(username)
            start_new_chat()
            ST.rerun()
        except ValueError as e:
            ST.error(str(e))


def render_sidebar(session_id: str) -> None:
    user = get_current_user()
    with ST.sidebar:
        ST.subheader("Account")
        ST.text(f"Signed in as {user}")
        if ST.button("Sign out", use_container_width=True):
            clear_chat_cache()
            sign_out()
            ST.rerun()

        ST.divider()
        ST.subheader("Chats")
        if ST.button("New chat", use_container_width=True):
            clear_chat_cache()
            start_new_chat()
            ST.rerun()

        past = list_past_chats()
        if not past:
            ST.caption("No past chats yet.")
            return

        for chat in past:
            sid = chat["session_id"]
            preview = (chat.get("last_message") or "Empty chat")[:60]
            label = f"{preview}…" if len(preview) >= 60 else preview
            is_active = sid == session_id
            if ST.button(
                label,
                key=f"session_{sid}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                if sid != session_id:
                    clear_chat_cache(sid)
                    switch_to_session(sid)
                    load_ui_messages(sid)
                    ST.rerun()

        chroma_mode = "Chroma Cloud" if Utils.use_chroma_cloud() else "local"
        ST.divider()
        ST.caption(f"Session: {session_id[:8]}… · Vector store: {chroma_mode}")


def create_chat(chat_id: str, session_id: str) -> None:
    chat = ST.container()

    if "messages" not in ST.session_state:
        ST.session_state.messages = []

    for message in ST.session_state.messages:
        if message["id"] == chat_id:
            chat.chat_message(message["role"]).write(message["content"])

    if prompt := ST.chat_input(
        placeholder="Ask me about AI legal stuff in the EU",
        key=chat_id,
    ):
        chat.chat_message("user").write(prompt)
        with ST.spinner("Wait for it..."):
            assistant_response = route_query(
                question=prompt,
                session_id=session_id,
                jwt=None,
            )
            chat.chat_message("assistant").write(assistant_response)

        ST.session_state.messages.append({"id": chat_id, "role": "user", "content": prompt})
        ST.session_state.messages.append(
            {"id": chat_id, "role": "assistant", "content": assistant_response}
        )


if __name__ == "__main__":
    ST.set_page_config(page_title="Legal-AI", page_icon="⚖️")
    
    # Initialize tracing (LangFuse)
    Utils.setup_langfuse_tracing()
    
    ST.title("Legal-AI")
    ST.caption("EU AI Act RAG assistant — multi-turn conversational retrieval")

    if not is_signed_in():
        render_sign_in()
        ST.stop()

    if not Utils.chroma_collection_has_documents():
        ST.error(
            "Vector store is empty. Run offline ingest first:\n\n"
            "```bash\npython embed.py\n```\n\n"
            "Requires `GEMINI_API_KEY` and Chroma credentials in `.env`."
        )
        ST.stop()

    if "legal_ai_session_id" not in ST.session_state:
        start_new_chat()

    session_id = get_or_create_session_id()
    if "messages" not in ST.session_state:
        load_ui_messages(session_id)

    render_sidebar(session_id)
    create_chat(CHAT_UI_KEY, session_id)

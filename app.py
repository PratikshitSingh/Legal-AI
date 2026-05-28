"""Legal-AI Streamlit Application - Main Entry Point."""

import logging
import os

logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

import streamlit as ST

from legal_ai.core import config, utils
from legal_ai.auth.auth import (
    get_or_create_session_id,
    get_current_user,
    get_current_user_id,
    get_current_access_token,
    is_signed_in,
    list_past_chats,
    refresh_access_token_if_needed,
    request_magic_link,
    set_auth_tokens,
    sign_out,
    start_new_chat,
    switch_to_session,
    verify_magic_link_token,
    init_auth,
)
from legal_ai.db.db import get_session_messages, get_jurisdiction_tree, get_user_jurisdictions, update_user_jurisdictions
from legal_ai.services.gateway import clear_chat_cache, route_query


CHAT_UI_KEY = "chat1"


def load_ui_messages(session_id: str) -> None:
    rows = get_session_messages(session_id)
    ST.session_state.messages = [
        {"id": CHAT_UI_KEY, "role": row["role"], "content": row["content"]}
        for row in rows
    ]


def render_sign_in() -> None:
    """Render passwordless email sign-in form."""
    ST.subheader("Sign in to Legal AI")
    ST.caption("Enter your email to receive a magic link for passwordless sign-in.")
    
    with ST.form("magic_link_form"):
        email = ST.text_input(
            "Email",
            placeholder="your.email@law-firm.com",
            help="We'll send you a link to sign in securely"
        )
        submitted = ST.form_submit_button("Send Magic Link")
    
    if submitted:
        if not email:
            ST.error("Please enter an email address.")
            return
        
        result = request_magic_link(email)
        if result["status"] == "success":
            ST.success(result["message"])
            ST.info("Check your email for the sign-in link. It expires in 15 minutes.")
        else:
            ST.error(result["message"])


def render_magic_link_verification(email: str, token: str) -> None:
    """Render magic link verification UI."""
    ST.info(f"🔐 Verifying your sign-in link for {email}...")
    
    with ST.spinner("Checking your magic link..."):
        result = verify_magic_link_token(email, token)
    
    if result["status"] == "success":
        # Store the authenticated session and persist it in the browser cookie.
        set_auth_tokens(
            user_id=result["user_id"],
            email=result["email"],
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            role=result.get("role", "viewer"),
            full_name=result.get("full_name"),
            firm=result.get("firm"),
        )
        ST.query_params.clear()
        ST.success(f"✅ Welcome, {result['email']}!")
        start_new_chat(result["user_id"])
        ST.balloons()
        # Rerun so the authenticated app state renders without the verification branch.
        ST.rerun()
    else:
        error_msg = result.get('message', 'Invalid or expired link. Please request a new one.')
        ST.error(f"❌ {error_msg}")
        ST.divider()
        if ST.button("← Back to Sign In"):
            ST.rerun()


def render_magic_link_email_prompt(token: str) -> None:
    """Prompt user to enter email for magic link verification."""
    ST.subheader("✉️ Complete your sign-in")
    ST.write("Enter your email address to verify the magic link.")
    
    col1, col2 = ST.columns([3, 1])
    with col1:
        email = ST.text_input(
            "Email",
            placeholder="your.email@law-firm.com",
            key="magic_link_email_input"
        )
    with col2:
        clicked = ST.button("Verify", use_container_width=True, key="verify_btn")
    
    if clicked:
        if not email:
            ST.error("❌ Please enter your email address.")
            ST.stop()
        else:
            render_magic_link_verification(email.strip().lower(), token)


def render_sidebar(session_id: str) -> None:
    user = get_current_user()
    with ST.sidebar:
        ST.subheader("Account")
        ST.text(f"Signed in as {user}")
        
        # Display user role if available
        from legal_ai.auth import auth as auth_module
        user_role = auth_module.get_current_user_role()
        role_emoji = {"admin": "👑", "editor": "✏️", "viewer": "👁️"}.get(user_role, "👤")
        ST.caption(f"{role_emoji} Role: {user_role}")
        
        col1, col2 = ST.columns(2)
        with col1:
            if ST.button("👤 Profile", use_container_width=True):
                ST.switch_page("pages/profile.py")
        
        with col2:
            if auth_module.is_admin():
                if ST.button("👑 Admin", use_container_width=True):
                    ST.switch_page("pages/admin.py")
        
        if ST.button("Sign out", use_container_width=True):
            clear_chat_cache()
            sign_out()
            ST.rerun()

        # Jurisdiction Filter
        ST.divider()
        ST.subheader("🌍 Jurisdictions")
        
        try:
            # Get user's current jurisdictions
            user_id = get_current_user_id()
            current_jurisdictions = get_user_jurisdictions(user_id)
            current_ids = [j["jurisdiction_id"] for j in current_jurisdictions] if current_jurisdictions else []
            
            # Get jurisdiction tree for selector
            jurisdictions = get_jurisdiction_tree()
            
            # Create jurisdiction options
            jurisdiction_options = {j["name"]: j["jurisdiction_id"] for j in jurisdictions}
            
            # Multi-select jurisdictions
            selected_names = ST.multiselect(
                "Select jurisdictions to search:",
                options=list(jurisdiction_options.keys()),
                default=[j["name"] for j in jurisdictions if j["jurisdiction_id"] in current_ids],
                help="Select one or more jurisdictions to filter your searches"
            )
            
            # Save user preferences
            selected_ids = [jurisdiction_options[name] for name in selected_names]
            if selected_ids and selected_ids != current_ids:
                if ST.button("✅ Save Preferences", use_container_width=True, key="save_jurisdictions"):
                    update_user_jurisdictions(user_id, selected_ids)
                    ST.success("Jurisdiction preferences saved!")
                    ST.rerun()
            
            # Store selected jurisdictions in session state for queries
            ST.session_state["selected_jurisdictions"] = selected_ids
            
            # Add comparison page button
            if ST.button("⚖️ Compare Jurisdictions", use_container_width=True):
                ST.switch_page("pages/compare.py")
        
        except Exception as e:
            ST.warning(f"Could not load jurisdictions: {str(e)}")

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
            preview = ((chat.get("last_message") or "").strip() or "Untitled chat")[:60]
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

        chroma_mode = "Chroma Cloud" if utils.use_chroma_cloud() else "local"
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
            # Get current access token
            access_token = get_current_access_token()
            
            # Get selected jurisdictions from session state
            jurisdiction_ids = ST.session_state.get("selected_jurisdictions", [])
            
            assistant_response = route_query(
                question=prompt,
                session_id=session_id,
                jwt=access_token,
                jurisdiction_ids=jurisdiction_ids if jurisdiction_ids else None,
            )
            chat.chat_message("assistant").write(assistant_response)

        ST.session_state.messages.append({"id": chat_id, "role": "user", "content": prompt})
        ST.session_state.messages.append(
            {"id": chat_id, "role": "assistant", "content": assistant_response}
        )


if __name__ == "__main__":
    ST.set_page_config(page_title="Legal-AI", page_icon="⚖️")
    
    # Initialize auth - restores session from browser storage or query params
    init_auth()
    
    # Initialize tracing (LangFuse)
    utils.setup_langfuse_tracing()
    
    ST.title("Legal-AI")
    ST.caption("EU AI Act RAG assistant — multi-turn conversational retrieval")

    # ========================================================================
    # Handle magic link verification from URL query params
    # ========================================================================
    token = ST.query_params.get("token")
    email_from_link = ST.query_params.get("email")
    
    if token:
        if is_signed_in():
            ST.query_params.clear()
        elif email_from_link:
            # Email is in the link - verify directly
            # Normalize email (strip and lowercase)
            email_from_link = email_from_link.strip().lower()
            ST.divider()
            render_magic_link_verification(email_from_link, token)
            ST.stop()
        else:
            # No email in link - ask user to enter it
            ST.divider()
            render_magic_link_email_prompt(token)
            ST.stop()

    # ========================================================================
    # Check if user is signed in
    # ========================================================================
    if not is_signed_in():
        render_sign_in()
        ST.stop()

    # ========================================================================
    # Refresh access token if needed
    # ========================================================================
    if not refresh_access_token_if_needed():
        ST.warning("Your session has expired. Please sign in again.")
        sign_out()
        ST.rerun()

    if not utils.chroma_collection_has_documents():
        ST.error(
            "Vector store is empty. Run offline ingest first:\n\n"
            "```bash\npython scripts/ingest.py\n```\n\n"
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

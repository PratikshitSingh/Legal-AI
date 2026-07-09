"""Legal-AI Streamlit Application - Main Entry Point."""

from legal_ai.core.logging import configure_logging

# Configure logging (and quiet transformers) before imports pull in the
# LLM/embedding stack.
configure_logging()

import streamlit as st
from streamlit.components.v1 import html as components_html

from legal_ai import db
from legal_ai.auth import browser_storage
from legal_ai.auth.auth import (
    get_current_access_token,
    get_current_user_email,
    get_current_user_id,
    get_or_create_session_id,
    init_auth,
    is_signed_in,
    list_past_chats,
    refresh_access_token_if_needed,
    request_magic_link,
    set_auth_tokens,
    sign_out,
    start_new_chat,
    switch_to_session,
    verify_magic_link_token,
)
from legal_ai.core import tracing
from legal_ai.core.constants import SessionKeys
from legal_ai.services import chat_service, vector_store

CHAT_UI_KEY = "chat1"


def load_ui_messages(session_id: str) -> None:
    rows = db.get_session_messages(session_id)
    st.session_state[SessionKeys.MESSAGES] = [
        {"id": CHAT_UI_KEY, "role": row["role"], "content": row["content"]} for row in rows
    ]


def render_sign_in() -> None:
    """Render passwordless email sign-in form."""
    st.subheader("Sign in to Legal AI")
    st.caption("Enter your email to receive a magic link for passwordless sign-in.")

    with st.form("magic_link_form"):
        email = st.text_input(
            "Email",
            placeholder="your.email@law-firm.com",
            help="We'll send you a link to sign in securely",
        )
        submitted = st.form_submit_button("Send Magic Link")

    if submitted:
        if not email:
            st.error("Please enter an email address.")
            return

        result = request_magic_link(email)
        if result["status"] == "success":
            st.success(result["message"])
            st.info("Check your email for the sign-in link. It expires in 15 minutes.")
        else:
            st.error(result["message"])


def render_magic_link_verification(email: str, token: str) -> None:
    """Render magic link verification UI."""
    # Avoid re-validating already-consumed token when this run is a duplicate
    # (browser prefetch, reloads, or stale verification URL).
    verified_marker = f"{email}:{token}"
    if is_signed_in() and verified_marker == st.session_state.get(
        SessionKeys.LAST_VERIFIED_MAGIC_LINK
    ):
        st.query_params.clear()
        st.rerun()

    st.info(f"🔐 Verifying your sign-in link for {email}...")

    with st.spinner("Checking your magic link..."):
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
        st.session_state[SessionKeys.LAST_VERIFIED_MAGIC_LINK] = verified_marker
        st.query_params.clear()
        st.success(f"✅ Welcome, {result['email']}!")
        start_new_chat(result["user_id"])
        st.balloons()
        # Do a client-side redirect shortly after success so the cookie write from
        # `set_auth_tokens` has time to persist before the app loads again.
        # NOTE: must use components.html — st.markdown/st.html never execute
        # <script> tags. The component runs in an iframe, so redirect the parent.
        components_html(
            """
            <script>
                setTimeout(function() {
                    try {
                        window.parent.location.href = window.parent.location.pathname;
                    } catch (e) {
                        window.location.href = '/';
                    }
                }, 400);
            </script>
            """,
            height=0,
        )
        st.stop()
    else:
        # If auth is already present, treat this as a stale/duplicate verify attempt
        # and continue into the signed-in app instead of showing a false negative.
        if is_signed_in():
            st.query_params.clear()
            st.rerun()

        error_msg = result.get("message", "Invalid or expired link. Please request a new one.")
        st.error(f"❌ {error_msg}")
        st.divider()
        if st.button("← Back to Sign In"):
            st.rerun()


def render_magic_link_email_prompt(token: str) -> None:
    """Prompt user to enter email for magic link verification."""
    st.subheader("✉️ Complete your sign-in")
    st.write("Enter your email address to verify the magic link.")

    col1, col2 = st.columns([3, 1])
    with col1:
        email = st.text_input(
            "Email", placeholder="your.email@law-firm.com", key="magic_link_email_input"
        )
    with col2:
        clicked = st.button("Verify", use_container_width=True, key="verify_btn")

    if clicked:
        if not email:
            st.error("❌ Please enter your email address.")
            st.stop()
        else:
            render_magic_link_verification(email.strip().lower(), token)


def render_sidebar(session_id: str) -> None:
    user = get_current_user_email()
    with st.sidebar:
        st.subheader("Account")
        st.text(f"Signed in as {user}")

        # Display user role if available
        from legal_ai.auth import auth as auth_module

        user_role = auth_module.get_current_user_role()
        role_emoji = {"admin": "👑", "editor": "✏️", "viewer": "👁️"}.get(user_role, "👤")
        st.caption(f"{role_emoji} Role: {user_role}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("👤 Profile", use_container_width=True):
                st.switch_page("pages/profile.py")

        with col2:
            if auth_module.is_admin():
                if st.button("👑 Admin", use_container_width=True):
                    st.switch_page("pages/admin.py")

        if st.button("Sign out", use_container_width=True):
            chat_service.clear_chat_cache()
            sign_out()
            st.rerun()

        # Jurisdiction Filter
        st.divider()
        st.subheader("🌍 Jurisdictions")

        try:
            # Get user's current jurisdictions
            user_id = get_current_user_id()
            current_jurisdictions = db.get_user_jurisdictions(user_id)
            current_ids = (
                [j["jurisdiction_id"] for j in current_jurisdictions]
                if current_jurisdictions
                else []
            )

            # Get jurisdiction tree for selector
            jurisdictions = db.get_jurisdiction_tree()

            # Create jurisdiction options
            jurisdiction_options = {j["name"]: j["jurisdiction_id"] for j in jurisdictions}

            # Multi-select jurisdictions
            selected_names = st.multiselect(
                "Select jurisdictions to search:",
                options=list(jurisdiction_options.keys()),
                default=[j["name"] for j in jurisdictions if j["jurisdiction_id"] in current_ids],
                help="Select one or more jurisdictions to filter your searches",
            )

            # Save user preferences
            selected_ids = [jurisdiction_options[name] for name in selected_names]
            if selected_ids and selected_ids != current_ids:
                if st.button(
                    "✅ Save Preferences", use_container_width=True, key="save_jurisdictions"
                ):
                    db.update_user_jurisdictions(user_id, selected_ids)
                    st.success("Jurisdiction preferences saved!")
                    st.rerun()

            # Store selected jurisdictions in session state for queries
            st.session_state[SessionKeys.SELECTED_JURISDICTIONS] = selected_ids

            # Add comparison page button
            if st.button("⚖️ Compare Jurisdictions", use_container_width=True):
                st.switch_page("pages/compare.py")

        except Exception as e:
            st.warning(f"Could not load jurisdictions: {str(e)}")

        st.divider()
        st.subheader("Chats")
        if st.button("New chat", use_container_width=True):
            chat_service.clear_chat_cache()
            start_new_chat()
            st.rerun()

        past = list_past_chats()
        if not past:
            st.caption("No past chats yet.")
            return

        for chat in past:
            sid = chat["session_id"]
            preview = ((chat.get("last_message") or "").strip() or "Untitled chat")[:60]
            label = f"{preview}…" if len(preview) >= 60 else preview
            is_active = sid == session_id
            if st.button(
                label,
                key=f"session_{sid}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                if sid != session_id:
                    chat_service.clear_chat_cache(sid)
                    switch_to_session(sid)
                    load_ui_messages(sid)
                    st.rerun()

        chroma_mode = "Chroma Cloud" if vector_store.use_chroma_cloud() else "local"
        st.divider()
        st.caption(f"Session: {session_id[:8]}… · Vector store: {chroma_mode}")


def create_chat(chat_id: str, session_id: str) -> None:
    chat = st.container()

    if SessionKeys.MESSAGES not in st.session_state:
        st.session_state[SessionKeys.MESSAGES] = []

    for message in st.session_state[SessionKeys.MESSAGES]:
        if message["id"] == chat_id:
            chat.chat_message(message["role"]).write(message["content"])

    if prompt := st.chat_input(
        placeholder="Ask me about AI legal stuff in the EU",
        key=chat_id,
    ):
        chat.chat_message("user").write(prompt)
        with st.spinner("Wait for it..."):
            # Get current access token
            access_token = get_current_access_token()

            # Get selected jurisdictions from session state
            jurisdiction_ids = st.session_state.get(SessionKeys.SELECTED_JURISDICTIONS, [])

            assistant_response = chat_service.route_query(
                question=prompt,
                session_id=session_id,
                jwt=access_token,
                jurisdiction_ids=jurisdiction_ids if jurisdiction_ids else None,
            )
            chat.chat_message("assistant").write(assistant_response)

        st.session_state[SessionKeys.MESSAGES].append(
            {"id": chat_id, "role": "user", "content": prompt}
        )
        st.session_state[SessionKeys.MESSAGES].append(
            {"id": chat_id, "role": "assistant", "content": assistant_response}
        )


if __name__ == "__main__":
    st.set_page_config(page_title="Legal-AI", page_icon="⚖️")

    # Initialize auth - restores session from browser storage or query params
    init_auth()

    # Inject cross-tab auth sync listener so other tabs reload when auth changes
    try:
        browser_storage.inject_auth_sync_listener()
    except Exception:
        pass

    # Initialize tracing (LangFuse)
    tracing.setup_langfuse_tracing()

    st.title("Legal-AI")
    st.caption("EU AI Act RAG assistant — multi-turn conversational retrieval")

    # ========================================================================
    # Handle magic link verification from URL query params
    # ========================================================================
    token = st.query_params.get("token")
    email_from_link = st.query_params.get("email")

    if token:
        if is_signed_in():
            st.query_params.clear()
        elif email_from_link:
            # Email is in the link - verify directly
            # Normalize email (strip and lowercase)
            email_from_link = email_from_link.strip().lower()
            st.divider()
            render_magic_link_verification(email_from_link, token)
            st.stop()
        else:
            # No email in link - ask user to enter it
            st.divider()
            render_magic_link_email_prompt(token)
            st.stop()

    # ========================================================================
    # Check if user is signed in
    # ========================================================================
    if not is_signed_in():
        render_sign_in()
        st.stop()

    # ========================================================================
    # Refresh access token if needed
    # ========================================================================
    if not refresh_access_token_if_needed():
        st.warning("Your session has expired. Please sign in again.")
        sign_out()
        st.rerun()

    if not vector_store.collection_has_documents():
        st.error(
            "Vector store is empty. Run offline ingest first:\n\n"
            "```bash\npython scripts/ingest.py\n```\n\n"
            "Requires `GEMINI_API_KEY` and Chroma credentials in `.env`."
        )
        st.stop()

    if SessionKeys.SESSION_ID not in st.session_state:
        start_new_chat()

    session_id = get_or_create_session_id()
    if SessionKeys.MESSAGES not in st.session_state:
        load_ui_messages(session_id)

    render_sidebar(session_id)
    create_chat(CHAT_UI_KEY, session_id)

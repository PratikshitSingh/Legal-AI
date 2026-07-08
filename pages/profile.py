"""User Profile Page - View and edit user profile."""

import streamlit as st

from legal_ai.auth import auth
from legal_ai import db
from legal_ai.auth import rbac
from legal_ai.core.constants import SessionKeys

# Initialize auth - restores session from browser storage
auth.init_auth()

# Configure page
st.set_page_config(page_title="Profile", page_icon="👤", layout="wide")

# Require login
if not auth.is_signed_in():
    st.error("❌ You must be signed in to view your profile.")
    st.stop()

# Get user profile
user_id = auth.get_current_user_id()
user = db.get_user_by_id(user_id)

if not user:
    st.error("❌ User profile not found.")
    st.stop()

# Page title
st.title("👤 Your Profile")

# Display read-only info
col1, col2 = st.columns(2)

with col1:
    st.subheader("Account Information")
    st.write(f"**Email:** `{user['email']}`")
    st.write(f"**User ID:** `{user_id}`")
    st.write(f"**Role:** {rbac.display_role_badge(user['role'])}")

with col2:
    st.subheader("Account Dates")
    if user.get("created_at"):
        st.write(f"**Created:** {user['created_at']}")
    if user.get("updated_at"):
        st.write(f"**Last Updated:** {user['updated_at']}")
    if user.get("last_login_at"):
        st.write(f"**Last Login:** {user['last_login_at']}")

st.divider()

# Editable profile fields
st.subheader("✏️ Edit Your Profile")

col1, col2 = st.columns(2)

with col1:
    full_name = st.text_input(
        "Full Name",
        value=user.get("full_name") or "",
        placeholder="Enter your full name",
        key="full_name_input",
    )

with col2:
    firm = st.text_input(
        "Firm / Organization",
        value=user.get("firm") or "",
        placeholder="Enter your firm or organization",
        key="firm_input",
    )

# Save button
if st.button("💾 Save Changes", key="save_profile"):
    try:
        # Update profile
        success = db.update_user_profile(
            user_id, full_name=full_name if full_name else None, firm=firm if firm else None
        )

        if success:
            # Update session state
            st.session_state[SessionKeys.USER_FULL_NAME] = full_name
            st.session_state[SessionKeys.USER_FIRM] = firm
            st.success("✅ Profile updated successfully!")
            st.rerun()
        else:
            st.error("❌ Failed to update profile.")
    except Exception as e:
        st.error(f"❌ Error updating profile: {str(e)}")

st.divider()

# Admin section
if auth.is_admin():
    st.subheader("🔒 Admin Info")
    with st.expander("View Audit Log for this User"):
        st.info("Audit logging feature coming soon...")

# Sign out button
st.divider()
if st.button("🚪 Sign Out", key="sign_out_btn"):
    auth.sign_out()
    st.success("✅ Signed out successfully!")
    st.rerun()

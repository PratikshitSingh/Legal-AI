"""Admin Dashboard - Manage users and roles."""

import streamlit as st

from legal_ai.auth import auth
from legal_ai.db import db
from legal_ai.auth import rbac

# Configure page
st.set_page_config(page_title="Admin Dashboard", page_icon="👑", layout="wide")

# Require admin role
if not auth.is_signed_in():
    st.error("❌ You must be signed in to access this page.")
    st.stop()

if not auth.is_admin():
    st.error("❌ Access denied. Admin role required.")
    st.stop()

st.title("👑 Admin Dashboard")

# Tabs for different admin functions
tab1, tab2, tab3 = st.tabs(["Users", "Roles", "Analytics"])

# ============================================================================
# TAB 1: User Management
# ============================================================================

with tab1:
    st.subheader("👥 Manage Users")
    
    # Search/filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search_email = st.text_input("Search by email", placeholder="user@example.com")
    
    with col2:
        role_filter = st.selectbox("Filter by role", ["All", "viewer", "editor", "admin"])
    
    with col3:
        limit = st.number_input("Limit results", min_value=10, max_value=500, value=50)
    
    # Fetch users
    try:
        all_users = db.get_all_users(limit=limit)
        
        # Apply filters
        if role_filter != "All":
            all_users = [u for u in all_users if u.get('role') == role_filter]
        
        if search_email:
            all_users = [u for u in all_users if search_email.lower() in u.get('email', '').lower()]
        
        if not all_users:
            st.info("No users found matching your criteria.")
        else:
            st.write(f"Found {len(all_users)} user(s)")
            
            # Display users in a table-like format
            for user in all_users:
                col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1.5, 1.5, 1])
                
                with col1:
                    st.write(f"📧 {user['email']}")
                    if user.get('full_name'):
                        st.caption(f"Name: {user['full_name']}")
                
                with col2:
                    st.write(f"{rbac.display_role_badge(user['role'])}")
                
                with col3:
                    if user.get('firm'):
                        st.write(f"🏢 {user['firm']}")
                    else:
                        st.write("—")
                
                with col4:
                    # Role change button
                    current_role = user['role']
                    new_role = st.selectbox(
                        "Change role",
                        ["viewer", "editor", "admin"],
                        index=["viewer", "editor", "admin"].index(current_role),
                        key=f"role_{user['user_id']}",
                        label_visibility="collapsed"
                    )
                
                with col5:
                    if new_role != current_role:
                        if st.button("✓ Update", key=f"update_{user['user_id']}"):
                            try:
                                success = db.update_user_role(
                                    user['user_id'],
                                    new_role,
                                    changed_by_user_id=auth.get_current_user_id()
                                )
                                if success:
                                    st.success(f"✅ Updated {user['email']} to {new_role}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed to update {user['email']}")
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")
                
                st.divider()
    
    except Exception as e:
        st.error(f"❌ Error loading users: {str(e)}")

# ============================================================================
# TAB 2: Role Configuration
# ============================================================================

with tab2:
    st.subheader("🔑 Roles & Permissions")
    
    st.info(
        """
        **Role Hierarchy:**
        - **Viewer** 👁️: Read-only access
        - **Editor** ✏️: Read and write access
        - **Admin** 👑: Full access including user management
        """
    )
    
    # Display permission matrix
    st.write("**Permission Matrix:**")
    
    perm_data = {
        "Permission": ["read", "write", "admin", "manage_users"],
        "Viewer": [
            rbac.ROLE_PERMISSIONS["viewer"].get("read", False),
            rbac.ROLE_PERMISSIONS["viewer"].get("write", False),
            rbac.ROLE_PERMISSIONS["viewer"].get("admin", False),
            rbac.ROLE_PERMISSIONS["viewer"].get("manage_users", False),
        ],
        "Editor": [
            rbac.ROLE_PERMISSIONS["editor"].get("read", False),
            rbac.ROLE_PERMISSIONS["editor"].get("write", False),
            rbac.ROLE_PERMISSIONS["editor"].get("admin", False),
            rbac.ROLE_PERMISSIONS["editor"].get("manage_users", False),
        ],
        "Admin": [
            rbac.ROLE_PERMISSIONS["admin"].get("read", False),
            rbac.ROLE_PERMISSIONS["admin"].get("write", False),
            rbac.ROLE_PERMISSIONS["admin"].get("admin", False),
            rbac.ROLE_PERMISSIONS["admin"].get("manage_users", False),
        ],
    }
    
    # Convert to display format
    import pandas as pd
    df = pd.DataFrame(perm_data)
    df = df.set_index("Permission")
    
    # Display with colored cells
    st.dataframe(df, use_container_width=True)
    
    st.caption("✅ = Permitted, ❌ = Not permitted")

# ============================================================================
# TAB 3: Analytics
# ============================================================================

with tab3:
    st.subheader("📊 Analytics")
    
    try:
        all_users = db.get_all_users(limit=1000)
        
        if all_users:
            # Count by role
            role_counts = {}
            for user in all_users:
                role = user.get('role', 'unknown')
                role_counts[role] = role_counts.get(role, 0) + 1
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Users", len(all_users))
            
            with col2:
                admins = len([u for u in all_users if u.get('role') == 'admin'])
                st.metric("Admins 👑", admins)
            
            with col3:
                editors = len([u for u in all_users if u.get('role') == 'editor'])
                st.metric("Editors ✏️", editors)
            
            st.divider()
            
            # Users by role chart
            st.write("**Users by Role:**")
            st.bar_chart(role_counts)
            
            # Profile completion
            st.write("**Profile Completion:**")

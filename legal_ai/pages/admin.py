"""Admin Dashboard - Manage users and roles."""

import io
import streamlit as st

from legal_ai.auth import auth
from legal_ai.db import db
from legal_ai.auth import rbac
from legal_ai.services import embed

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
tab1, tab2, tab3, tab4 = st.tabs(["Users", "Roles", "Analytics", "Documents"])

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
            
            # Count users with full profiles
            complete_profiles = len([u for u in all_users if u.get('full_name') and u.get('firm')])
            incomplete = len(all_users) - complete_profiles
            
            st.write(f"- Complete profiles: {complete_profiles}/{len(all_users)}")
            st.write(f"- Incomplete profiles: {incomplete}/{len(all_users)}")
    
    except Exception as e:
        st.error(f"❌ Error loading analytics: {str(e)}")

# ============================================================================
# TAB 4: Document Management
# ============================================================================

with tab4:
    st.subheader("📄 Manage Documents")
    
    # Two columns: Upload & History
    col_upload, col_history = st.columns([1, 1])
    
    with col_upload:
        st.write("### Upload Document")
        
        uploaded_file = st.file_uploader(
            "Choose a file (PDF or TXT)",
            type=["pdf", "txt"],
            help="Upload PDF or TXT files to add to the embedding vector store"
        )
        
        if uploaded_file:
            # Extract file type
            file_type = uploaded_file.name.split(".")[-1].lower()
            
            # Get file content
            file_bytes = uploaded_file.read()
            file_size_mb = len(file_bytes) / (1024 * 1024)
            
            if file_size_mb > 50:
                st.error(f"❌ File too large ({file_size_mb:.1f} MB). Max 50 MB allowed.")
            else:
                # Document metadata
                doc_name = st.text_input(
                    "Document Name",
                    value=uploaded_file.name.split(".")[0],
                    help="Name for this document (used for duplicate detection)"
                )
                
                doc_description = st.text_area(
                    "Description",
                    help="Brief description of document content",
                    height=80
                )
                
                # Preflight check
                if st.button("🔍 Check for Duplicates", key="preflight_check"):
                    with st.spinner("Checking for duplicates…"):
                        try:
                            # Extract text for hashing
                            text = embed.extract_text_from_file(file_bytes, file_type)
                            content_hash = embed.get_document_hash(text)
                            
                            # Check for duplicates
                            dup_result = embed.check_duplicate_document(doc_name, content_hash)
                            
                            st.session_state.preflight_result = {
                                "hash": content_hash,
                                "text": text,
                                "dup_result": dup_result,
                            }
                            
                            if dup_result["existing_exact_match"]:
                                st.warning(
                                    f"⚠️ **Duplicate document detected!** "
                                    f"This exact document (name + content) already exists in the system. "
                                    f"Existing: {dup_result['existing_chunks']} chunks. "
                                    f"Uploading will be skipped.",
                                    icon="⚠️"
                                )
                            elif dup_result["existing_chunks"] > 0:
                                st.info(
                                    f"ℹ️ **Document name exists** ({dup_result['existing_chunks']} chunks), "
                                    f"but content is different. New content will be added.",
                                    icon="ℹ️"
                                )
                            else:
                                st.success(
                                    f"✅ **New document** - ~{len(embed.split_text_into_sections(text, 1000))} chunks will be added.",
                                    icon="✅"
                                )
                        
                        except Exception as e:
                            st.error(f"❌ Preflight check failed: {str(e)}")
                
                # Upload button (only enabled after preflight)
                if "preflight_result" in st.session_state:
                    if st.button("📤 Upload & Embed", key="upload_button"):
                        current_user_id = auth.get_current_user_id()
                        
                        with st.spinner("Uploading and embedding document… (this may take a few minutes)"):
                            try:
                                result = embed.ingest_custom_document(
                                    file_bytes=file_bytes,
                                    document_name=doc_name,
                                    document_description=doc_description,
                                    uploaded_by_user_id=current_user_id,
                                    file_type=file_type,
                                )
                                
                                if result["success"]:
                                    st.success(result["message"], icon="✅")
                                    
                                    # Log audit event
                                    if result["document_id"]:
                                        db.log_document_audit(
                                            result["document_id"],
                                            current_user_id,
                                            "upload",
                                            {"file_type": file_type, "chunks_added": result["chunks_added"]}
                                        )
                                    
                                    st.rerun()
                                else:
                                    st.error(result["message"], icon="❌")
                            
                            except Exception as e:
                                st.error(f"❌ Upload failed: {str(e)}")
    
    with col_history:
        st.write("### Document History")
        
        # Fetch all documents
        try:
            all_docs = db.get_all_documents(limit=20)
            
            if not all_docs:
                st.info("No documents uploaded yet.")
            else:
                st.write(f"**Latest {len(all_docs)} uploads:**")
                
                for doc in all_docs:
                    with st.container(border=True):
                        col_name, col_meta = st.columns([2, 1])
                        
                        with col_name:
                            st.write(f"**{doc['name']}**")
                            if doc.get('description'):
                                st.caption(doc['description'][:100] + ("…" if len(doc['description']) > 100 else ""))
                        
                        with col_meta:
                            st.metric("Chunks", doc.get('chunk_count', 0))
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.caption(f"📝 {doc['file_type'].upper()}")
                        
                        with col2:
                            uploader_email = doc.get('uploaded_by_email', '?')
                            st.caption(f"👤 {uploader_email}")
                        
                        with col3:
                            created = doc.get('created_at', '?')
                            st.caption(f"📅 {created}")
        
        except Exception as e:
            st.error(f"❌ Error loading documents: {str(e)}")

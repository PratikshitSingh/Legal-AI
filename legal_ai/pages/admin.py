"""Admin Dashboard - Manage users and roles."""

import io
import csv
import streamlit as st
import pandas as pd

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
    
    # Tabs for different document operations
    doc_tab1, doc_tab2, doc_tab3 = st.tabs(["Upload", "Browse", "Bulk Import"])
    
    # ========================================================================
    # Document Upload
    # ========================================================================
    with doc_tab1:
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
                
                # NEW: Jurisdiction selector
                try:
                    jurisdictions = db.get_jurisdiction_tree()
                    jurisdiction_options = {j["name"]: j["jurisdiction_id"] for j in jurisdictions}
                    
                    selected_jurisdiction = st.selectbox(
                        "Jurisdiction",
                        options=list(jurisdiction_options.keys()),
                        help="Select the jurisdiction this document applies to"
                    )
                    jurisdiction_id = jurisdiction_options[selected_jurisdiction]
                except Exception as e:
                    st.warning(f"Could not load jurisdictions: {str(e)}")
                    jurisdiction_id = None
                
                # NEW: Document type selector
                doc_types = ["regulation", "directive", "guidance", "case_law", "statute", "ordinance", "policy", "bill"]
                doc_type = st.selectbox(
                    "Document Type",
                    options=doc_types,
                    help="Classify the type of document"
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
    
    # ========================================================================
    # Document Browser with Filters
    # ========================================================================
    with doc_tab2:
        st.write("### Browse Documents")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Jurisdiction filter
            try:
                jurisdictions = db.get_jurisdiction_tree()
                jurisdiction_filter = st.multiselect(
                    "Filter by Jurisdiction",
                    options=[j["name"] for j in jurisdictions],
                    help="Leave empty to show all jurisdictions"
                )
            except Exception as e:
                st.warning(f"Could not load jurisdictions: {str(e)}")
                jurisdiction_filter = []
        
        with col2:
            # Document type filter
            doc_type_filter = st.multiselect(
                "Filter by Document Type",
                options=["regulation", "directive", "guidance", "case_law", "statute", "ordinance", "policy", "bill"],
                help="Leave empty to show all types"
            )
        
        with col3:
            # Sort by
            sort_by = st.selectbox(
                "Sort by",
                options=["Created (Newest)", "Created (Oldest)", "Name (A-Z)", "Chunks (Most)"],
                help="How to sort documents"
            )
        
        # Fetch documents
        try:
            all_docs = db.get_all_documents(limit=100)
            
            if not all_docs:
                st.info("No documents in the system yet.")
            else:
                st.write(f"**Displaying up to {len(all_docs)} documents:**")
                
                # Apply filters
                if jurisdiction_filter:
                    # Create jurisdiction ID to name map
                    jurisdictions = db.get_jurisdiction_tree()
                    jurisdiction_name_to_id = {j["name"]: j["jurisdiction_id"] for j in jurisdictions}
                    filtered_ids = [jurisdiction_name_to_id[name] for name in jurisdiction_filter]
                    # Filter would need to be applied based on document's jurisdiction_id
                    # For now, this is a placeholder as the documents table needs jurisdiction_id populated
                
                if doc_type_filter:
                    # Filter by doc_type (would need to be stored in documents)
                    pass
                
                # Sort
                if sort_by == "Created (Newest)":
                    all_docs = sorted(all_docs, key=lambda x: x.get('created_at', ''), reverse=True)
                elif sort_by == "Created (Oldest)":
                    all_docs = sorted(all_docs, key=lambda x: x.get('created_at', ''))
                elif sort_by == "Name (A-Z)":
                    all_docs = sorted(all_docs, key=lambda x: x.get('name', ''))
                elif sort_by == "Chunks (Most)":
                    all_docs = sorted(all_docs, key=lambda x: x.get('chunk_count', 0), reverse=True)
                
                # Display documents
                for doc in all_docs:
                    with st.container(border=True):
                        col_name, col_meta = st.columns([2, 1])
                        
                        with col_name:
                            st.write(f"**{doc['name']}**")
                            if doc.get('description'):
                                st.caption(doc['description'][:100] + ("…" if len(doc['description']) > 100 else ""))
                        
                        with col_meta:
                            st.metric("Chunks", doc.get('chunk_count', 0))
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.caption(f"📝 {doc['file_type'].upper()}")
                        
                        with col2:
                            uploader_email = doc.get('uploaded_by_email', '?')
                            st.caption(f"👤 {uploader_email}")
                        
                        with col3:
                            created = doc.get('created_at', '?')
                            st.caption(f"📅 {created}")
                        
                        with col4:
                            if st.button("ℹ️ Details", key=f"doc_details_{doc['document_id']}"):
                                with st.expander("Document Details"):
                                    st.json({
                                        "ID": doc['document_id'],
                                        "Name": doc['name'],
                                        "Type": doc['file_type'],
                                        "Chunks": doc['chunk_count'],
                                        "Uploaded By": doc.get('uploaded_by_email', 'N/A'),
                                        "Created": doc.get('created_at', 'N/A'),
                                    })
        
        except Exception as e:
            st.error(f"❌ Error loading documents: {str(e)}")
    
    # ========================================================================
    # Bulk Import via CSV
    # ========================================================================
    with doc_tab3:
        st.write("### Bulk Import Documents")
        
        st.info(
            """
            **CSV Format:** Create a CSV file with the following columns:
            - `file_path` (required): Path to PDF or TXT file
            - `document_name` (required): Name of the document
            - `description` (optional): Document description
            - `jurisdiction` (optional): Jurisdiction code (e.g., "EU", "US")
            - `document_type` (optional): Type of document (regulation, directive, etc.)
            
            **Example:**
            ```
            file_path,document_name,description,jurisdiction,document_type
            docs/gdpr.pdf,GDPR,General Data Protection Regulation,EU,regulation
            docs/ccpa.pdf,CCPA,California Consumer Privacy Act,US,statute
            ```
            """
        )
        
        # CSV Upload
        csv_file = st.file_uploader(
            "Upload CSV file",
            type=["csv"],
            help="CSV file with document metadata and file paths"
        )
        
        if csv_file:
            try:
                # Read CSV
                df = pd.read_csv(csv_file)
                
                # Validate required columns
                required_cols = ['file_path', 'document_name']
                missing_cols = [col for col in required_cols if col not in df.columns]
                
                if missing_cols:
                    st.error(f"❌ Missing required columns: {', '.join(missing_cols)}")
                else:
                    st.write(f"**Found {len(df)} documents in CSV**")
                    
                    # Preview
                    with st.expander("Preview CSV Data"):
                        st.dataframe(df, use_container_width=True)
                    
                    # Import button
                    if st.button("📥 Start Bulk Import", key="bulk_import_button"):
                        current_user_id = auth.get_current_user_id()
                        progress_bar = st.progress(0)
                        status_container = st.container()
                        
                        imported_count = 0
                        failed_count = 0
                        
                        for idx, row in df.iterrows():
                            try:
                                # Get file path
                                file_path = row.get('file_path')
                                if not file_path:
                                    failed_count += 1
                                    continue
                                
                                # Try to read file
                                try:
                                    with open(file_path, 'rb') as f:
                                        file_bytes = f.read()
                                except FileNotFoundError:
                                    status_container.warning(f"⚠️ File not found: {file_path}")
                                    failed_count += 1
                                    continue
                                
                                # Get metadata
                                doc_name = row.get('document_name', 'Untitled')
                                doc_description = row.get('description', '')
                                file_type = file_path.split('.')[-1].lower()
                                
                                # Ingest document
                                result = embed.ingest_custom_document(
                                    file_bytes=file_bytes,
                                    document_name=doc_name,
                                    document_description=doc_description,
                                    uploaded_by_user_id=current_user_id,
                                    file_type=file_type,
                                )
                                
                                if result["success"]:
                                    imported_count += 1
                                    db.log_document_audit(
                                        result["document_id"],
                                        current_user_id,
                                        "bulk_import",
                                        {"file_type": file_type, "chunks_added": result["chunks_added"]}
                                    )
                                else:
                                    failed_count += 1
                            
                            except Exception as e:
                                failed_count += 1
                            
                            # Update progress
                            progress_bar.progress((idx + 1) / len(df))
                        
                        # Summary
                        st.divider()
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.success(f"✅ Successfully imported: {imported_count} documents")
                        
                        with col2:
                            if failed_count > 0:
                                st.warning(f"⚠️ Failed: {failed_count} documents")
            
            except Exception as e:
                st.error(f"❌ Error processing CSV: {str(e)}")

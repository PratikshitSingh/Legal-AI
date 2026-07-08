"""Cross-jurisdiction document comparison page."""

import streamlit as st

from legal_ai.auth.auth import is_signed_in, init_auth
from legal_ai import db
from legal_ai.services.jurisdiction_retriever import JurisdictionAwareRetriever

# Initialize auth - restores session from browser storage
init_auth()

# Configure page
st.set_page_config(page_title="Compare Jurisdictions", page_icon="⚖️", layout="wide")

# Require sign-in
if not is_signed_in():
    st.error("❌ You must be signed in to access this page.")
    st.stop()

st.title("⚖️ Compare Jurisdictions")
st.caption("Search for regulations side-by-side across different jurisdictions")

# Get all jurisdictions
jurisdictions = db.get_jurisdiction_tree()
jurisdiction_map = {j["name"]: j["jurisdiction_id"] for j in jurisdictions}

col1, col2 = st.columns(2)

with col1:
    st.subheader("📍 Jurisdiction 1")
    jurisdiction_1_name = st.selectbox(
        "Select first jurisdiction:",
        options=list(jurisdiction_map.keys()),
        key="jurisdiction_1_select",
    )
    jurisdiction_1_id = jurisdiction_map[jurisdiction_1_name]

with col2:
    st.subheader("📍 Jurisdiction 2")
    # Filter out already selected jurisdiction
    available_jurisdictions = [j for j in jurisdiction_map.keys() if j != jurisdiction_1_name]
    jurisdiction_2_name = st.selectbox(
        "Select second jurisdiction:", options=available_jurisdictions, key="jurisdiction_2_select"
    )
    jurisdiction_2_id = jurisdiction_map[jurisdiction_2_name]

st.divider()

# Search query
st.subheader("🔍 Search Query")
query = st.text_input(
    "Enter search query (e.g., 'data protection', 'AI regulations'):",
    placeholder="What would you like to compare?",
    help="Search for documents containing this query in both jurisdictions",
)

if st.button("🔎 Search & Compare", type="primary", use_container_width=True):
    if not query.strip():
        st.error("Please enter a search query.")
    else:
        with st.spinner("Searching both jurisdictions..."):
            try:
                retriever = JurisdictionAwareRetriever()

                # Search in both jurisdictions
                results_1 = retriever.search_within_jurisdictions(
                    query=query, jurisdiction_ids=[jurisdiction_1_id], k=5
                )

                results_2 = retriever.search_within_jurisdictions(
                    query=query, jurisdiction_ids=[jurisdiction_2_id], k=5
                )

                # Display results side-by-side
                st.divider()
                st.subheader("📊 Comparison Results")

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"### 🔵 {jurisdiction_1_name}")

                    if not results_1:
                        st.info("No documents found for this jurisdiction.")
                    else:
                        st.write(f"**Found {len(results_1)} results:**")

                        for i, result in enumerate(results_1, 1):
                            with st.container(border=True):
                                st.write(f"**Result {i}** - {result.get('section_title', 'N/A')}")
                                st.write(f"*Relevance: {(1 - result['distance']):.1%}*")
                                st.markdown(
                                    f"```\n{result['document'][:300]}...\n```"
                                    if len(result["document"]) > 300
                                    else f"```\n{result['document']}\n```"
                                )

                                meta = result.get("metadata", {})
                                st.caption(
                                    f"Status: {result.get('status', 'active')} | "
                                    f"Effective: {result.get('effective_date', 'N/A')}"
                                )

                with col2:
                    st.markdown(f"### 🔴 {jurisdiction_2_name}")

                    if not results_2:
                        st.info("No documents found for this jurisdiction.")
                    else:
                        st.write(f"**Found {len(results_2)} results:**")

                        for i, result in enumerate(results_2, 1):
                            with st.container(border=True):
                                st.write(f"**Result {i}** - {result.get('section_title', 'N/A')}")
                                st.write(f"*Relevance: {(1 - result['distance']):.1%}*")
                                st.markdown(
                                    f"```\n{result['document'][:300]}...\n```"
                                    if len(result["document"]) > 300
                                    else f"```\n{result['document']}\n```"
                                )

                                meta = result.get("metadata", {})
                                st.caption(
                                    f"Status: {result.get('status', 'active')} | "
                                    f"Effective: {result.get('effective_date', 'N/A')}"
                                )

                # Summary
                st.divider()
                st.subheader("📈 Summary")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric(f"{jurisdiction_1_name} Results", len(results_1))

                with col2:
                    st.metric(f"{jurisdiction_2_name} Results", len(results_2))

                with col3:
                    avg_relevance_1 = (
                        sum(1 - r["distance"] for r in results_1) / len(results_1)
                        if results_1
                        else 0
                    )
                    avg_relevance_2 = (
                        sum(1 - r["distance"] for r in results_2) / len(results_2)
                        if results_2
                        else 0
                    )
                    avg_relevance = (avg_relevance_1 + avg_relevance_2) / 2
                    st.metric("Avg Relevance", f"{avg_relevance:.1%}")

                # Observations
                if results_1 and results_2:
                    st.info(
                        f"""
                        **Key Observations:**
                        - {jurisdiction_1_name}: {len(results_1)} relevant document(s) found
                        - {jurisdiction_2_name}: {len(results_2)} relevant document(s) found
                        - Average relevance score: {avg_relevance:.1%}
                        
                        **Recommendations:**
                        1. Review the most relevant sections (highest relevance scores)
                        2. Compare language and requirements between jurisdictions
                        3. Identify common regulatory themes
                        4. Note jurisdiction-specific requirements and exceptions
                        """
                    )

            except Exception as e:
                st.error(f"❌ Search failed: {str(e)}")

st.divider()
st.caption(
    "💡 Tip: Use this tool to understand regulatory differences between jurisdictions and identify compliance requirements."
)

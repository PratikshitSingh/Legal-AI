"""Jurisdiction-aware document retrieval service."""

from legal_ai.services.embed import _get_collection


class JurisdictionAwareRetriever:
    """Search documents with jurisdiction-aware filtering using Chroma metadata."""

    def __init__(self):
        """Initialize retriever with Chroma collection."""
        self.collection = _get_collection()

    def _build_jurisdiction_filter(self, jurisdiction_ids: list[str], include_parent: bool = True) -> dict:
        """Build Chroma WHERE filter for jurisdiction IDs.

        Args:
            jurisdiction_ids: List of jurisdiction IDs to filter by
            include_parent: If True, also include parent jurisdictions (not implemented yet)

        Returns:
            Chroma WHERE clause dict
        """
        if not jurisdiction_ids:
            return {}

        # Create WHERE clause: jurisdiction_id IN [id1, id2, ...]
        if len(jurisdiction_ids) == 1:
            return {"jurisdiction_id": {"$eq": jurisdiction_ids[0]}}
        else:
            return {"jurisdiction_id": {"$in": jurisdiction_ids}}

    def search_within_jurisdictions(
        self,
        query: str,
        jurisdiction_ids: list[str],
        k: int = 5,
        include_parent: bool = True
    ) -> list[dict]:
        """Search for documents within specific jurisdictions.

        Args:
            query: Search query (natural language)
            jurisdiction_ids: List of jurisdiction IDs to search within
            k: Number of results to return
            include_parent: Include parent jurisdictions in search (future feature)

        Returns:
            List of result dicts with:
                - document: chunk text
                - metadata: chunk metadata
                - distance: similarity score
                - jurisdiction: jurisdiction info
        """
        if not jurisdiction_ids:
            return []

        # Build Chroma WHERE filter
        where_filter = self._build_jurisdiction_filter(jurisdiction_ids, include_parent)

        # Query Chroma collection
        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where_filter if where_filter else None
        )

        if not results or not results["documents"]:
            return []

        # Format results with jurisdiction information
        formatted_results = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0

            formatted_results.append({
                "document": doc,
                "metadata": metadata,
                "distance": distance,
                "jurisdiction": metadata.get("jurisdiction_code", "UNKNOWN"),
                "section_title": metadata.get("section_title", ""),
                "status": metadata.get("status", "active"),
                "effective_date": metadata.get("effective_date", ""),
            })

        return formatted_results

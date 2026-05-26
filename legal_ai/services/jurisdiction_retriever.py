"""Jurisdiction-aware document retrieval service."""

from typing import Optional

from legal_ai.services.embed import _get_collection
from legal_ai.db.db import get_engine
from sqlalchemy import text


class JurisdictionAwareRetriever:
    """Search documents with jurisdiction-aware filtering using Chroma metadata."""
    
    def __init__(self):
        """Initialize retriever with Chroma collection."""
        self.collection = _get_collection()
        self.engine = get_engine()
    
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
    
    def search_across_jurisdictions(
        self,
        query: str,
        jurisdiction_ids: list[str],
        k: int = 5,
        return_grouped: bool = True
    ) -> dict | list[dict]:
        """Search across multiple jurisdictions and optionally group by jurisdiction.
        
        Args:
            query: Search query (natural language)
            jurisdiction_ids: List of jurisdiction IDs to search across
            k: Total number of results to return
            return_grouped: If True, return as dict grouped by jurisdiction.
                          If False, return flat list.
        
        Returns:
            If return_grouped=True: Dict with jurisdiction_code -> results
            If return_grouped=False: List of result dicts with jurisdiction info
        """
        if not jurisdiction_ids:
            return {} if return_grouped else []
        
        # Get all results from Chroma
        where_filter = self._build_jurisdiction_filter(jurisdiction_ids)
        
        results = self.collection.query(
            query_texts=[query],
            n_results=k * 2,  # Get extra results for grouping
            where=where_filter if where_filter else None
        )
        
        if not results or not results["documents"]:
            return {} if return_grouped else []
        
        # Format results
        flat_results = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else 0
            
            flat_results.append({
                "document": doc,
                "metadata": metadata,
                "distance": distance,
                "jurisdiction": metadata.get("jurisdiction_code", "UNKNOWN"),
                "section_title": metadata.get("section_title", ""),
                "status": metadata.get("status", "active"),
                "effective_date": metadata.get("effective_date", ""),
            })
        
        if not return_grouped:
            return flat_results[:k]
        
        # Group by jurisdiction
        grouped = {}
        for result in flat_results:
            jurisdiction = result["jurisdiction"]
            if jurisdiction not in grouped:
                grouped[jurisdiction] = []
            
            grouped[jurisdiction].append(result)
            
            # Stop when we have k results
            total_results = sum(len(v) for v in grouped.values())
            if total_results >= k:
                break
        
        return grouped
    
    def search_all_jurisdictions(
        self,
        query: str,
        k: int = 10
    ) -> list[dict]:
        """Search across all jurisdictions without filtering.
        
        Args:
            query: Search query (natural language)
            k: Number of results to return
        
        Returns:
            List of result dicts with jurisdiction information
        """
        # Query without WHERE clause
        results = self.collection.query(
            query_texts=[query],
            n_results=k
        )
        
        if not results or not results["documents"]:
            return []
        
        # Format results
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
    
    def get_jurisdiction_info(self, jurisdiction_id: str) -> dict | None:
        """Get jurisdiction metadata from database.
        
        Args:
            jurisdiction_id: Jurisdiction ID (UUID as string)
        
        Returns:
            Jurisdiction dict with code, name, level, flag_emoji, or None
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 
                        jurisdiction_id::text,
                        code,
                        name,
                        level,
                        flag_emoji,
                        region_code
                    FROM jurisdictions
                    WHERE jurisdiction_id = CAST(:jurisdiction_id AS UUID)
                    """
                ),
                {"jurisdiction_id": jurisdiction_id}
            ).mappings().first()
        
        return dict(row) if row else None

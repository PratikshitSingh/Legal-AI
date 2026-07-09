"""Migrate EU AI Act to new multi-jurisdiction schema.

Run as: ``python -m legal_ai.scripts.migrate_eu_ai_act``.
"""

import hashlib
import logging

from sqlalchemy import text

from legal_ai.db import get_engine

logger = logging.getLogger(__name__)


def migrate_eu_ai_act() -> None:
    """
    Migrate the EU AI Act to the new schema:
    1. Assign to EU jurisdiction
    2. Set doc type, language, version, effective_date, status
    3. Update Chroma chunks with new metadata
    """
    engine = get_engine()

    logger.info("Migrating EU AI Act to new schema...")

    # Generate a placeholder content hash for the existing document
    placeholder_hash = hashlib.md5(b"EU-AI-Act-1.0").hexdigest()

    with engine.begin() as conn:
        # Get EU jurisdiction ID
        eu_jurisdiction = conn.execute(
            text("SELECT jurisdiction_id::text FROM jurisdictions WHERE code = 'EU'")
        ).scalar()

        if not eu_jurisdiction:
            logger.error("EU jurisdiction not found. Run seed_jurisdictions first.")
            return

        # Get doc type ID for 'regulation'
        reg_type = conn.execute(
            text("SELECT doc_type_id::text FROM document_types WHERE name = 'regulation'")
        ).scalar()

        # Get language ID for 'en'
        en_lang = conn.execute(
            text("SELECT language_id::text FROM languages WHERE code = 'en'")
        ).scalar()

        # Find existing EU AI Act document
        eu_ai_doc = conn.execute(
            text("""
                SELECT document_id::text FROM documents
                WHERE name ILIKE '%Artificial Intelligence Act%'
                LIMIT 1
            """)
        ).scalar()

        if eu_ai_doc:
            logger.info("Found existing EU AI Act document: %s", eu_ai_doc)
            doc_id = eu_ai_doc
        else:
            logger.info("Creating new EU AI Act document record...")
            # Create new document record
            result = conn.execute(
                text("""
                    INSERT INTO documents (
                        name, description, content_hash, jurisdiction_id, doc_type_id, language_id,
                        version, effective_date, status, is_latest, chunk_count
                    )
                    VALUES (
                        :name, :description, :content_hash, CAST(:jurisdiction_id AS UUID),
                        CAST(:doc_type_id AS UUID), CAST(:language_id AS UUID),
                        :version, :effective_date, :status, true, 0
                    )
                    RETURNING document_id::text
                """),
                {
                    "name": "Artificial Intelligence Act",
                    "description": "EU Regulation on Artificial Intelligence (AI Act)",
                    "content_hash": placeholder_hash,
                    "jurisdiction_id": eu_jurisdiction,
                    "doc_type_id": reg_type,
                    "language_id": en_lang,
                    "version": "1.0",
                    "effective_date": "2024-05-25",
                    "status": "active",
                },
            ).scalar()
            doc_id = result
            logger.info("Created new document: %s", doc_id)

        # Update existing document if needed
        if eu_ai_doc:
            conn.execute(
                text("""
                    UPDATE documents
                    SET jurisdiction_id = CAST(:jurisdiction_id AS UUID),
                        doc_type_id = CAST(:doc_type_id AS UUID),
                        language_id = CAST(:language_id AS UUID),
                        version = :version,
                        effective_date = :effective_date,
                        status = :status,
                        is_latest = true
                    WHERE document_id = CAST(:doc_id AS UUID)
                """),
                {
                    "jurisdiction_id": eu_jurisdiction,
                    "doc_type_id": reg_type,
                    "language_id": en_lang,
                    "version": "1.0",
                    "effective_date": "2024-05-25",
                    "status": "active",
                    "doc_id": doc_id,
                },
            )
            logger.info("Updated document with jurisdiction and metadata")

        # Create document version record
        conn.execute(
            text("""
                INSERT INTO document_versions (
                    document_id, version, effective_date, change_summary
                )
                SELECT
                    CAST(:doc_id AS UUID), :version, :effective_date, :summary
                WHERE NOT EXISTS (
                    SELECT 1 FROM document_versions
                    WHERE document_id = CAST(:doc_id AS UUID) AND version = :version
                )
            """),
            {
                "doc_id": doc_id,
                "version": "1.0",
                "effective_date": "2024-05-25",
                "summary": "Initial EU AI Act (Regulation 2024/1689)",
            },
        )
        logger.info("Created version record")

    # Update Chroma collection metadata
    logger.info("Updating Chroma chunks with new metadata...")
    try:
        from legal_ai.services import vector_store

        collection = vector_store.get_collection()

        # Get all chunks with the EU AI Act name
        results = collection.get(where={"name": {"$eq": "Artificial Intelligence Act"}})

        if not results or not results["ids"]:
            logger.warning("No chunks found in Chroma collection")
            return

        chunk_ids = results["ids"]
        logger.info("Found %d chunks to update", len(chunk_ids))

        # Update metadata for each chunk
        updated_metadatas = []
        for i, old_metadata in enumerate(results.get("metadatas", [])):
            updated_metadata = {
                "name": old_metadata.get("name", "Artificial Intelligence Act"),
                "description": old_metadata.get(
                    "description", "EU Regulation on Artificial Intelligence (AI Act)"
                ),
                "jurisdiction_id": eu_jurisdiction,
                "jurisdiction_code": "EU",
                "document_id": doc_id,
                "version": "1.0",
                "status": "active",
                "section_title": old_metadata.get("section_title", ""),
                "chunk_index": i,
                "doc_type": "regulation",
                "effective_date": "2024-05-25",
                "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689",
                "uploaded_by": old_metadata.get("uploaded_by"),
            }
            updated_metadatas.append(updated_metadata)

        # Update in batches
        batch_size = 100
        for i in range(0, len(chunk_ids), batch_size):
            batch_ids = chunk_ids[i : i + batch_size]
            batch_metadatas = updated_metadatas[i : i + batch_size]

            collection.update(ids=batch_ids, metadatas=batch_metadatas)
            logger.info("Updated %d/%d chunks", min(i + batch_size, len(chunk_ids)), len(chunk_ids))

        logger.info("Successfully migrated EU AI Act to new schema")

    except Exception as e:
        logger.warning(
            "Could not update Chroma chunks (non-fatal; they refresh on next ingest): %s", e
        )


if __name__ == "__main__":
    from legal_ai.core.logging import configure_logging

    configure_logging()
    migrate_eu_ai_act()

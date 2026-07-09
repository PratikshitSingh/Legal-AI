"""Document queries: upload records and the document audit trail."""

import json
import logging

from sqlalchemy import text

from ._engine import DOCUMENT_COLUMNS, get_engine, with_retry

logger = logging.getLogger(__name__)


def create_document_record(
    name: str,
    description: str,
    content_hash: str,
    uploaded_by_user_id: str,
    file_type: str = "pdf",
    chunk_count: int = 0,
    metadata: dict | None = None,
) -> dict | None:
    """Create a record for an uploaded document in the documents table.

    Args:
        name: Document name
        description: Document description
        content_hash: MD5 hash of document content (for duplicate detection)
        uploaded_by_user_id: UUID of admin uploading document
        file_type: File type ('pdf' or 'txt')
        chunk_count: Number of chunks created in Chroma
        metadata: Additional metadata (file size, text length, etc.)

    Returns:
        Document record dict with document_id, or None if error
    """
    if metadata is None:
        metadata = {}

    engine = get_engine()
    try:
        with engine.begin() as conn:
            result = (
                conn.execute(
                    text(
                        """
                        INSERT INTO documents (name, description, content_hash, uploaded_by, file_type, chunk_count, metadata)
                        VALUES (:name, :description, :content_hash, CAST(:uploaded_by_user_id AS UUID), :file_type, :chunk_count, :metadata::jsonb)
                        RETURNING document_id::text, name, description, created_at
                        """
                    ),
                    {
                        "name": name,
                        "description": description,
                        "content_hash": content_hash,
                        "uploaded_by_user_id": uploaded_by_user_id,
                        "file_type": file_type,
                        "chunk_count": chunk_count,
                        # json.dumps, NOT str(dict).replace("'", '"') — the latter
                        # produces invalid JSON for None/True/False and any value
                        # containing an apostrophe, making the insert fail.
                        "metadata": json.dumps(metadata),
                    },
                )
                .mappings()
                .first()
            )

        return dict(result) if result else None
    except Exception:
        logger.exception("Error creating document record")
        return None


@with_retry
def get_document_by_name_hash(name: str, content_hash: str) -> dict | None:
    """Fetch document by name and content hash (exact match for duplicate detection).

    Args:
        name: Document name
        content_hash: MD5 hash of document content

    Returns:
        Document dict, or None if not found
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    f"""
                    SELECT {DOCUMENT_COLUMNS}
                    FROM documents
                    WHERE name = :name AND content_hash = :content_hash
                    LIMIT 1
                    """
                ),
                {"name": name, "content_hash": content_hash},
            )
            .mappings()
            .first()
        )

    return dict(row) if row else None


@with_retry
def get_all_documents(limit: int = 100, offset: int = 0) -> list[dict]:
    """Fetch all uploaded documents with pagination.

    Args:
        limit: Maximum documents to return
        offset: Number of documents to skip

    Returns:
        List of document dicts (including the uploader's email)
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT
                        d.document_id::text, d.name, d.description, d.content_hash,
                        d.uploaded_by::text, u.email as uploaded_by_email,
                        d.file_type, d.chunk_count,
                        d.created_at, d.updated_at, d.metadata
                    FROM documents d
                    LEFT JOIN users u ON d.uploaded_by = u.user_id
                    ORDER BY d.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            )
            .mappings()
            .all()
        )

    return [dict(row) for row in rows]


def log_document_audit(
    document_id: str, user_id: str, action: str, details: dict | None = None
) -> None:
    """Log document action to audit trail.

    Args:
        document_id: Document ID
        user_id: User ID performing action
        action: Action type ('upload', 'delete', 'view', etc.)
        details: Additional details (JSON)
    """
    if details is None:
        details = {}

    engine = get_engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO document_audit_log (document_id, user_id, action, details)
                    VALUES (CAST(:document_id AS UUID), CAST(:user_id AS UUID), :action, :details::jsonb)
                    """
                ),
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "action": action,
                    "details": json.dumps(details),
                },
            )
    except Exception:
        logger.exception("Error logging document audit")

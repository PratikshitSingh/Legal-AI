"""Document management orchestration: upload preflight, ingestion, bulk import.

The admin page renders forms and progress; the multi-step work (extract →
hash → duplicate-check → embed → record → audit) lives here.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from legal_ai import db
from legal_ai.services import embed

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_MB = 50


def preflight_check(file_bytes: bytes, file_type: str, document_name: str) -> dict:
    """Analyze an upload before embedding: extract text, hash, check duplicates.

    Args:
        file_bytes: Raw file content
        file_type: 'pdf' or 'txt'
        document_name: Name used for duplicate detection

    Returns:
        {
            'text': str,               # extracted text
            'content_hash': str,       # MD5 of the text
            'duplicates': dict,        # embed.check_duplicate_document result
            'estimated_chunks': int,   # chunk count if embedded
        }

    Raises:
        ValueError: If the file type is unsupported or extraction fails
    """
    text = embed.extract_text_from_file(file_bytes, file_type)
    content_hash = embed.get_document_hash(text)
    duplicates = embed.check_duplicate_document(document_name, content_hash)
    return {
        "text": text,
        "content_hash": content_hash,
        "duplicates": duplicates,
        "estimated_chunks": len(embed.split_text_into_sections(text, 1000)),
    }


def upload_document(
    *,
    file_bytes: bytes,
    document_name: str,
    document_description: str,
    uploaded_by_user_id: UUID | str,
    file_type: str,
) -> dict:
    """Ingest one uploaded document and record the audit event.

    Returns embed.ingest_custom_document's result dict (success, message,
    document_id, chunks_added, is_duplicate, existing_chunks).
    """
    result = embed.ingest_custom_document(
        file_bytes=file_bytes,
        document_name=document_name,
        document_description=document_description,
        uploaded_by_user_id=uploaded_by_user_id,
        file_type=file_type,
    )

    if result["success"] and result["document_id"]:
        db.log_document_audit(
            result["document_id"],
            uploaded_by_user_id,
            "upload",
            {"file_type": file_type, "chunks_added": result["chunks_added"]},
        )

    return result


@dataclass
class BulkImportResult:
    """Outcome of a CSV bulk import."""

    imported: int = 0
    failed: int = 0
    warnings: list[str] = field(default_factory=list)


def bulk_import_from_csv(
    rows: list[dict],
    uploaded_by_user_id: UUID | str,
    *,
    progress_cb: Callable[[float], None] | None = None,
    status_cb: Callable[[str], None] | None = None,
) -> BulkImportResult:
    """Import documents listed in CSV rows.

    Each row needs ``file_path`` and ``document_name`` (``description`` is
    optional); files are read from the local filesystem. Failures are counted
    per row and never abort the batch.

    Args:
        rows: CSV rows as dicts
        uploaded_by_user_id: Admin performing the import (for audit)
        progress_cb: Optional callback receiving completion fraction (0..1)
        status_cb: Optional callback receiving human-readable warnings as
                   they happen (e.g. missing files)
    """
    result = BulkImportResult()

    for idx, row in enumerate(rows):
        try:
            file_path = row.get("file_path")
            if not file_path:
                result.failed += 1
                continue

            try:
                with open(file_path, "rb") as f:
                    file_bytes = f.read()
            except FileNotFoundError:
                message = f"File not found: {file_path}"
                result.warnings.append(message)
                if status_cb:
                    status_cb(message)
                result.failed += 1
                continue

            document_name = row.get("document_name", "Untitled")
            description = row.get("description", "")
            file_type = file_path.split(".")[-1].lower()

            ingest = embed.ingest_custom_document(
                file_bytes=file_bytes,
                document_name=document_name,
                document_description=description,
                uploaded_by_user_id=uploaded_by_user_id,
                file_type=file_type,
            )

            if ingest["success"]:
                result.imported += 1
                if ingest.get("document_id"):
                    db.log_document_audit(
                        ingest["document_id"],
                        uploaded_by_user_id,
                        "bulk_import",
                        {"file_type": file_type, "chunks_added": ingest["chunks_added"]},
                    )
                else:
                    message = (
                        f"Bulk import succeeded but no document_id was recorded for {file_path}"
                    )
                    result.warnings.append(message)
                    if status_cb:
                        status_cb(message)
            else:
                result.failed += 1

        except Exception:
            logger.exception("Bulk import failed for row %d", idx)
            result.failed += 1

        if progress_cb:
            progress_cb((idx + 1) / len(rows))

    return result

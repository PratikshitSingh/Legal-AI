"""Offline ingestion: download EU AI Act PDF → chunk → embed → Chroma DB."""

import argparse
import hashlib
import time
from pathlib import Path
from uuid import UUID

import chromadb
import fitz
import requests
from chromadb.utils import embedding_functions
from tqdm import tqdm

from legal_ai.core import utils, constants

# Gemini free tier: ~100 embed requests/min; each doc in a batch counts as one request
EMBED_BATCH_SIZE = 50
EMBED_BATCH_DELAY_SEC = 65
INGEST_MIN_CHUNKS = 500

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
}


def _is_pdf(data: bytes) -> bool:
    return len(data) > 4 and data[:4] == b"%PDF"


def _pdf_bytes_to_text(pdf_data: bytes) -> str:
    document = fitz.open(stream=pdf_data, filetype="pdf")
    text = ""
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        text += page.get_text()
    document.close()
    if not text.strip():
        raise ValueError("PDF downloaded but no extractable text was found.")
    return text


def _cache_pdf(pdf_data: bytes) -> None:
    cache_path = Path(constants.EUROPEAN_ACT_CACHE_PATH)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(pdf_data)


def _download_pdf(url: str) -> bytes:
    response = requests.get(url, timeout=120, headers=_FETCH_HEADERS)
    response.raise_for_status()
    pdf_data = response.content
    if not pdf_data or not _is_pdf(pdf_data):
        raise ValueError(
            f"Invalid or empty PDF from {url} "
            f"(status {response.status_code}, {len(pdf_data)} bytes)"
        )
    return pdf_data


def fetch_pdf_bytes(urls: list[str] | None = None) -> bytes:
    """Download EU AI Act PDF, using cache and fallback URLs."""
    cache_path = Path(constants.EUROPEAN_ACT_CACHE_PATH)
    if cache_path.is_file():
        cached = cache_path.read_bytes()
        if _is_pdf(cached):
            return cached

    candidates = urls or [constants.EUROPEAN_ACT_URL, *constants.EUROPEAN_ACT_FALLBACK_URLS]
    errors: list[str] = []
    for url in candidates:
        try:
            pdf_data = _download_pdf(url)
            _cache_pdf(pdf_data)
            return pdf_data
        except Exception as e:
            errors.append(f"{url}: {e}")

    raise ValueError(
        "Could not download the EU AI Act PDF from any source.\n"
        + "\n".join(errors)
        + "\nPlace a copy at data/eu_ai_act.pdf and retry."
    )


def split_text_into_sections(text: str, min_chars_per_section: int) -> list[str]:
    paragraphs = text.split("\n")
    sections: list[str] = []
    current_section = ""
    current_length = 0

    for paragraph in paragraphs:
        paragraph_length = len(paragraph)
        if current_length + paragraph_length + 2 <= min_chars_per_section:
            current_section += paragraph + "\n\n"
            current_length += paragraph_length + 2
        else:
            if current_section:
                sections.append(current_section.strip())
            current_section = paragraph + "\n\n"
            current_length = paragraph_length + 2

    if current_section:
        sections.append(current_section.strip())

    return sections


def get_document_hash(text: str) -> str:
    """Compute MD5 hash of document content for duplicate detection."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def extract_text_from_file(file_bytes: bytes, file_type: str) -> str:
    """Extract text from uploaded file (PDF or TXT).
    
    Args:
        file_bytes: Raw file content
        file_type: File type ('pdf' or 'txt')
    
    Returns:
        Extracted text string
    
    Raises:
        ValueError: If file type unsupported or extraction fails
    """
    if file_type.lower() == "pdf":
        return _pdf_bytes_to_text(file_bytes)
    elif file_type.lower() == "txt":
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("TXT file must be valid UTF-8 encoded")
    else:
        raise ValueError(f"Unsupported file type: {file_type}. Supported: pdf, txt")


def check_duplicate_document(document_name: str, content_hash: str) -> dict:
    """Check if document already exists (preflight validation).
    
    Queries Chroma collection metadata for existing document with same name,
    then checks Postgres documents table for exact name+hash match.
    
    Args:
        document_name: Name of document to check
        content_hash: MD5 hash of document content
    
    Returns:
        {
            'is_duplicate': bool,
            'existing_chunks': int (total chunks with same name),
            'existing_exact_match': bool (name + hash match),
            'new_chunks_estimate': int (estimated new chunks for this document)
        }
    """
    from legal_ai.db import db
    
    collection = _get_collection()
    
    # Query Chroma collection for existing document with same name
    existing_chunks = 0
    try:
        results = collection.get(
            where={"name": {"$eq": document_name}},
            include=[]  # Only count, don't fetch data
        )
        existing_chunks = len(results.get("ids", [])) if results else 0
    except Exception:
        # Chroma query might not support exact equality; try anyway
        pass
    
    # Query Postgres documents table for exact name+hash match
    existing_exact_match = False
    try:
        existing_doc = db.get_document_by_name_hash(document_name, content_hash)
        existing_exact_match = existing_doc is not None
    except Exception:
        # DB might not have documents table yet
        pass
    
    is_duplicate = existing_exact_match or (existing_chunks > 0)
    
    return {
        "is_duplicate": is_duplicate,
        "existing_chunks": existing_chunks,
        "existing_exact_match": existing_exact_match,
        "new_chunks_estimate": 0 if existing_exact_match else -1,  # -1 means unknown until we process
    }


def _get_collection(*, force: bool = False):
    sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-mpnet-base-v2",
    )
    if utils.use_chroma_cloud():
        client = utils.get_chroma_client()
    else:
        client = chromadb.PersistentClient(path=utils.DB_FOLDER)

    if force:
        try:
            client.delete_collection(utils.COLLECTION_NAME)
            print(f"Deleted collection {utils.COLLECTION_NAME}")
        except Exception:
            pass

    return client.get_or_create_collection(
        name=utils.COLLECTION_NAME,
        embedding_function=sentence_transformer_ef,
    )


def embed_text_in_chromadb(
    text: str,
    document_name: str,
    document_description: str,
    persist_directory: str = utils.DB_FOLDER,
    *,
    force: bool = False,
    uploaded_by_user_id: UUID | None = None,
    skip_duplicate_chunks: bool = False,
    existing_chunk_ids: set[str] | None = None,
) -> int:
    """Embed text into Chroma DB with optional duplicate chunk skipping.
    
    Args:
        text: Text content to embed
        document_name: Name of document
        document_description: Description of document
        persist_directory: Directory for Chroma persistence
        force: Delete and recreate collection
        uploaded_by_user_id: UUID of user uploading document (for audit)
        skip_duplicate_chunks: If True, skip chunks already in collection
        existing_chunk_ids: Set of chunk IDs that already exist (for skipping)
    
    Returns:
        Number of new chunks added
    """
    documents = [
        doc for doc in split_text_into_sections(text, 1000) if doc and doc.strip()
    ]
    if not documents:
        raise ValueError(
            "No text to embed. Check the PDF URL or network access, then re-run embed.py."
        )

    metadata = {
        "name": document_name,
        "description": document_description,
    }
    if uploaded_by_user_id:
        metadata["uploaded_by"] = str(uploaded_by_user_id)
    
    metadatas = [metadata] * len(documents)

    _ = persist_directory  # local path used via utils.DB_FOLDER in _get_collection
    collection = _get_collection(force=force)

    count = collection.count()
    print(f"Collection already contains {count} documents")
    ids = [str(i) for i in range(count, count + len(documents))]
    
    # Filter out duplicate chunks if requested
    if skip_duplicate_chunks and existing_chunk_ids:
        filtered_ids = []
        filtered_documents = []
        filtered_metadatas = []
        
        for doc_id, doc_text, doc_metadata in zip(ids, documents, metadatas):
            if doc_id not in existing_chunk_ids:
                filtered_ids.append(doc_id)
                filtered_documents.append(doc_text)
                filtered_metadatas.append(doc_metadata)
        
        if not filtered_documents:
            print("All chunks already exist in collection. Skipping embedding.")
            return 0

        skipped = len(ids) - len(filtered_ids)
        ids = filtered_ids
        documents = filtered_documents
        metadatas = filtered_metadatas
        if skipped:
            print(f"Skipping {skipped} duplicate chunks")

    chunks_added = 0
    for i in tqdm(
        range(0, len(documents), EMBED_BATCH_SIZE),
        desc="Adding documents",
        unit_scale=EMBED_BATCH_SIZE,
    ):
        end = min(i + EMBED_BATCH_SIZE, len(documents))
        while True:
            try:
                collection.add(
                    ids=ids[i:end],
                    documents=documents[i:end],
                    metadatas=metadatas[i:end],
                )
                chunks_added += (end - i)
                break
            except ValueError as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    print("Rate limited — waiting before retry…")
                    time.sleep(EMBED_BATCH_DELAY_SEC)
                else:
                    raise
        if end < len(documents):
            time.sleep(EMBED_BATCH_DELAY_SEC)

    new_count = collection.count()
    print(f"Added {chunks_added} new chunks (collection now has {new_count} total)")
    return chunks_added


def ingest_custom_document(
    file_bytes: bytes,
    document_name: str,
    document_description: str,
    uploaded_by_user_id: UUID,
    file_type: str = "pdf",
) -> dict:
    """Ingest custom document with preflight duplicate detection.
    
    Orchestrates the full upload flow:
    1. Extract text from file
    2. Compute content hash
    3. Check for duplicates (preflight)
    4. Skip or embed based on duplicate status
    5. Record in documents table
    
    Args:
        file_bytes: Raw file content
        document_name: Name of document
        document_description: Description of document
        uploaded_by_user_id: UUID of admin uploading document
        file_type: File type ('pdf' or 'txt')
    
    Returns:
        {
            'success': bool,
            'message': str,
            'document_id': str | None,
            'chunks_added': int,
            'is_duplicate': bool,
            'existing_chunks': int,
        }
    """
    from legal_ai.db import db
    
    try:
        # Step 1: Extract text
        print(f"Extracting text from {file_type.upper()}…")
        text = extract_text_from_file(file_bytes, file_type)
        print(f"Extracted {len(text)} characters")
        
        # Step 2: Compute hash
        content_hash = get_document_hash(text)
        print(f"Content hash: {content_hash}")
        
        # Step 3: Preflight check for duplicates
        print("Checking for duplicates…")
        dup_check = check_duplicate_document(document_name, content_hash)
        print(f"Duplicate check result: {dup_check}")
        
        # Step 4: Exact duplicates are NOT re-embedded and NOT re-recorded.
        # (Previously the skip flag was passed with existing_chunk_ids=None,
        # which disabled skipping — duplicates were silently re-embedded while
        # the UI claimed nothing was added, and a second document record was
        # created for the same content.)
        if dup_check["existing_exact_match"]:
            existing_doc = db.get_document_by_name_hash(document_name, content_hash)
            return {
                "success": True,
                "message": (
                    f"⚠️ Duplicate document detected! No new chunks added "
                    f"(existing: {dup_check['existing_chunks']} chunks)."
                ),
                "document_id": str(existing_doc["document_id"]) if existing_doc else None,
                "chunks_added": 0,
                "is_duplicate": True,
                "existing_chunks": dup_check["existing_chunks"],
            }

        # Step 5: Embed new content
        print("Embedding into Chroma…")
        chunks_added = embed_text_in_chromadb(
            text,
            document_name,
            document_description,
            uploaded_by_user_id=uploaded_by_user_id,
        )

        # Step 6: Record in documents table
        print("Recording in documents table…")
        doc_record = db.create_document_record(
            name=document_name,
            description=document_description,
            content_hash=content_hash,
            uploaded_by_user_id=uploaded_by_user_id,
            file_type=file_type,
            chunk_count=chunks_added,
            metadata={
                "file_size_bytes": len(file_bytes),
                "text_length_chars": len(text),
            },
        )

        return {
            "success": True,
            "message": f"✅ Document uploaded successfully! Added {chunks_added} chunks.",
            "document_id": str(doc_record["document_id"]) if doc_record else None,
            "chunks_added": chunks_added,
            "is_duplicate": False,
            "existing_chunks": dup_check["existing_chunks"],
        }
    
    except Exception as e:
        error_msg = f"❌ Error ingesting document: {str(e)}"
        print(error_msg)
        return {
            "success": False,
            "message": error_msg,
            "document_id": None,
            "chunks_added": 0,
            "is_duplicate": False,
            "existing_chunks": 0,
        }


DOCUMENT_NAME = "Artificial Intelligence Act"
DOCUMENT_DESCRIPTION = "Artificial Intelligence Act"


def ingest_complete() -> bool:
    if not utils.chroma_collection_has_documents():
        return False
    collection = _get_collection()
    return collection.count() >= INGEST_MIN_CHUNKS


def run_ingest(*, force: bool = False) -> None:
    if not force and ingest_complete():
        print("Collection already fully ingested. Use --force to re-ingest.")
        return

    print("Fetching EU AI Act PDF…")
    pdf_data = fetch_pdf_bytes()
    print(f"PDF ready ({len(pdf_data)} bytes at {constants.EUROPEAN_ACT_CACHE_PATH})")

    print("Extracting text…")
    text = _pdf_bytes_to_text(pdf_data)
    print(f"Extracted {len(text)} characters")

    print("Embedding into Chroma…")
    embed_text_in_chromadb(
        text,
        DOCUMENT_NAME,
        DOCUMENT_DESCRIPTION,
        force=force,
    )
    print("Ingest complete.")


if __name__ == "__main__":
    # Initialize tracing (LangFuse) - best practice for batch processes
    utils.setup_langfuse_tracing()
    
    try:
        parser = argparse.ArgumentParser(description="Download EU AI Act PDF and embed into Chroma")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing collection and re-ingest from scratch",
        )
        args = parser.parse_args()
        run_ingest(force=args.force)
    finally:
        # Best practice: flush traces before script exit (batch process)
        utils.flush_langfuse_traces()

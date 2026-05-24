"""Offline ingestion: download EU AI Act PDF → chunk → embed → Chroma DB."""

import argparse
import time
from pathlib import Path

import chromadb
import fitz
import requests
from chromadb.utils import embedding_functions
from tqdm import tqdm

import utils as Utils

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
    cache_path = Path(Utils.EUROPEAN_ACT_CACHE_PATH)
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
    cache_path = Path(Utils.EUROPEAN_ACT_CACHE_PATH)
    if cache_path.is_file():
        cached = cache_path.read_bytes()
        if _is_pdf(cached):
            return cached

    candidates = urls or [Utils.EUROPEAN_ACT_URL, *Utils.EUROPEAN_ACT_FALLBACK_URLS]
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


def pdf_to_text(url: str | None = None) -> str:
    try:
        if url:
            pdf_data = _download_pdf(url)
            _cache_pdf(pdf_data)
        else:
            pdf_data = fetch_pdf_bytes()
        return _pdf_bytes_to_text(pdf_data)
    except Exception as e:
        print(f"An error occurred: {e}")
        raise


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


def _get_collection(*, force: bool = False):
    Utils.get_gemini_api_key()
    emb_cfg = Utils.get_embedding_settings()
    gemini_ef = embedding_functions.GoogleGeminiEmbeddingFunction(
        model_name=emb_cfg["model"],
        api_key_env_var=emb_cfg["api_key_env"],
    )
    if Utils.use_chroma_cloud():
        client = Utils.get_chroma_client()
    else:
        client = chromadb.PersistentClient(path=Utils.DB_FOLDER)

    if force:
        try:
            client.delete_collection(Utils.COLLECTION_NAME)
            print(f"Deleted collection {Utils.COLLECTION_NAME}")
        except Exception:
            pass

    return client.get_or_create_collection(
        name=Utils.COLLECTION_NAME,
        embedding_function=gemini_ef,
    )


def embed_text_in_chromadb(
    text: str,
    document_name: str,
    document_description: str,
    persist_directory: str = Utils.DB_FOLDER,
    *,
    force: bool = False,
) -> None:
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
    metadatas = [metadata] * len(documents)

    _ = persist_directory  # local path used via Utils.DB_FOLDER in _get_collection
    collection = _get_collection(force=force)

    count = collection.count()
    print(f"Collection already contains {count} documents")
    ids = [str(i) for i in range(count, count + len(documents))]

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
    print(f"Added {new_count - count} documents")


DOCUMENT_NAME = "Artificial Intelligence Act"
DOCUMENT_DESCRIPTION = "Artificial Intelligence Act"


def ingest_complete() -> bool:
    if not Utils.chroma_collection_has_documents():
        return False
    collection = _get_collection()
    return collection.count() >= INGEST_MIN_CHUNKS


def run_ingest(*, force: bool = False) -> None:
    if not force and ingest_complete():
        print("Collection already fully ingested. Use --force to re-ingest.")
        return

    print("Fetching EU AI Act PDF…")
    pdf_data = fetch_pdf_bytes()
    print(f"PDF ready ({len(pdf_data)} bytes at {Utils.EUROPEAN_ACT_CACHE_PATH})")

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
    parser = argparse.ArgumentParser(description="Download EU AI Act PDF and embed into Chroma")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing collection and re-ingest from scratch",
    )
    args = parser.parse_args()
    run_ingest(force=args.force)

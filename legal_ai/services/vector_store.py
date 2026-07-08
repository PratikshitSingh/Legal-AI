"""Single home for the Chroma client, collection, and embedding function.

Chroma Cloud is used when the CHROMA_* environment variables are set;
otherwise a local persistent store under ``chroma_storage/``.
"""

import logging
import os

import chromadb
from chromadb.utils import embedding_functions

from legal_ai.core.constants import COLLECTION_NAME, DB_FOLDER, EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)


def use_chroma_cloud() -> bool:
    """Check if Chroma Cloud is configured."""
    return bool(
        os.getenv("CHROMA_API_KEY") and os.getenv("CHROMA_TENANT") and os.getenv("CHROMA_DATABASE")
    )


def get_chroma_client():
    """Return a Chroma Cloud or local persistent client."""
    if use_chroma_cloud():
        return chromadb.CloudClient(
            api_key=os.environ["CHROMA_API_KEY"],
            tenant=os.environ["CHROMA_TENANT"],
            database=os.environ["CHROMA_DATABASE"],
        )
    return chromadb.PersistentClient(path=DB_FOLDER)


def get_collection(*, force: bool = False):
    """Get (or create) the app's document collection with its embedding function.

    Args:
        force: Delete any existing collection first (full re-ingest).
    """
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL_NAME,
    )
    client = get_chroma_client()

    if force:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("Deleted collection %s", COLLECTION_NAME)
        except Exception:
            logger.debug("No existing collection %s to delete", COLLECTION_NAME)

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )


def collection_has_documents() -> bool:
    """Check whether the document collection exists and is non-empty."""
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        return collection.count() > 0
    except Exception:
        return False

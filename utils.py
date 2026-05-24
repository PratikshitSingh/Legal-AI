import json as JS
import os as OS
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
ARTICLES_FILE = "articles.json"
ARTICLES_FOLDER = "articles"
DB_FOLDER = str(ROOT / "chroma_storage")
DATA_FOLDER = str(ROOT / "data")
# europarl doceo links often return 202 + empty body for scripted clients
EUROPEAN_ACT_URL = (
    "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689"
)
EUROPEAN_ACT_FALLBACK_URLS = [
    "https://artificialintelligenceact.eu/wp-content/uploads/2024/04/TA-9-2024-0138_EN.pdf",
    "https://data.consilium.europa.eu/doc/document/PE-24-2024-REV-1/en/pdf",
]
EUROPEAN_ACT_CACHE_PATH = str(Path(DATA_FOLDER) / "eu_ai_act.pdf")
COLLECTION_NAME = "collection_1"


def use_chroma_cloud() -> bool:
    return bool(
        OS.getenv("CHROMA_API_KEY")
        and OS.getenv("CHROMA_TENANT")
        and OS.getenv("CHROMA_DATABASE")
    )


def get_chroma_cloud_settings() -> dict[str, str]:
    api_key = OS.getenv("CHROMA_API_KEY")
    tenant = OS.getenv("CHROMA_TENANT")
    database = OS.getenv("CHROMA_DATABASE")
    if not api_key or not tenant or not database:
        raise ValueError(
            "Chroma Cloud requires CHROMA_API_KEY, CHROMA_TENANT, and CHROMA_DATABASE in .env"
        )
    return {"api_key": api_key, "tenant": tenant, "database": database}


def get_chroma_client():
    """Return a Chroma Cloud or local persistent client."""
    import chromadb

    if use_chroma_cloud():
        cfg = get_chroma_cloud_settings()
        return chromadb.CloudClient(
            api_key=cfg["api_key"],
            tenant=cfg["tenant"],
            database=cfg["database"],
        )
    return chromadb.PersistentClient(path=DB_FOLDER)


def chroma_collection_has_documents() -> bool:
    client = get_chroma_client()
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
        return collection.count() > 0
    except Exception:
        return False


def get_gemini_api_key() -> str:
    config = load_config()
    env_name = config.get("embeddings", {}).get("api_key_env", "GEMINI_API_KEY")
    key = OS.getenv(env_name) or OS.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            f"Set {env_name} in .env (Google AI Studio API key). "
            "Get one at https://aistudio.google.com/apikey"
        )
    OS.environ.setdefault("GEMINI_API_KEY", key)
    OS.environ.setdefault("GOOGLE_API_KEY", key)
    return key


def get_embedding_settings() -> dict:
    config = load_config()
    emb = config.get("embeddings", {})
    return {
        "model": emb.get("model", "gemini-embedding-001"),
        "task_type": emb.get("task_type", "RETRIEVAL_DOCUMENT"),
        "api_key_env": emb.get("api_key_env", "GEMINI_API_KEY"),
    }


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_articles(file_name: str) -> list:
    result = []
    if OS.path.exists(file_name):
        with open(file_name, encoding="utf-8") as file:
            try:
                result = JS.load(file)
            except JS.JSONDecodeError:
                print("File exists but is not valid JSON. Returning empty object.")
    else:
        with open(file_name, "w", encoding="utf-8") as file:
            JS.dump("[{}]", file)
        print(f"File '{file_name}' did not exist and was created.")
        OS.makedirs(ARTICLES_FOLDER, exist_ok=True)
        print("'articles' directory was created")

    return result


def save_articles(file_name: str, data) -> None:
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            JS.dump(data, file, indent=4)
            print(f"Data successfully saved to '{file_name}'.")
    except Exception as e:
        print(f"Error: trying to save articles data [{e}]")


def save_article_content(file_name: str, content: str) -> None:
    try:
        with open(file_name, "w", encoding="utf-8") as file:
            file.write(content)
    except IOError as e:
        print(f"An IOError occurred: {e.strerror}")
    except Exception as e:
        print(f"Error: {e}")
    else:
        print(f"Content successfully written to '{file_name}'.")


def load_article_content(file_name: str) -> str:
    result = ""
    try:
        with open(file_name, encoding="utf-8") as file:
            result = file.read()
    except Exception as e:
        print(
            f"An unexpected error occurred while reading content file '{file_name}': {e}"
        )

    return result

"""Application constants."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

DB_FOLDER = str(ROOT / "chroma_storage")
DATA_FOLDER = str(ROOT / "data")

# europarl doceo links often return 202 + empty body for scripted clients
EUROPEAN_ACT_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32024R1689"
EUROPEAN_ACT_FALLBACK_URLS = [
    "https://artificialintelligenceact.eu/wp-content/uploads/2024/04/TA-9-2024-0138_EN.pdf",
    "https://data.consilium.europa.eu/doc/document/PE-24-2024-REV-1/en/pdf",
]
EUROPEAN_ACT_CACHE_PATH = str(Path(DATA_FOLDER) / "eu_ai_act.pdf")
COLLECTION_NAME = "collection_1"

# One model name, two wrappers: the agent builds LangChain HuggingFaceEmbeddings
# from it while the vector store builds Chroma's SentenceTransformer embedding
# function — they must stay the same model or queries stop matching documents.
EMBEDDING_MODEL_NAME = "all-mpnet-base-v2"

# Configuration file path
CONFIG_FILE = ROOT / "config.yaml"


class SessionKeys:
    """Streamlit ``st.session_state`` keys used across the app.

    The string values are effectively persisted protocol: tests seed them and
    the auth flow round-trips them on every rerun. Rename the attribute, not
    the value.
    """

    USER_ID = "legal_ai_user_id"
    USER_EMAIL = "legal_ai_user_email"
    ACCESS_TOKEN = "legal_ai_access_token"
    REFRESH_TOKEN = "legal_ai_refresh_token"
    USER_ROLE = "legal_ai_user_role"
    USER_FULL_NAME = "legal_ai_user_full_name"
    USER_FIRM = "legal_ai_user_firm"
    SESSION_ID = "legal_ai_session_id"
    SELECTED_SESSION_ID = "selected_session_id"
    MESSAGES = "messages"
    SELECTED_JURISDICTIONS = "selected_jurisdictions"
    AUTH_INITIALIZED = "_legal_ai_auth_initialized"
    LAST_VERIFIED_MAGIC_LINK = "_legal_ai_last_verified_magic_link"
    SIGNED_OUT = "_legal_ai_signed_out"

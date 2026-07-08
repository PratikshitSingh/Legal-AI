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

# Configuration file path
CONFIG_FILE = ROOT / "config.yaml"

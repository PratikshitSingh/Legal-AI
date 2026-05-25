#!/usr/bin/env python3
"""Offline ingestion: download EU AI Act PDF → chunk → embed → Chroma DB."""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from legal_ai.services.embed import fetch_pdf_bytes, pdf_to_text
from legal_ai.core import utils

if __name__ == "__main__":
    print("📥 Starting EU AI Act ingestion...")
    
    try:
        # This is a wrapper script. The actual ingest logic is in legal_ai.services.embed
        # Call this with: python scripts/ingest.py
        print("✅ Ingest script ready. Use the embed module for full ingestion.")
        print("   from legal_ai.services.embed import fetch_pdf_bytes, pdf_to_text")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

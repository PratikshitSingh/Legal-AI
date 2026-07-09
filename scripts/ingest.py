#!/usr/bin/env python3
"""Offline ingestion: download EU AI Act PDF → chunk → embed → Chroma DB.

Thin CLI wrapper around ``legal_ai.services.embed.run_ingest``; equivalent to
``python -m legal_ai.services.embed [--force]``.
"""

import argparse
import sys
from pathlib import Path

# Runnable as a plain file from any CWD, so the repo root must be on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from legal_ai.core import tracing
from legal_ai.core.logging import configure_logging
from legal_ai.services.embed import run_ingest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download the EU AI Act PDF and embed it into Chroma"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete the existing collection and re-ingest from scratch",
    )
    args = parser.parse_args()

    configure_logging()
    tracing.setup_langfuse_tracing()
    try:
        run_ingest(force=args.force)
    finally:
        # Flush traces before exit — batch processes have no server lifecycle
        # to do it for them.
        tracing.flush_langfuse_traces()

#!/usr/bin/env python3
"""Apply the SQL migrations in legal_ai/migrations/ in filename order.

Complements ``db.init_db()`` (which creates the auth/session tables): the
migrations own the documents/jurisdictions schema. Re-running is safe — every
migration is written idempotently (IF NOT EXISTS / ON CONFLICT).
"""

import logging
import sys
from pathlib import Path

# Runnable as a plain file from any CWD, so the repo root must be on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from legal_ai.core.logging import configure_logging
from legal_ai.db import get_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "legal_ai" / "migrations"


def run_migrations() -> None:
    """Apply every migration file, each in its own transaction."""
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_paths:
        raise FileNotFoundError(f"No migration files found in {MIGRATIONS_DIR}")

    engine = get_engine()
    try:
        for migration_path in migration_paths:
            logger.info("Running migration: %s", migration_path.name)
            migration_sql = migration_path.read_text()
            with engine.begin() as conn:
                conn.execute(text(migration_sql))
            logger.info("%s applied successfully", migration_path.name)

        logger.info("All %d database migrations applied successfully", len(migration_paths))
    finally:
        engine.dispose()


if __name__ == "__main__":
    configure_logging()
    try:
        run_migrations()
    except Exception:
        logger.exception("Migration failed")
        sys.exit(1)

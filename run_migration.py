#!/usr/bin/env python3
"""Apply all database migrations in sequence."""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("NEON_DB_DATABASE_URL")
if not url:
    print("❌ NEON_DB_DATABASE_URL not found in .env")
    exit(1)

print("📊 Applying database migrations...")
engine = create_engine(url)

# List of migrations in order
migrations = [
    "001_add_user_profile_and_rbac.sql",
    "002_add_documents_tracking_table.sql",
    "003_jurisdictions_hierarchy.sql",
    "004_refactor_documents.sql",
    "005_seed_world_jurisdiction.sql",
    "006_fix_documents_uploaded_by.sql",
]

migrations_dir = Path(__file__).parent / "legal_ai" / "migrations"

try:
    for migration_file in migrations:
        migration_path = migrations_dir / migration_file
        if not migration_path.exists():
            print(f"⚠️  Migration file not found: {migration_file} (skipping)")
            continue
        
        print(f"\n📝 Running migration: {migration_file}")
        
        with open(migration_path) as f:
            migration_sql = f.read()
        
        with engine.begin() as conn:
            # Execute the entire migration as a single transaction
            conn.execute(text(migration_sql))
        
        print(f"   ✅ {migration_file} applied successfully!")
    
    print("\n✅ All database migrations applied successfully!")
except Exception as e:
    print(f"\n❌ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    engine.dispose()

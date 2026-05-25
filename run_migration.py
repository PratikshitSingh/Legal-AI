#!/usr/bin/env python3
"""Apply database migration for RBAC and user profiles."""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("NEON_DB_DATABASE_URL")
if not url:
    print("❌ NEON_DB_DATABASE_URL not found in .env")
    exit(1)

print("📊 Applying database migration...")
engine = create_engine(url)

try:
    with open("migrations/001_add_user_profile_and_rbac.sql") as f:
        migration_sql = f.read()
    
    with engine.begin() as conn:
        # Execute the entire migration as a single transaction
        conn.execute(text(migration_sql))
    
    print("✅ Database migration applied successfully!")
except Exception as e:
    print(f"❌ Migration failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)
finally:
    engine.dispose()

"""Seed jurisdictions from JSON into database."""

import json

from legal_ai.db.db import get_engine
from sqlalchemy import text


def load_jurisdictions_from_file(file_path: str = "legal_ai/data/jurisdictions_seed.json") -> dict:
    """Load jurisdiction hierarchy from JSON file."""
    with open(file_path, "r") as f:
        return json.load(f)


def insert_jurisdiction(
    conn,
    code: str,
    name: str,
    level: str,
    parent_jurisdiction_id: str | None = None,
    region_code: str | None = None,
    flag_emoji: str | None = None,
) -> str:
    """Insert a jurisdiction and return its ID."""
    result = conn.execute(
        text(
            """
            INSERT INTO jurisdictions (code, name, level, parent_jurisdiction_id, region_code, flag_emoji)
            VALUES (:code, :name, :level, CAST(:parent_id AS UUID), :region_code, :flag_emoji)
            ON CONFLICT (code) DO UPDATE SET updated_at = NOW()
            RETURNING jurisdiction_id::text
            """
        ),
        {
            "code": code,
            "name": name,
            "level": level,
            "parent_id": parent_jurisdiction_id,
            "region_code": region_code,
            "flag_emoji": flag_emoji,
        },
    ).scalar()
    return result


def seed_jurisdictions(file_path: str | None = None) -> None:
    """
    Load hierarchical jurisdictions from JSON into database.

    Args:
        file_path: Path to jurisdictions_seed.json (defaults to data/jurisdictions_seed.json)
    """
    if file_path is None:
        file_path = "legal_ai/data/jurisdictions_seed.json"

    # Load seed data
    seed_data = load_jurisdictions_from_file(file_path)

    # Get WORLD jurisdiction ID (should exist from migration 005)
    engine = get_engine()
    with engine.begin() as conn:
        world_id = conn.execute(
            text("SELECT jurisdiction_id::text FROM jurisdictions WHERE code = 'WORLD'")
        ).scalar()

        if not world_id:
            print("❌ WORLD jurisdiction not found. Run migrations first.")
            return

        print(f"🌍 Root jurisdiction WORLD: {world_id}")

        # Process regions
        inserted = 0
        for region in seed_data.get("regions", []):
            print(f"\n📍 Region: {region['name']}")

            # Insert region under WORLD
            region_id = insert_jurisdiction(
                conn,
                code=region["code"],
                name=region["name"],
                level=region.get("level", "region"),
                parent_jurisdiction_id=world_id,
                region_code=region["code"],
                flag_emoji=region.get("flag_emoji"),
            )
            inserted += 1
            print(f"  ✅ Inserted region: {region['name']} ({region['code']})")

            # Process countries/states in this region
            for country_or_region in region.get("countries", []):
                # Check if it's an EU-like super-region (has countries inside)
                if "countries" in country_or_region:
                    # It's a super-region like EU
                    super_region_id = insert_jurisdiction(
                        conn,
                        code=country_or_region["code"],
                        name=country_or_region["name"],
                        level=country_or_region.get("level", "region"),
                        parent_jurisdiction_id=region_id,
                        region_code=region["code"],
                        flag_emoji=country_or_region.get("flag_emoji"),
                    )
                    inserted += 1
                    print(
                        f"    ✅ Inserted sub-region: {country_or_region['name']} ({country_or_region['code']})"
                    )

                    # Insert countries under super-region
                    for country in country_or_region.get("countries", []):
                        country_id = insert_jurisdiction(
                            conn,
                            code=country["code"],
                            name=country["name"],
                            level=country.get("level", "country"),
                            parent_jurisdiction_id=super_region_id,
                            region_code=region["code"],
                            flag_emoji=country.get("flag_emoji"),
                        )
                        inserted += 1
                        print(f"      ✅ Inserted country: {country['name']} ({country['code']})")

                else:
                    # It's a regular country
                    country_id = insert_jurisdiction(
                        conn,
                        code=country_or_region["code"],
                        name=country_or_region["name"],
                        level=country_or_region.get("level", "country"),
                        parent_jurisdiction_id=region_id,
                        region_code=region["code"],
                        flag_emoji=country_or_region.get("flag_emoji"),
                    )
                    inserted += 1
                    print(
                        f"    ✅ Inserted country: {country_or_region['name']} ({country_or_region['code']})"
                    )

                    # Insert states (for countries like US)
                    for state in country_or_region.get("states", []):
                        state_id = insert_jurisdiction(
                            conn,
                            code=state["code"],
                            name=state["name"],
                            level=state.get("level", "state"),
                            parent_jurisdiction_id=country_id,
                            region_code=region["code"],
                        )
                        inserted += 1

        print(f"\n✅ Successfully seeded {inserted} jurisdictions!")


if __name__ == "__main__":
    seed_jurisdictions()

#!/usr/bin/env python3
"""Script to set up the sample database."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.interface import create_sample_database
from src.config import settings


def main():
    """Create the sample database with test data."""
    db_path = settings.database_url.replace("sqlite:///", "")

    print(f"Creating sample database at: {db_path}")
    db = create_sample_database(db_path)

    # Verify the database
    print("\nVerifying database contents...")

    tables = db.get_table_names()
    print(f"\nTables created: {', '.join(tables)}")

    for table in tables:
        rows, count = db.execute_query(f"SELECT COUNT(*) as count FROM {table}")
        print(f"  - {table}: {rows[0]['count']} rows")

    print("\n[OK] Sample database created successfully!")
    print("\nYou can now run:")
    print("  - CLI: python -m src.cli")
    print("  - Web:  python -m src.web")

    db.close()


if __name__ == "__main__":
    main()

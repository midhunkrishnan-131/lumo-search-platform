"""Quick diagnostic script to verify PostgreSQL connectivity for LUMO."""

import sys

from app.config import get_settings
from app.database.connection import (
    check_database_connection,
    database_target_label,
    init_database,
)


def main() -> None:
    settings = get_settings()
    target = database_target_label(settings.database_url)
    print(f"Connecting to PostgreSQL at {target}...")

    if not settings.database_url:
        print("[INFO] DATABASE_URL is empty in .env. Database connection skipped.")
        sys.exit(0)

    init_database(settings.database_url)
    if check_database_connection():
        print("[SUCCESS] PostgreSQL connected and responded to SELECT 1 successfully.")
        sys.exit(0)
    else:
        print("[FAILED] Could not connect to PostgreSQL database.")
        print("  1. Verify the PostgreSQL Windows service is running (Get-Service postgresql*).")
        print("  2. Check that the role and password in backend/.env match your PostgreSQL setup.")
        print("  3. Make sure the database exists (e.g. CREATE DATABASE lumo OWNER lumo_user;).")
        sys.exit(1)


if __name__ == "__main__":
    main()

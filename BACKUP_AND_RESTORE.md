# LUMO Backup & Restore Guide (Phase 26)

Implemented in [`backup.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/ops/backup.py) and [`ops.py`](file:///c:/Users/midhu/OneDrive/Desktop/BBX/BBX-inside%20main/Extracted/lumo/backend/app/api/routes/ops.py).

## Manual Backup
- `POST /api/v1/ops/backups?label=manual`: Creates a timestamped backup directory under `backups/` using `sqlite3.backup()` (SQLite) or `pg_dump` (PostgreSQL), copies `backend/data/` and `qdrant_storage/`, and writes SHA-256 checksums to `manifest.json`.
- `GET /api/v1/ops/backups`: Lists available backups.
- `POST /api/v1/ops/backups/{backup_id}/verify`: Verifies every file against its SHA-256 checksum in `manifest.json`.
- `POST /api/v1/ops/backups/prune?keep=5`: Retains the latest `keep` backups.

## Confirmed Restore
- `POST /api/v1/ops/backups/{backup_id}/restore` with JSON body `{"confirm": true}`:
  - Refuses to overwrite unless `confirm: true` is explicitly provided and `verify_backup()` passes.
  - Disposes active DB connections, restores database and files, and re-initializes the database engine.

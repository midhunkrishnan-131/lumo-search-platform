"""LUMO Phase 21 Operational CLI (`python -m app.ops.cli <command>`)."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.database.connection import check_database_connection, init_database
from app.ops.backup import create_backup, list_backups, restore_backup, verify_backup
from app.ops.diagnostics import run_deployment_diagnostics
from app.ops.migrations import apply_safe_migrations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LUMO Operational CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="Run deployment and dependency diagnostics")
    sub.add_parser("migrate", help="Apply non-destructive schema migrations")
    b_p = sub.add_parser("backup", help="Create a timestamped backup")
    b_p.add_argument("--label", default="cli")
    sub.add_parser("list-backups", help="List available backups")
    v_p = sub.add_parser("verify", help="Verify backup integrity")
    v_p.add_argument("backup_id")
    r_p = sub.add_parser("restore", help="Restore a backup (requires --confirm)")
    r_p.add_argument("backup_id")
    r_p.add_argument("--confirm", action="store_true")

    args = parser.parse_args(argv)
    cfg = get_settings()
    init_database(cfg.database_url or "sqlite:///lumo.db")
    if not check_database_connection() and cfg.environment != "test":
        init_database("sqlite:///lumo.db")

    if args.cmd == "check":
        res = run_deployment_diagnostics(cfg)
        print(json.dumps(res, indent=2))
        return 1 if res["overall_status"] == "FAILED" else 0
    if args.cmd == "migrate":
        print(json.dumps(apply_safe_migrations(), indent=2))
        return 0
    if args.cmd == "backup":
        print(json.dumps(create_backup(label=args.label, settings=cfg), indent=2))
        return 0
    if args.cmd == "list-backups":
        print(json.dumps(list_backups(), indent=2))
        return 0
    if args.cmd == "verify":
        res = verify_backup(args.backup_id)
        print(json.dumps(res, indent=2))
        return 0 if res["valid"] else 1
    if args.cmd == "restore":
        if not args.confirm:
            print("ERROR: Pass --confirm to authorize database/document restoration.", file=sys.stderr)
            return 2
        print(json.dumps(restore_backup(args.backup_id, confirm=True, settings=cfg), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

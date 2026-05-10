"""ledger-writer: tail Lobster Trap audit JSONL, normalize into the SQLite ledger.

Stdlib only. Survives:
  - audit log not yet existing (Lobster Trap may not have started)
  - malformed JSON lines (logs and continues)
  - unknown event shapes (normalize() degrades gracefully)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

# Allow `python ledger_writer.py` from inside ledger-writer/ AND `python ledger-writer/ledger_writer.py`
sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize import normalize  # noqa: E402

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format=LOG_FORMAT)
log = logging.getLogger("ledger_writer")

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
POLL_INTERVAL = 0.5


def init_db(conn: sqlite3.Connection) -> None:
    """Apply schema.sql once. Idempotent: skip if 'verdict' table already exists."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='verdict'"
    )
    if cur.fetchone():
        log.info("schema already present; skipping init")
        return
    if not SCHEMA_FILE.exists():
        raise RuntimeError(f"schema file not found: {SCHEMA_FILE}")
    log.info("initializing schema from %s", SCHEMA_FILE)
    conn.executescript(SCHEMA_FILE.read_text())
    conn.commit()


def insert_rows(conn: sqlite3.Connection, rows: list[tuple[str, dict]]) -> None:
    for table, row in rows:
        if not row:
            continue
        cols = ",".join(row.keys())
        placeholders = ",".join(["?"] * len(row))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        conn.execute(sql, list(row.values()))


def open_audit_log(path: str):
    """Open audit log for tailing; retry until it exists. Returns file handle at EOF."""
    while True:
        try:
            f = open(path, "r")
            f.seek(0, 2)  # tail from end
            log.info("tailing audit log: %s", path)
            return f
        except FileNotFoundError:
            log.info("audit log %s not present yet; waiting...", path)
            time.sleep(2.0)


def process_line(conn: sqlite3.Connection, line: str) -> None:
    line = line.strip()
    if not line:
        return
    try:
        event = json.loads(line)
    except json.JSONDecodeError as e:
        log.error("malformed JSON, skipping line: %s", e)
        return
    try:
        rows = normalize(event)
    except Exception as e:  # normalize is defensive but never crash the loop
        log.exception("normalize raised: %s", e)
        return
    try:
        insert_rows(conn, rows)
        conn.commit()
    except sqlite3.Error as e:
        log.error("sqlite insert failed: %s", e)
        try:
            conn.rollback()
        except sqlite3.Error:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tail Lobster Trap audit log into SQLite ledger.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Open DB, init schema, exit 0 without tailing the audit log.",
    )
    args = parser.parse_args(argv)

    db_path = os.environ.get("LEDGER_PATH")
    log_path = os.environ.get("LOBSTERTRAP_AUDIT_LOG")

    if not db_path:
        log.error("LEDGER_PATH env var required")
        return 2
    if not args.dry_run and not log_path:
        log.error("LOBSTERTRAP_AUDIT_LOG env var required (unless --dry-run)")
        return 2

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    init_db(conn)

    if args.dry_run:
        log.info("dry-run complete; ledger initialized at %s", db_path)
        conn.close()
        return 0

    f = open_audit_log(log_path)
    try:
        while True:
            line = f.readline()
            if not line:
                time.sleep(POLL_INTERVAL)
                continue
            process_line(conn, line)
    except KeyboardInterrupt:
        log.info("shutdown requested")
        return 0
    finally:
        try:
            f.close()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    sys.exit(main())

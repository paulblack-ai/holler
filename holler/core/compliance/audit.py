"""AuditLog — immutable compliance audit trail.

Primary record: append-only JSONL files, rotated by date (compliance-YYYY-MM-DD.jsonl).
Derived index: SQLite with call_uuid, destination, and timestamp indexes for queries.

Design per D-20, D-21, D-22:
- Every compliance check produces an audit entry
- JSONL is write-once (OS-level append mode)
- SQLite is derived — queryable for compliance reporting
- No UPDATE or DELETE operations in the write path
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite


class AuditLog:
    """Compliance audit log with JSONL primary record and SQLite queryable index.

    JSONL files are append-only and rotated by date. The SQLite index is
    a derived, queryable view of the same data — never the source of truth.
    """

    def __init__(self, log_dir: str, db_path: str) -> None:
        self._log_dir = Path(log_dir)
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Open persistent connection, enable WAL mode, create schema and indexes.

        Idempotent — safe to call multiple times.
        """
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                logged_at    TEXT NOT NULL,
                call_uuid    TEXT,
                session_uuid TEXT,
                check_type   TEXT NOT NULL,
                destination  TEXT,
                result       TEXT NOT NULL CHECK(result IN ('allow', 'deny')),
                reason       TEXT,
                did          TEXT,
                log_file     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_call_uuid ON audit_log(call_uuid);
            CREATE INDEX IF NOT EXISTS idx_audit_destination ON audit_log(destination);
            CREATE INDEX IF NOT EXISTS idx_audit_logged_at ON audit_log(logged_at);
        """)
        await self._db.commit()

    def _today_log_path(self) -> Path:
        """Return path for today's JSONL file: {log_dir}/compliance-YYYY-MM-DD.jsonl."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"compliance-{today}.jsonl"

    async def write(self, entry: dict) -> None:
        """Write a compliance check entry to both JSONL file and SQLite index.

        The JSONL write is the primary immutable record. SQLite is derived.
        No UPDATE or DELETE operations are performed — write-once semantics.
        """
        now = datetime.now(timezone.utc).isoformat()
        entry = dict(entry)  # copy to avoid mutating caller's dict
        entry["logged_at"] = now

        # 1. Append one JSON line to today's JSONL file (primary record)
        log_path = self._today_log_path()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # 2. INSERT row into SQLite audit_log (derived queryable index)
        await self._db.execute(
            """
            INSERT INTO audit_log
                (logged_at, call_uuid, session_uuid, check_type, destination,
                 result, reason, did, log_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                entry.get("call_uuid"),
                entry.get("session_uuid"),
                entry.get("check_type", ""),
                entry.get("destination"),
                entry.get("result", "deny"),
                entry.get("reason"),
                entry.get("did"),
                str(log_path),
            ),
        )
        await self._db.commit()

    async def query_by_call_uuid(self, call_uuid: str) -> List[Dict]:
        """Return all audit entries for a given call UUID, ordered by logged_at."""
        async with self._db.execute(
            "SELECT * FROM audit_log WHERE call_uuid = ? ORDER BY logged_at",
            (call_uuid,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def close(self) -> None:
        """Close the aiosqlite connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

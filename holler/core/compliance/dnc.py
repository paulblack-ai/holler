"""DNCList — SQLite-backed Do Not Call list for compliance checking.

Operator-managed DNC list. No FTC API integration — operator imports via
this interface (D-12). Uses INSERT OR IGNORE for idempotent adds.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite


class DNCList:
    """Fast SQLite-backed DNC lookup with operator-managed number list.

    Numbers are stored as E.164 strings. Lookups are O(1) via PRIMARY KEY index.
    Bulk import uses executemany with INSERT OR IGNORE for idempotent operation.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Open persistent connection, enable WAL mode, create schema.

        Idempotent — safe to call multiple times.
        """
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dnc (
                phone_number TEXT PRIMARY KEY,
                added_at     TEXT NOT NULL,
                source       TEXT NOT NULL DEFAULT 'operator'
            )
        """)
        await self._db.commit()

    async def is_on_dnc(self, phone_number: str) -> bool:
        """Return True if the phone number is on the DNC list."""
        async with self._db.execute(
            "SELECT 1 FROM dnc WHERE phone_number = ?",
            (phone_number,),
        ) as cursor:
            row = await cursor.fetchone()
        return row is not None

    async def add_number(self, phone_number: str, source: str = "operator") -> None:
        """Add a number to the DNC list. Idempotent — no error if already present."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT OR IGNORE INTO dnc (phone_number, added_at, source) VALUES (?, ?, ?)",
            (phone_number, now, source),
        )
        await self._db.commit()

    async def import_numbers(
        self, numbers: List[str], source: str = "operator"
    ) -> int:
        """Bulk insert E.164 numbers. Uses INSERT OR IGNORE for idempotent operation.

        Returns count of newly inserted rows (existing rows are skipped).
        """
        now = datetime.now(timezone.utc).isoformat()
        rows = [(num, now, source) for num in numbers]
        cursor = await self._db.executemany(
            "INSERT OR IGNORE INTO dnc (phone_number, added_at, source) VALUES (?, ?, ?)",
            rows,
        )
        await self._db.commit()
        return cursor.rowcount

    async def count(self) -> int:
        """Return total number of DNC entries."""
        async with self._db.execute("SELECT COUNT(*) FROM dnc") as cursor:
            row = await cursor.fetchone()
        return row[0]

    async def close(self) -> None:
        """Close the aiosqlite connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

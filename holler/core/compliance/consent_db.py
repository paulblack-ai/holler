"""ConsentDB — append-only SQLite-backed consent and opt-out records.

Design: Consent rows are NEVER updated or deleted. Opt-outs are new INSERT rows
with revoked_at populated. This is legally required per D-14 (append-only
consent records). Latest row for a phone number determines current consent state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite


class ConsentDB:
    """Append-only consent database backed by aiosqlite with WAL mode.

    Each consent grant or opt-out is a new row. The most recent row
    for a phone number determines current consent status: row with
    revoked_at IS NULL means consented; row with revoked_at set means opted out.
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
            CREATE TABLE IF NOT EXISTS consent (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT NOT NULL,
                consent_type TEXT NOT NULL CHECK(consent_type IN ('express', 'written')),
                granted_at   TEXT NOT NULL,
                revoked_at   TEXT,
                source       TEXT NOT NULL CHECK(source IN ('api', 'call', 'sms', 'dtmf')),
                call_uuid    TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            )
        """)
        await self._db.commit()

    async def record_consent(
        self,
        phone_number: str,
        consent_type: str,
        source: str = "api",
        call_uuid: Optional[str] = None,
    ) -> None:
        """INSERT a new consent grant row. Never updates existing rows."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO consent (phone_number, consent_type, granted_at, revoked_at, source, call_uuid)
            VALUES (?, ?, ?, NULL, ?, ?)
            """,
            (phone_number, consent_type, now, source, call_uuid),
        )
        await self._db.commit()

    async def record_optout(
        self,
        phone_number: str,
        source: str = "dtmf",
        call_uuid: Optional[str] = None,
    ) -> None:
        """INSERT a new opt-out row with revoked_at set. Never updates existing rows."""
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            """
            INSERT INTO consent (phone_number, consent_type, granted_at, revoked_at, source, call_uuid)
            VALUES (?, 'express', ?, ?, ?, ?)
            """,
            (phone_number, now, now, source, call_uuid),
        )
        await self._db.commit()

    async def has_consent(self, phone_number: str) -> bool:
        """Return True if the most recent consent record has no revocation.

        Returns False if no record exists or the latest row has revoked_at set.
        """
        async with self._db.execute(
            """
            SELECT revoked_at FROM consent
            WHERE phone_number = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (phone_number,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return False
        return row[0] is None

    async def close(self) -> None:
        """Close the aiosqlite connection."""
        if self._db is not None:
            await self._db.close()
            self._db = None

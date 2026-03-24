"""Tests for ConsentDB — append-only consent and opt-out records.

Tests cover:
- record_consent() inserts a row; has_consent() returns True
- record_optout() inserts a row with revoked_at set; has_consent() returns False
- has_consent() returns False for unknown numbers
- Multiple grants and revocations — latest state wins
- record_consent() after opt-out re-establishes consent
- Rows are never updated — count increases monotonically
- initialize() creates schema (idempotent)
"""
import asyncio
import pytest

from holler.core.compliance.consent_db import ConsentDB


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "consent.db")
    db = ConsentDB(db_path=path)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.initialize())
    yield db
    loop.run_until_complete(db.close())


def test_record_consent_and_has_consent(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    result = loop.run_until_complete(db.has_consent("+14155551234"))
    assert result is True


def test_record_optout_clears_consent(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    loop.run_until_complete(
        db.record_optout("+14155551234", source="dtmf", call_uuid="uuid-1")
    )
    result = loop.run_until_complete(db.has_consent("+14155551234"))
    assert result is False


def test_has_consent_returns_false_for_unknown(db):
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(db.has_consent("+19995550000"))
    assert result is False


def test_multiple_grants_and_revocations(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    loop.run_until_complete(db.record_optout("+14155551234", source="dtmf"))
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="sms"))
    loop.run_until_complete(db.record_optout("+14155551234", source="call"))
    result = loop.run_until_complete(db.has_consent("+14155551234"))
    assert result is False


def test_reconsent_after_optout(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    loop.run_until_complete(db.record_optout("+14155551234", source="dtmf"))
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    result = loop.run_until_complete(db.has_consent("+14155551234"))
    assert result is True


def test_rows_increase_monotonically_append_only(db):
    """Consent rows are never updated — count increases with each operation."""
    loop = asyncio.get_event_loop()

    async def count_rows():
        async with db._db.execute("SELECT COUNT(*) FROM consent") as cursor:
            row = await cursor.fetchone()
            return row[0]

    assert loop.run_until_complete(count_rows()) == 0
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="api"))
    assert loop.run_until_complete(count_rows()) == 1
    loop.run_until_complete(db.record_optout("+14155551234", source="dtmf"))
    assert loop.run_until_complete(count_rows()) == 2
    loop.run_until_complete(db.record_consent("+14155551234", "express", source="sms"))
    assert loop.run_until_complete(count_rows()) == 3


def test_initialize_is_idempotent(tmp_path):
    """initialize() can be called multiple times without error."""
    loop = asyncio.get_event_loop()
    path = str(tmp_path / "consent2.db")
    db = ConsentDB(db_path=path)

    async def run():
        await db.initialize()
        await db.initialize()  # second call — must not fail
        await db.close()

    loop.run_until_complete(run())

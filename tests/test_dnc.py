"""Tests for DNCList — SQLite-backed Do Not Call list.

Tests cover:
- is_on_dnc() returns False when list is empty
- After add_number(), is_on_dnc() returns True
- is_on_dnc() returns False for numbers not on list
- import_numbers() bulk-loads numbers; is_on_dnc() returns True for each
- add_number() is idempotent (adding same number twice doesn't error)
- count() returns number of DNC entries
"""
import asyncio
import pytest

from holler.core.compliance.dnc import DNCList


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "dnc.db")
    dnc = DNCList(db_path=path)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(dnc.initialize())
    yield dnc
    loop.run_until_complete(dnc.close())


def test_empty_list_is_not_on_dnc(db):
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(db.is_on_dnc("+14155551234"))
    assert result is False


def test_add_number_and_is_on_dnc(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.add_number("+14155551234"))
    result = loop.run_until_complete(db.is_on_dnc("+14155551234"))
    assert result is True


def test_is_on_dnc_false_for_unlisted(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.add_number("+14155551234"))
    result = loop.run_until_complete(db.is_on_dnc("+14155559999"))
    assert result is False


def test_import_numbers_bulk(db):
    loop = asyncio.get_event_loop()
    numbers = ["+14155551001", "+14155551002", "+14155551003"]
    count = loop.run_until_complete(db.import_numbers(numbers))
    assert count == 3
    for num in numbers:
        assert loop.run_until_complete(db.is_on_dnc(num)) is True


def test_add_number_is_idempotent(db):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.add_number("+14155551234"))
    # Adding same number again must not raise
    loop.run_until_complete(db.add_number("+14155551234"))
    # Count should still be 1
    assert loop.run_until_complete(db.count()) == 1


def test_count_returns_entry_count(db):
    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(db.count()) == 0
    loop.run_until_complete(db.add_number("+14155551001"))
    loop.run_until_complete(db.add_number("+14155551002"))
    assert loop.run_until_complete(db.count()) == 2


def test_import_numbers_idempotent(db):
    """import_numbers with overlapping numbers should not raise."""
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db.import_numbers(["+14155551234", "+14155551235"]))
    # Re-importing with same numbers
    loop.run_until_complete(db.import_numbers(["+14155551234", "+14155551236"]))
    # +14155551234 exists, +14155551235 exists, +14155551236 new
    assert loop.run_until_complete(db.count()) == 3

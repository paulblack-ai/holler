"""Tests for AuditLog — JSONL primary record + SQLite index.

Tests cover:
- write() creates JSONL file named compliance-YYYY-MM-DD.jsonl
- write() appends valid JSON line (parseable with json.loads)
- write() inserts a row into SQLite audit_log table
- Each write() adds exactly one line to JSONL and one row to SQLite
- JSONL entries include logged_at, call_uuid, check_type, destination, result, reason, did
- Multiple writes to same day append to same file
- query_by_call_uuid() returns all audit entries for a given UUID from SQLite
"""
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from holler.core.compliance.audit import AuditLog


@pytest.fixture
def audit(tmp_path):
    log_dir = str(tmp_path / "logs")
    db_path = str(tmp_path / "audit.db")
    al = AuditLog(log_dir=log_dir, db_path=db_path)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(al.initialize())
    yield al
    loop.run_until_complete(al.close())


def _sample_entry(call_uuid="call-uuid-1"):
    return {
        "call_uuid": call_uuid,
        "check_type": "tcpa",
        "destination": "+14155551234",
        "result": "allow",
        "reason": "consent verified",
        "did": "+14155559001",
    }


def test_write_creates_jsonl_file(audit, tmp_path):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry()))

    log_dir = Path(tmp_path / "logs")
    files = list(log_dir.glob("compliance-*.jsonl"))
    assert len(files) == 1


def test_jsonl_filename_matches_date_pattern(audit, tmp_path):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry()))

    log_dir = Path(tmp_path / "logs")
    files = list(log_dir.glob("compliance-*.jsonl"))
    assert len(files) == 1
    filename = files[0].name
    # Must match compliance-YYYY-MM-DD.jsonl
    assert re.match(r"compliance-\d{4}-\d{2}-\d{2}\.jsonl", filename), f"Bad filename: {filename}"


def test_jsonl_line_is_valid_json(audit, tmp_path):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry()))

    log_dir = Path(tmp_path / "logs")
    jsonl_file = list(log_dir.glob("compliance-*.jsonl"))[0]
    lines = jsonl_file.read_text().strip().split("\n")
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)


def test_jsonl_entry_contains_required_fields(audit, tmp_path):
    loop = asyncio.get_event_loop()
    entry = _sample_entry("call-uuid-fields")
    loop.run_until_complete(audit.write(entry))

    log_dir = Path(tmp_path / "logs")
    jsonl_file = list(log_dir.glob("compliance-*.jsonl"))[0]
    parsed = json.loads(jsonl_file.read_text().strip())

    for field in ["logged_at", "call_uuid", "check_type", "destination", "result", "reason", "did"]:
        assert field in parsed, f"Missing field: {field}"


def test_write_inserts_sqlite_row(audit):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry("call-uuid-sqlite")))

    async def count():
        async with audit._db.execute("SELECT COUNT(*) FROM audit_log") as cursor:
            row = await cursor.fetchone()
            return row[0]

    count_val = loop.run_until_complete(count())
    assert count_val == 1


def test_each_write_adds_one_line_and_one_row(audit, tmp_path):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry("uuid-a")))
    loop.run_until_complete(audit.write(_sample_entry("uuid-b")))
    loop.run_until_complete(audit.write(_sample_entry("uuid-c")))

    log_dir = Path(tmp_path / "logs")
    jsonl_file = list(log_dir.glob("compliance-*.jsonl"))[0]
    lines = [l for l in jsonl_file.read_text().strip().split("\n") if l]
    assert len(lines) == 3

    async def count():
        async with audit._db.execute("SELECT COUNT(*) FROM audit_log") as cursor:
            row = await cursor.fetchone()
            return row[0]

    assert loop.run_until_complete(count()) == 3


def test_multiple_writes_append_to_same_file(audit, tmp_path):
    """Multiple writes on same day append to the same JSONL file."""
    loop = asyncio.get_event_loop()
    for i in range(5):
        loop.run_until_complete(audit.write(_sample_entry(f"uuid-{i}")))

    log_dir = Path(tmp_path / "logs")
    files = list(log_dir.glob("compliance-*.jsonl"))
    assert len(files) == 1  # Only one file for today


def test_query_by_call_uuid(audit):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(audit.write(_sample_entry("target-uuid")))
    loop.run_until_complete(audit.write(_sample_entry("other-uuid")))
    loop.run_until_complete(audit.write(_sample_entry("target-uuid")))  # second for same UUID

    results = loop.run_until_complete(audit.query_by_call_uuid("target-uuid"))
    assert len(results) == 2
    for row in results:
        assert row["call_uuid"] == "target-uuid"

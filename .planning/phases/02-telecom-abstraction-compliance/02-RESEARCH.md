# Phase 2: Telecom Abstraction + Compliance - Research

**Researched:** 2026-03-24
**Domain:** Redis number pooling, telecom session state, TCPA/DNC compliance, FreeSWITCH recording, async SQLite audit logging
**Confidence:** HIGH — decisions are pre-locked in CONTEXT.md; research validates implementation approaches against existing code and official documentation

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Number pool management**
- D-01: DID pool stored in Redis SET. Checkout via atomic `SPOP`, release via `SADD`. Redis already runs in Docker Compose from Phase 1.
- D-02: Pool initialized on startup from a config-defined list of DIDs (environment variable or config file). No carrier provisioning API — operator manages DIDs with their trunk provider.
- D-03: No call can originate without a checked-out DID. The originate path must acquire a DID before calling `esl.originate()`. If pool is empty, call fails with a clear error.

**Session state architecture**
- D-04: Telecom session state stored in Redis hash per session. Keys include: session_uuid, call_uuid, did, destination, compliance_result, consent_status, recording_path, timestamps. TTL-based cleanup on session end.
- D-05: New `TelecomSession` class wraps Phase 1's `VoiceSession`. TelecomSession adds DID allocation, compliance state, recording reference, and jurisdiction context. VoiceSession remains voice-pipeline-only. Composition, not inheritance.
- D-06: Session state is the single source of truth for call lifecycle. All components (compliance gateway, recording, audit log) read/write through the session object.

**Compliance gateway architecture**
- D-07: Compliance gateway is a pre-originate gate in the ESL call control layer. Runs BEFORE `esl.originate()` is issued. No code path bypasses the gateway.
- D-08: Country module plugin interface: each module implements `check_outbound(destination, session) -> ComplianceResult` (allow/deny with reason and audit fields). Jurisdiction router calls the correct module based on E.164 prefix.
- D-09: Jurisdiction router maps E.164 country code prefix to the correct country module. If no module exists for a destination, the call is denied by default (fail-closed).
- D-10: Country module template (`countries/_template/`) scaffolds a new jurisdiction with the plugin interface contract, example checks, and documentation.

**US compliance module**
- D-11: US module enforces TCPA: verifies prior consent record exists, checks caller identification requirement, enforces time-of-day restrictions (8am-9pm in recipient's local time zone, derived from area code).
- D-12: DNC check runs against a local DNC list loaded into SQLite. The list is operator-managed (import from FTC DNC registry or custom). Check runs before every outbound call to a US number.
- D-13: Time-of-day check uses area code to timezone mapping (NANPA data). If destination timezone cannot be determined, the call is denied (fail-closed).

**Consent and opt-out state machine**
- D-14: Consent records stored in SQLite (append-only). Schema: phone_number, consent_type (express/written), granted_at, revoked_at, source (api/call/sms), call_uuid. Append-only — revocations are new rows, not updates.
- D-15: Opt-out capture via two channels: DTMF detection in FreeSWITCH (configurable key, default `9`) and keyword detection via live STT transcript (configurable keywords: "stop", "remove me", "do not call"). Both channels write to consent DB immediately.
- D-16: Once opt-out is recorded, all subsequent calls to that number are blocked by the compliance gateway. The opt-out is permanent until explicitly re-consented via API.

**Call recording and transcript**
- D-17: Call recording via FreeSWITCH native `uuid_record` ESL command. Recording starts when call connects, stops on hangup. Output format: WAV (16-bit PCM, 8kHz). Files stored in a configurable directory (default: `./recordings/`).
- D-18: Post-call transcript generated from the WAV recording using faster-whisper (same engine as live STT). Runs as a background task after call ends — does not block the call flow. Transcript stored as JSON alongside the WAV file.
- D-19: Recording and transcript paths stored in the telecom session and audit log for retrieval.

**Audit log**
- D-20: Every compliance check produces an audit log entry: timestamp, call_uuid, session_uuid, check_type (tcpa/dnc/tod/consent), destination, result (allow/deny), reason, DID used, operator context.
- D-21: Audit log written as append-only JSONL file (one JSON object per line). Additionally indexed in SQLite for queryable compliance reporting. JSONL is the primary immutable record; SQLite is a derived index.
- D-22: Audit log is the primary legal defense asset. It must be write-once (no updates, no deletes). File rotation by date (one file per day).

### Claude's Discretion
- Redis key naming conventions and TTL values
- SQLite schema details beyond the specified fields
- Exact FreeSWITCH `uuid_record` parameters and file naming
- Area code to timezone mapping data source and update mechanism
- Background task runner for post-call transcription
- Error handling for compliance check failures (network, DB)
- Logging format for compliance events (beyond audit log)

### Deferred Ideas (OUT OF SCOPE)
- STIR/SHAKEN A-level attestation (XCOMP-02) — requires STI-PA certificate registration, v2
- State-level US compliance overlays (California SB 1001, Florida written consent) — v2
- UK country module (XCOMP-01) — v2, community-contributed
- Webhook notifications for compliance events (MON-03) — Phase 3 or v2
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CALL-04 | Call recording captures audio and stores as retrievable WAV file | FreeSWITCH `uuid_record` ESL command + `record_sample_rate` channel variable; WAV 8kHz default |
| CALL-05 | Post-call transcript is generated and persisted alongside recording | faster-whisper `transcribe()` on WAV file; asyncio background task via `asyncio.create_task()` |
| TEL-01 | Number pool manager checks out a DID per session and releases it on call end | Redis `redis.asyncio.Redis.spop()` + `sadd()` — atomic, no additional locking needed for single-member operations |
| TEL-02 | Session state tracks conversation context, turn history, and tool-call state for the call lifetime | Redis HSET/HGETALL with TTL; `TelecomSession` wrapping `VoiceSession` via composition |
| TEL-03 | Jurisdiction router maps E.164 destination prefix to the correct country compliance module | E.164 prefix dict lookup (`+1` → US module); fail-closed default |
| COMP-01 | Compliance gateway is mandatory in the outbound call path — no bypass route exists | Wrap `FreeSwitchESL.originate()` inside `ComplianceGateway.check()` — structural enforcement, not optional |
| COMP-02 | US module enforces TCPA: prior consent verification, caller identification, time-of-day (8am-9pm local) | Area code → timezone static data dict (NANPA); `zoneinfo` for timezone math; consent SQLite query |
| COMP-03 | US module performs DNC list check before call connects | SQLite DNC table with operator-imported data; synchronous aiosqlite query in compliance check path |
| COMP-04 | Consent/opt-out state machine captures and enforces opt-out requests (DTMF or spoken) during call | FreeSWITCH DTMF event (`DTMF` event type, `DTMF-Digit` header); STT keyword match in pipeline |
| COMP-05 | Audit log records every compliance check with timestamp, result, and call context | JSONL file (daily rotation) + aiosqlite index; append-only design |
| COMP-06 | Country module plugin interface allows adding new jurisdictions without modifying core | Python ABC (abstract base class) `ComplianceModule` with `check_outbound()` abstract method |
| COMP-07 | Country module template (`_template/`) scaffolds a new jurisdiction | Template directory with annotated `gateway.py` implementing the ABC |
</phase_requirements>

---

## Summary

Phase 2 builds the telecom abstraction and compliance layer on top of Phase 1's voice pipeline. The work is architecturally well-defined by CONTEXT.md's locked decisions — research confirms implementation feasibility and identifies concrete answers for the discretionary areas.

The key structural insight: `FreeSwitchESL.originate()` in `esl.py` is the single chokepoint. All new logic (DID checkout, compliance gate, session creation) wraps that one method. Nothing else needs to change in the ESL layer — the gate is installed at the call site.

Redis `SPOP` is genuinely atomic — no additional locking is needed for single-member pop on a SET. This means the number pool is naturally race-condition-free for concurrent checkout. The `redis.asyncio` module (redis-py 7.x) is already in `pyproject.toml` and supports this natively.

For the area code → timezone mapping (discretionary), the right approach is a static Python dict bundled with the US module — no external library needed. The NANPA area code count (~380 active NPAs) is small enough for a lookup table that can be updated manually when new area codes are added.

**Primary recommendation:** Build the compliance gateway as a mandatory wrapper around `esl.originate()`, use Redis SPOP for atomic DID checkout, and use aiosqlite for both consent DB and audit log — all async-compatible with the established pattern.

---

## Standard Stack

### Core (Phase 2 additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| redis (asyncio) | 7.0.1 (latest) | Number pool SPOP/SADD, session HSET/HGETALL | Already in pyproject.toml (>=5.0); `redis.asyncio` submodule provides native asyncio support; atomic SPOP eliminates race conditions |
| aiosqlite | 0.22.1 | Consent DB + DNC list + audit log SQLite backend | Already installed in project env; asyncio bridge to stdlib sqlite3; single shared thread per connection prevents blocking |
| zoneinfo | stdlib (Python 3.9+) | Area code timezone math for TCPA time-of-day checks | Built into Python 3.11+ (project minimum); replaces pytz; IANA timezone database support |
| faster-whisper | 1.2.1 (already used) | Post-call transcript from WAV recording | Same engine as live STT; `WhisperModel.transcribe(file_path)` works directly on WAV files |

### Supporting (already in pyproject.toml)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| structlog | 23.0+ | Compliance event logging (beyond audit log) | Same pattern already used throughout Phase 1 — structured logging for compliance events |
| asyncio | stdlib | Background task for post-call transcription | `asyncio.create_task()` fires transcription without blocking call teardown |

### New Dependencies (must add to pyproject.toml)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| aiosqlite | >=0.22.0 | Async SQLite for consent DB, DNC list, audit index | Pure asyncio, no threads, MIT license, actively maintained |

**Installation:**
```bash
# Add to pyproject.toml dependencies
aiosqlite>=0.22.0

# No new system dependencies required
# Redis already running in Docker Compose
# Python stdlib covers zoneinfo (3.11+)
```

**Version verification (confirmed 2026-03-24):**
- `redis` (redis-py): 7.0.1 (confirmed via `pip3 index versions redis`)
- `aiosqlite`: 0.22.1 (confirmed via `pip show aiosqlite` — already installed)
- `redis.asyncio.Redis.spop()` available — type hint issue exists (mypy false positive) but method is functional

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
holler/
├── core/
│   ├── freeswitch/
│   │   ├── esl.py              # MODIFY: originate() now requires TelecomSession
│   │   └── events.py           # MODIFY: on_hangup fires recording stop + DID release
│   ├── telecom/                # NEW directory
│   │   ├── __init__.py
│   │   ├── pool.py             # NumberPool class — Redis SPOP/SADD
│   │   ├── session.py          # TelecomSession wrapping VoiceSession
│   │   └── router.py           # JurisdictionRouter — E.164 prefix → module
│   ├── compliance/             # NEW directory
│   │   ├── __init__.py
│   │   ├── gateway.py          # ComplianceModule ABC + ComplianceGateway orchestrator
│   │   ├── consent_db.py       # ConsentDB — aiosqlite CRUD for consent/opt-out
│   │   ├── dnc.py              # DNCList — SQLite-backed DNC check
│   │   └── audit.py            # AuditLog — JSONL + SQLite index writer
│   └── voice/
│       ├── pipeline.py         # UNCHANGED (VoiceSession stays as-is)
│       └── ...
├── countries/                  # NEW directory
│   ├── __init__.py
│   ├── us/
│   │   ├── __init__.py
│   │   ├── module.py           # USComplianceModule implementing ComplianceModule ABC
│   │   ├── tcpa.py             # TCPA checks (consent, time-of-day, caller ID)
│   │   ├── dnc_check.py        # DNC list check wrapper
│   │   └── timezones.py        # Area code → IANA timezone static dict
│   └── _template/
│       ├── __init__.py
│       └── module.py           # Annotated template implementing ComplianceModule ABC
├── config.py                   # MODIFY: add PoolConfig, ComplianceConfig, RecordingConfig
└── main.py                     # MODIFY: integrate gateway, pool, session manager
```

### Pattern 1: Atomic DID Checkout via Redis SPOP

**What:** `SPOP key` atomically removes and returns one random member from a Redis SET. This is the correct primitive for pool checkout — no separate lock, no race condition.

**When to use:** Every outbound call origination. Before `esl.originate()` is called.

**Example:**
```python
# Source: redis-py docs + redis.io/docs/latest/commands/spop/
import redis.asyncio as aioredis

class NumberPool:
    def __init__(self, redis_client: aioredis.Redis, pool_key: str = "holler:did_pool"):
        self._redis = redis_client
        self._pool_key = pool_key

    async def checkout(self) -> str:
        """Atomically claim one DID from the pool. Returns E.164 number."""
        did = await self._redis.spop(self._pool_key)
        if did is None:
            raise NumberPoolExhaustedError("DID pool is empty — cannot originate call")
        return did.decode() if isinstance(did, bytes) else did

    async def release(self, did: str) -> None:
        """Return a DID to the pool after call ends."""
        await self._redis.sadd(self._pool_key, did)

    async def initialize(self, dids: list[str]) -> None:
        """Populate pool from config on startup. Idempotent — SADD ignores duplicates."""
        if dids:
            await self._redis.sadd(self._pool_key, *dids)
```

**Note on mypy:** redis-py 7.x has a known type hint issue where `spop` on the asyncio client is typed as non-awaitable. The method IS awaitable at runtime — add `# type: ignore` or cast if static analysis flags it (redis-py issue #3886).

### Pattern 2: TelecomSession as Composition over VoiceSession

**What:** `TelecomSession` holds a `VoiceSession` reference (not inheritance). This preserves Phase 1's voice pipeline unchanged while adding the telecom layer on top.

**When to use:** `TelecomSession` is the object that flows through the entire Phase 2 call path. `VoiceSession` still lives in `pipeline.py` and is unchanged.

**Example:**
```python
from dataclasses import dataclass, field
from typing import Optional
from holler.core.voice.pipeline import VoiceSession

@dataclass
class TelecomSession:
    """Telecom context wrapper around VoiceSession. D-05."""
    session_uuid: str
    call_uuid: str
    did: str                          # Checked-out DID for this call
    destination: str
    jurisdiction: str                 # "us", "uk", etc. (from router)
    voice_session: VoiceSession       # Composition: voice pipeline state
    compliance_result: Optional[dict] = None
    consent_status: str = "unknown"   # "consented", "opted_out", "unknown"
    recording_path: Optional[str] = None
    transcript_path: Optional[str] = None
    started_at: Optional[float] = None
    answered_at: Optional[float] = None
    ended_at: Optional[float] = None
```

### Pattern 3: Compliance Gateway as Structural Chokepoint

**What:** The `ComplianceGateway` wraps `esl.originate()`. There is no exposed `originate()` callable that skips the gateway. The pattern is: one public entrypoint for outbound calls, and that entrypoint always runs the compliance check first.

**When to use:** This is the architectural invariant for COMP-01. The gateway is not optional middleware.

**Example:**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ComplianceResult:
    passed: bool
    reason: str
    check_type: str
    audit_fields: dict

class ComplianceModule(ABC):
    """Plugin interface for jurisdiction-specific compliance. D-08."""

    @abstractmethod
    async def check_outbound(
        self,
        destination: str,
        session: "TelecomSession",
    ) -> ComplianceResult:
        """Check all rules for this jurisdiction. Return allow or deny."""
        ...


class ComplianceGateway:
    """Mandatory gate. Wraps ESL originate. No call exits without clearing this. D-07."""

    def __init__(self, router: "JurisdictionRouter", audit_log: "AuditLog"):
        self._router = router
        self._audit = audit_log

    async def originate_checked(
        self,
        esl: "FreeSwitchESL",
        pool: "NumberPool",
        session: "TelecomSession",
    ) -> str:
        """Run compliance check, then originate. Returns call_uuid."""
        module = self._router.resolve(session.destination)
        result = await module.check_outbound(session.destination, session)
        await self._audit.write(session, result)

        if not result.passed:
            await pool.release(session.did)  # Return DID to pool on block
            raise ComplianceBlockError(result.reason)

        call_uuid = await esl.originate(session.destination, session.session_uuid)
        return call_uuid
```

### Pattern 4: FreeSWITCH uuid_record for WAV Recording

**What:** `uuid_record <uuid> start <path>` begins recording. `uuid_record <uuid> stop <path>` (or stop all) ends it. The `record_sample_rate` channel variable controls sample rate.

**When to use:** On `CHANNEL_ANSWER` ESL event, start recording. On `CHANNEL_HANGUP`, stop recording and fire background transcription task.

**Important caveat:** Official docs warn that `uuid_record` "seems to completely hijack control and doesn't generate FreeSWITCH events." This means RECORD_STOP events are not reliably fired. Use `uuid_record stop <path>` explicitly in the `CHANNEL_HANGUP` handler rather than relying on events.

**Example:**
```python
# Set record_sample_rate BEFORE calling uuid_record start
# The channel variable controls WAV sample rate (default 8kHz — matches PSTN)

async def start_recording(esl: FreeSwitchESL, call_uuid: str, path: str) -> None:
    # Set sample rate (8kHz = D-17 spec: 16-bit PCM 8kHz)
    await esl.send_raw(f"api uuid_setvar {call_uuid} record_sample_rate 8000")
    await esl.send_raw(f"api uuid_record {call_uuid} start {path}")

async def stop_recording(esl: FreeSwitchESL, call_uuid: str, path: str) -> None:
    await esl.send_raw(f"api uuid_record {call_uuid} stop {path}")
```

**File naming convention (discretionary recommendation):** `{recordings_dir}/{YYYY-MM-DD}/{call_uuid}.wav`
The date-based subdirectory makes rotation and archival straightforward.

### Pattern 5: Area Code to Timezone (Discretionary Implementation)

**What:** NANPA has ~380 active US area codes. Each maps to one primary timezone. A static Python dict is the right implementation — no library needed, no external call, no latency.

**When to use:** In the US compliance module's time-of-day check. Extract 3-digit NPA from E.164 destination.

**Data source:** NANPA official NPA reports (https://www.nanpa.com/reports/npa-reports) provide a downloadable CSV with timezone data. This ships as `holler/countries/us/timezones.py`.

**Example:**
```python
# holler/countries/us/timezones.py
# Generated from NANPA NPA reports. Update when new NPAs assigned.
# Format: NPA (str) -> IANA timezone name
NPA_TIMEZONES: dict[str, str] = {
    "201": "America/New_York",   # NJ
    "202": "America/New_York",   # DC
    "203": "America/New_York",   # CT
    "205": "America/Chicago",    # AL
    "206": "America/Los_Angeles", # WA
    # ... ~380 entries total
    "907": "America/Anchorage",  # AK
    "808": "Pacific/Honolulu",   # HI
}

def get_timezone_for_npa(e164_destination: str) -> str | None:
    """Extract NPA from E.164 number and return IANA timezone. +1NPAXXXXXXX"""
    if not e164_destination.startswith("+1") or len(e164_destination) < 5:
        return None
    npa = e164_destination[2:5]  # Extract area code digits
    return NPA_TIMEZONES.get(npa)
```

### Pattern 6: DTMF Opt-Out Detection via Genesis ESL

**What:** FreeSWITCH sends DTMF events to ESL subscribers when a caller presses a key. Event name is `DTMF`. Relevant fields: `Unique-ID` (call UUID), `DTMF-Digit` (the key pressed), `DTMF-Duration`.

**When to use:** Subscribe to DTMF events in the EventRouter. When DTMF-Digit matches the configured opt-out key (default `9`), write an opt-out record to the consent DB immediately.

**Example:**
```python
# In EventRouter setup (events.py modified or main.py)
# Genesis Consumer subscribes to DTMF events

@event_router.on("DTMF")
async def handle_dtmf(event: dict, call: ActiveCall | None):
    digit = event.get("DTMF-Digit", "")
    call_uuid = event.get("Unique-ID", "")
    if digit == config.compliance.opt_out_dtmf_key and call:
        await consent_db.record_optout(
            phone_number=call.destination,
            source="dtmf",
            call_uuid=call_uuid,
        )
        await esl.hangup(call_uuid, "NORMAL_CLEARING")
```

### Pattern 7: Post-Call Transcription as Background Task

**What:** After call ends and recording is saved, fire an asyncio background task that calls `WhisperModel.transcribe(wav_path)`. faster-whisper's `transcribe()` accepts a file path directly. The result is written as JSON alongside the WAV.

**Important:** faster-whisper's transcription is CPU/GPU bound and NOT natively async. Wrap in `asyncio.get_event_loop().run_in_executor(None, ...)` to avoid blocking the event loop.

**Example:**
```python
import asyncio
import json
from faster_whisper import WhisperModel

async def transcribe_recording(wav_path: str, model: WhisperModel) -> str:
    """Run post-call transcription in executor thread. Returns transcript JSON path."""
    loop = asyncio.get_event_loop()

    def _transcribe():
        segments, info = model.transcribe(wav_path, beam_size=5)
        return [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in segments
        ]

    segments = await loop.run_in_executor(None, _transcribe)
    json_path = wav_path.replace(".wav", ".transcript.json")
    with open(json_path, "w") as f:
        json.dump({"segments": segments, "language": info.language}, f)
    return json_path

# In CHANNEL_HANGUP handler — fire and forget
asyncio.create_task(transcribe_recording(session.recording_path, stt_model))
```

### Pattern 8: Append-Only Audit Log (JSONL + SQLite)

**What:** Two writes per compliance check: (1) append one JSON line to the daily JSONL file, (2) insert one row to SQLite for queryability. JSONL is the immutable record; SQLite is the search index.

**When to use:** Every compliance check, pass or fail. One log entry per check type (tcpa, dnc, tod, consent), not one entry per call.

**Example:**
```python
import json
import aiosqlite
from datetime import datetime, timezone
from pathlib import Path

class AuditLog:
    def __init__(self, log_dir: str, db_path: str):
        self._log_dir = Path(log_dir)
        self._db_path = db_path

    def _today_log_path(self) -> Path:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"compliance-{date_str}.jsonl"

    async def write(self, entry: dict) -> None:
        """Append to JSONL (primary) and insert to SQLite (index). D-21."""
        entry["logged_at"] = datetime.now(timezone.utc).isoformat()

        # JSONL write — synchronous (fast, OS-level append)
        log_path = self._today_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # SQLite index write — async
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO audit_log
                   (logged_at, call_uuid, session_uuid, check_type,
                    destination, result, reason, did, log_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry["logged_at"], entry.get("call_uuid"), entry.get("session_uuid"),
                 entry.get("check_type"), entry.get("destination"), entry.get("result"),
                 entry.get("reason"), entry.get("did"), str(self._today_log_path()))
            )
            await db.commit()
```

### Anti-Patterns to Avoid

- **Bypass mode for testing:** The compliance gateway must always run — in tests it returns a stub result, not a skip. A bypass path is equivalent to no compliance (see PITFALLS.md Pitfall 4).
- **Mutable consent records:** Consent rows are never updated. Revocations are new rows with `revoked_at` set. Query `WHERE revoked_at IS NULL` for active consent. Breaking this makes the consent trail legally indefensible.
- **Sharing the WhisperModel instance across transcription and live STT simultaneously:** faster-whisper models are not thread-safe for concurrent inference. The post-call transcription task must either use a separate model instance or queue with the live STT engine. Recommended: separate model instance initialized at startup, used only for post-call work.
- **Calling `esl.originate()` directly from outside the gateway:** After Phase 2, `esl.originate()` should only be called from within `ComplianceGateway.originate_checked()`. Consider making the direct method private or adding an assertion.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Atomic DID reservation under concurrency | Manual lock + SELECT + UPDATE sequence | Redis `SPOP` | SPOP is a single atomic O(1) command; no lock, no race, no transaction overhead |
| Async SQLite access | Thread pool + queue + sqlite3 | aiosqlite | Thread-per-connection model; replicates sqlite3 API exactly; already in project env |
| IANA timezone math | Custom UTC offset arithmetic | `zoneinfo` (stdlib) | Handles DST transitions, historical rules, all edge cases correctly |
| Post-call audio transcription | Custom Whisper wrapper | `WhisperModel.transcribe(file_path)` | faster-whisper accepts file paths natively; no custom audio loading needed |
| JSONL immutability enforcement | Custom write guard | OS-level file append + WAL mode off | File append is OS-atomic; no overwrite possible without explicit seek. Add SQLite `WITHOUT ROWID` or `CHECK` constraints for the index |

**Key insight:** The compliance domain is legally sensitive. Every "hand-rolled" component is a potential gap in the audit trail. Established libraries with known behavior are defensive choices, not just engineering preference.

---

## Common Pitfalls

### Pitfall 1: uuid_record Does Not Generate RECORD_STOP Events

**What goes wrong:** Developer relies on RECORD_STOP ESL event to trigger post-call processing. The event is not reliably generated by `uuid_record`. Post-call transcription never fires.

**Why it happens:** Official FreeSWITCH docs note that `uuid_record` "completely hijacks control" without typical event generation. This is a known limitation.

**How to avoid:** Do not use RECORD_STOP as a trigger. Instead, call `uuid_record stop` explicitly in the `CHANNEL_HANGUP` event handler, then immediately fire the transcription task. The stop command is synchronous — the file is closed and flushed before the hangup handler completes.

**Warning signs:** Transcription tasks never execute; WAV files are present but no JSON transcript.

### Pitfall 2: Redis SPOP Returns bytes, Not str

**What goes wrong:** `await redis.spop("holler:did_pool")` returns `b"+14155551234"` (bytes), not `"+14155551234"` (str). All downstream code that treats the DID as a string produces TypeErrors or silent bugs.

**Why it happens:** redis-py returns bytes by default for string operations. The `decode_responses=True` client parameter auto-decodes, but `redis.asyncio.Redis()` does not set this by default.

**How to avoid:** Either create the client with `decode_responses=True`, or explicitly decode in `NumberPool.checkout()`: `did.decode() if isinstance(did, bytes) else did`. Prefer `decode_responses=True` at client creation for consistency across all operations.

### Pitfall 3: aiosqlite Opens a New Connection Per Operation

**What goes wrong:** Calling `async with aiosqlite.connect(db_path) as db:` for every audit log entry opens, uses, and closes a connection each time. Under concurrent call volume (each call has multiple compliance checks), this is slower than necessary.

**Why it happens:** The aiosqlite pattern from examples uses context managers per operation. This is correct for correctness but not optimal for throughput.

**How to avoid:** Open a persistent connection at component initialization: `self._db = await aiosqlite.connect(db_path)`. Close it at shutdown. For WAL mode (enables concurrent reads): `await self._db.execute("PRAGMA journal_mode=WAL")`. This is safe for the append-only audit log pattern.

### Pitfall 4: Compliance Gateway Failure Mode — What Happens When SQLite Is Unavailable?

**What goes wrong:** If the consent DB or audit DB is unavailable (disk full, corruption, startup race), the compliance check throws an exception. An uncaught exception in the gateway could either (a) silently pass the call through or (b) crash the process.

**Why it happens:** Exception handling in the gateway is left as an exercise. A try/except that returns `ComplianceResult(passed=True, ...)` on exception is a backdoor.

**How to avoid:** Fail-closed: any exception in the compliance check must result in `ComplianceResult(passed=False, reason="compliance_check_error")`. Log the error. Block the call. This mirrors D-09 (unknown jurisdiction → denied by default). A compliance system that silently passes calls on error is legally equivalent to no compliance.

### Pitfall 5: Area Code Timezone Coverage Gaps

**What goes wrong:** A new US area code was assigned after the `timezones.py` dict was last updated. The destination timezone lookup returns `None`. The time-of-day check fails closed (D-13) — the call is blocked.

**Why it happens:** NANPA assigns new area codes occasionally. The static dict goes stale.

**How to avoid:** Document the NANPA update procedure in `countries/us/timezones.py`. Note the source URL and generation date. Fail-closed behavior (block on unknown NPA) is correct and safe — it prevents calls to new area codes until the operator updates the mapping. Log a `WARNING` with the unknown NPA so operators see it.

### Pitfall 6: Two WhisperModel Instances Compete for VRAM

**What goes wrong:** Live STT uses `STTEngine` (which holds a `WhisperModel`). Post-call transcription spawns tasks using `transcribe_recording()` with a second `WhisperModel`. Two instances compete for GPU VRAM. Under concurrent calls, VRAM is exhausted and one instance fails to load.

**Why it happens:** Post-call transcription naturally wants its own model to avoid contention with live STT. But two models on one GPU is often impossible.

**How to avoid:** For the initial implementation, run post-call transcription on `device="cpu"`. The post-call task is not latency-sensitive (not in the call path). A separate CPU-based WhisperModel for post-call transcription avoids all VRAM contention. Configure via `PostCallTranscriptionConfig(device="cpu", compute_type="int8")`.

### Pitfall 7: Redis Session Hash TTL Not Reset on Activity

**What goes wrong:** A session hash is created with a 1-hour TTL. The call goes longer. The hash expires mid-call. Subsequent reads return empty results.

**Why it happens:** TTL is set once at session creation, not refreshed on activity.

**How to avoid:** Use `EXPIRE` to refresh the TTL on each meaningful write to the session hash. Or set a generous TTL (e.g., 24h) and rely on explicit cleanup at hangup. Explicit cleanup (delete on CHANNEL_HANGUP) is preferred — it avoids orphaned sessions while ensuring long calls don't expire.

---

## Code Examples

### Redis Client Setup (asyncio mode with decode_responses)

```python
# Source: redis-py docs (redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
import redis.asyncio as aioredis

async def create_redis(url: str = "redis://localhost:6379") -> aioredis.Redis:
    return aioredis.from_url(url, decode_responses=True)

# In config — decode_responses=True ensures all returns are str, not bytes
```

### TelecomSession Redis Persistence

```python
# HSET fields map directly to TelecomSession dataclass fields
# TTL set to 24h; explicitly deleted on CHANNEL_HANGUP

async def save_session(redis: aioredis.Redis, session: TelecomSession) -> None:
    key = f"holler:session:{session.session_uuid}"
    await redis.hset(key, mapping={
        "call_uuid": session.call_uuid or "",
        "did": session.did,
        "destination": session.destination,
        "jurisdiction": session.jurisdiction,
        "compliance_result": session.compliance_result or "",
        "consent_status": session.consent_status,
        "recording_path": session.recording_path or "",
    })
    await redis.expire(key, 86400)  # 24h safety TTL

async def load_session(redis: aioredis.Redis, session_uuid: str) -> dict:
    key = f"holler:session:{session_uuid}"
    return await redis.hgetall(key)
```

### SQLite Schema for Consent DB

```sql
-- Source: D-14 spec + append-only design requirement
-- aiosqlite + WAL mode for concurrent reads

PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS consent (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number TEXT NOT NULL,
    consent_type TEXT NOT NULL CHECK(consent_type IN ('express', 'written')),
    granted_at   TEXT NOT NULL,  -- ISO 8601 UTC
    revoked_at   TEXT,           -- NULL = active consent; populated by opt-out row
    source       TEXT NOT NULL CHECK(source IN ('api', 'call', 'sms')),
    call_uuid    TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Active consent query
-- SELECT * FROM consent WHERE phone_number = ? AND revoked_at IS NULL ORDER BY granted_at DESC LIMIT 1

CREATE TABLE IF NOT EXISTS dnc (
    phone_number TEXT PRIMARY KEY,
    added_at     TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'operator'  -- 'ftc', 'operator', 'internal'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at   TEXT NOT NULL,
    call_uuid   TEXT,
    session_uuid TEXT,
    check_type  TEXT NOT NULL,  -- 'tcpa', 'dnc', 'tod', 'consent'
    destination TEXT,
    result      TEXT NOT NULL CHECK(result IN ('allow', 'deny')),
    reason      TEXT,
    did         TEXT,
    log_file    TEXT            -- path to JSONL file containing this entry
);

CREATE INDEX IF NOT EXISTS idx_audit_call_uuid ON audit_log(call_uuid);
CREATE INDEX IF NOT EXISTS idx_audit_destination ON audit_log(destination);
CREATE INDEX IF NOT EXISTS idx_audit_logged_at ON audit_log(logged_at);
```

### Jurisdiction Router

```python
# Source: D-08/D-09 spec; E.164 country code prefix lookup

class JurisdictionRouter:
    def __init__(self):
        self._modules: dict[str, ComplianceModule] = {}

    def register(self, prefix: str, module: ComplianceModule) -> None:
        self._modules[prefix] = module

    def resolve(self, destination: str) -> ComplianceModule:
        """Map E.164 destination to compliance module. Fail-closed on unknown. D-09."""
        for prefix, module in self._modules.items():
            if destination.startswith(prefix):
                return module
        raise NoComplianceModuleError(
            f"No compliance module for destination {destination[:4]}... — call denied"
        )
```

### US TCPA Time-of-Day Check

```python
# Source: TCPA 47 U.S.C. 227(b)(1)(A) — 8am-9pm recipient local time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from holler.countries.us.timezones import get_timezone_for_npa

def check_time_of_day(destination: str) -> tuple[bool, str]:
    """Return (passed, reason). Fail-closed on unknown NPA. D-11, D-13."""
    tz_name = get_timezone_for_npa(destination)
    if tz_name is None:
        return False, f"unknown_npa:{destination[2:5]}"

    now_local = datetime.now(ZoneInfo(tz_name))
    hour = now_local.hour
    if 8 <= hour < 21:  # 8am to 9pm (exclusive)
        return True, "within_tcpa_hours"
    return False, f"outside_tcpa_hours:{now_local.strftime('%H:%M %Z')}"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-call Postgres transaction for DID lock | Redis SPOP (atomic, in-memory) | Redis 1.0+ | Zero contention, sub-ms checkout |
| pytz for timezone math | zoneinfo (stdlib) | Python 3.9 | No third-party dep, correct DST handling |
| Compliance as optional middleware flag | Structural enforcement (gateway in call path) | TCPA precedent / architecture choice | Cannot be bypassed by misconfiguration |
| aioredis (separate package) | redis.asyncio (built into redis-py 4.2+) | redis-py 4.2 (2022) | One less dependency; same API |
| Separate Whisper model for each use | Shared model with executor for post-call | faster-whisper threading guidance | Avoids VRAM double-loading |

**Deprecated/outdated:**
- `aioredis`: Archived, functionality merged into `redis.asyncio` in redis-py 4.2. Do not add as a separate dependency.
- `pytz`: Still maintained but `zoneinfo` is the stdlib replacement for Python 3.9+. Use `zoneinfo` throughout.
- OpenAI `whisper` package for post-call transcription: 4x slower than faster-whisper, no advantage.

---

## Open Questions

1. **FTC DNC List Import Format**
   - What we know: FTC provides a public API (JSON) and CSV exports for reported call complaints. The "National DNC Registry" is separate from reported calls — actual registered numbers are only accessible to telemarketers via the FTC's Subscription Service (paid, no public bulk download).
   - What's unclear: For Phase 2, the DNC list is "operator-managed." This means the operator imports their own list. The question is: what format do we accept for import?
   - Recommendation: Accept CSV import with one E.164 number per line. Document that the FTC's official DNC subscription data is the operator's responsibility. Ship a `holler dnc import <file.csv>` CLI helper in Phase 3. For Phase 2, a simple `INSERT INTO dnc` from a CSV file is sufficient.

2. **Redis Key Prefix Namespacing**
   - What we know: Multiple Redis keys will exist — DID pool, session hashes, potentially future keys.
   - What's unclear: Convention not yet established.
   - Recommendation: Use `holler:{component}:{id}` pattern:
     - DID pool: `holler:did_pool` (single SET)
     - Sessions: `holler:session:{session_uuid}` (HASH)
     - No other keys needed in Phase 2

3. **uuid_record vs record_session for Recording**
   - What we know: `uuid_record` is the ESL API command. `record_session` is a dialplan application. D-17 specifies `uuid_record`. The official docs warn `uuid_record` doesn't generate RECORD_STOP events.
   - What's unclear: Whether `record_session` would work better here (it CAN be triggered via `uuid_execute_api`).
   - Recommendation: Stick with D-17's `uuid_record` as specified. Handle the missing RECORD_STOP by stopping explicitly in the CHANNEL_HANGUP handler (documented in Common Pitfalls #1 above). This is the correct ESL-based approach.

4. **Compliance Check Timeout**
   - What we know: Compliance checks are synchronous SQLite queries (fast, local). No network calls.
   - What's unclear: Should a timeout be enforced on the compliance check to prevent blocking the call path indefinitely?
   - Recommendation: Wrap the compliance check in `asyncio.wait_for(module.check_outbound(...), timeout=2.0)`. On timeout, fail-closed. 2 seconds is generous for local SQLite but prevents a hung DB from blocking the event loop.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Redis container (D-01) | Yes | 29.1.5 | — |
| Docker Compose | Full stack orchestration | Yes | v5.0.1 | — |
| Redis (via Docker) | Number pool, session state | Running in Docker Compose | redis:7-alpine | — |
| aiosqlite | Consent DB, DNC, audit log | Yes (pip installed) | 0.22.1 | — |
| Python 3.11+ | zoneinfo stdlib | Yes (project requires >=3.11) | See pyproject.toml | — |
| faster-whisper | Post-call transcription | Yes (in pyproject.toml) | 1.2.1 | — |
| redis-py (asyncio) | Redis client | In pyproject.toml (>=5.0); NOT installed in venv | 7.0.1 (latest) | — |

**Missing dependencies with no fallback:**
- None — all required dependencies are either installed or in Docker Compose.

**Missing dependencies with fallback:**
- `redis-py` not yet installed in project venv (no venv exists yet). Must be installed at Phase 2 start via `pip install -e ".[dev]"` or equivalent. Already declared in `pyproject.toml`.
- `aiosqlite` not in `pyproject.toml` yet — must be added to project dependencies.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 2 |
|-----------|-------------------|
| Python core (orchestration, agent interface) | All new code is Python async — no Go, no Rust for Phase 2 components |
| asyncio throughout | All new components must be `async def` compatible; no blocking calls in event loop |
| Config-from-environment pattern (`from_env()`) | `PoolConfig`, `ComplianceConfig`, `RecordingConfig` all use `HollerConfig.from_env()` extension pattern |
| Deferred initialization pattern | `NumberPool`, `ComplianceGateway`, `AuditLog` all initialized once at startup, not at import |
| Apache 2.0 license | All new dependencies must be Apache 2.0 or MIT compatible (redis-py: MIT, aiosqlite: MIT, zoneinfo: stdlib — all clear) |
| No vendor accounts | DNC list is operator-managed; no FTC API credentials required in the core |
| Python 3.9 compat note from STATE.md | Use `Optional[T]` not `T | None` in signatures — however `pyproject.toml` now requires >=3.11. Safe to use `T | None` but be consistent with existing Phase 1 code style which uses `Optional[T]` |
| `asyncio.get_event_loop().run_until_complete()` in tests | If pytest-asyncio not available, use this pattern in tests (see STATE.md Phase 1 note) |
| `websockets 15.x` handler pattern | Not directly relevant to Phase 2 — no new WebSocket servers |

---

## Sources

### Primary (HIGH confidence)
- redis-py PyPI — version 7.0.1 confirmed via `pip3 index versions redis`
- aiosqlite PyPI — version 0.22.1 confirmed via `pip show aiosqlite`
- FreeSWITCH mod_commands `uuid_record` — official docs: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Modules/mod_commands_1966741/
- FreeSWITCH `record_sample_rate` channel variable — official docs: https://developer.signalwire.com/freeswitch/Channel-Variables-Catalog/record_sample_rate_16353888/
- Python `zoneinfo` stdlib docs: https://docs.python.org/3/library/zoneinfo.html
- redis.io SPOP command: https://redis.io/docs/latest/commands/sadd/
- CONTEXT.md decisions D-01 through D-22 — locked, authoritative

### Secondary (MEDIUM confidence)
- redis-py asyncio examples — https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html
- aiosqlite documentation — https://aiosqlite.omnilib.dev/en/stable/
- FreeSWITCH DTMF documentation — https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Configuration/DTMF_9634268/
- FreeSWITCH record_session docs — https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Modules/mod-dptools/6587110/
- redis-py spop type hint issue — https://github.com/redis/redis-py/issues/3886 (confirms method IS awaitable despite type error)
- faster-whisper inconsistent async transcription — https://github.com/SYSTRAN/faster-whisper/issues/1207 (supports run_in_executor recommendation)
- NANPA NPA reports (area code data source) — https://www.nanpa.com/reports/npa-reports
- existing project research: `.planning/research/PITFALLS.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`

### Tertiary (LOW confidence)
- FTC DNC API format — https://www.ftc.gov/developer/api/v0/endpoints/do-not-call-dnc-reported-calls-data-api (noted that public DNC subscription data is not freely available in bulk)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — redis-py and aiosqlite versions confirmed from package index; all other tools are Phase 1 carry-forwards
- Architecture: HIGH — decisions locked in CONTEXT.md; patterns confirmed against existing esl.py/events.py/pipeline.py code
- Compliance logic: HIGH — TCPA requirements sourced from FCC and PITFALLS.md (previously verified against official sources)
- Pitfalls: HIGH — uuid_record event behavior confirmed against official docs; others from Phase 1 research carry-forward
- Area code timezone data: MEDIUM — NANPA as authoritative source confirmed, but full NPA-to-timezone dict must be generated from NANPA CSV

**Research date:** 2026-03-24
**Valid until:** 2026-09-24 (stable; Redis and SQLite APIs are very stable; TCPA rules change rarely at the federal level)

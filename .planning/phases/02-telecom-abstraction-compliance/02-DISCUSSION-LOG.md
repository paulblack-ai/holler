# Phase 2: Telecom Abstraction + Compliance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 02-telecom-abstraction-compliance
**Areas discussed:** Number pool management, Session state architecture, Compliance gateway architecture, Consent/DNC storage, Call recording mechanism, Audit log format
**Mode:** Auto (all recommended defaults selected)

---

## Number Pool Management

| Option | Description | Selected |
|--------|-------------|----------|
| Redis SET (SPOP/SADD) | Atomic checkout/release, sub-ms, already running | ✓ |
| PostgreSQL table | ACID, survives restart, but adds dependency | |
| In-memory Python set | Simplest, but lost on restart | |

**User's choice:** [auto] Redis SET — already running from Phase 1, atomic operations, natural fit
**Notes:** Pool initialized from config on startup. Empty pool = call denied.

---

## Session State Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Redis hash per session | Extends existing Redis, TTL cleanup, shared | ✓ |
| SQLite per session | Persistent, queryable, but slower | |
| In-memory dict | Fast but lost on restart | |

**User's choice:** [auto] Redis hash — consistent with Phase 1 infrastructure
**Notes:** TelecomSession wraps VoiceSession (composition). Session is single source of truth.

---

## Compliance Gateway Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-originate gate in ESL | Structurally non-bypassable, checks before FreeSWITCH call | ✓ |
| FreeSWITCH dialplan gate | In-switch check, but harder to implement complex logic | |
| Post-routing middleware | Easier to add but can be bypassed | |

**User's choice:** [auto] Pre-originate gate — only code path to PSTN, impossible to bypass
**Notes:** Plugin interface: `check_outbound(destination, session) -> ComplianceResult`. Fail-closed for unknown jurisdictions.

---

## Consent/DNC Storage

| Option | Description | Selected |
|--------|-------------|----------|
| SQLite append-only | No external deps, survives Redis restart, audit-friendly | ✓ |
| Redis with persistence | Fast but less audit-friendly | |
| PostgreSQL | Full ACID but adds dependency | |

**User's choice:** [auto] SQLite — append-only for legal defensibility, no external dependency
**Notes:** Opt-out via DTMF + STT keyword detection. Permanent until re-consented via API.

---

## Call Recording Mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| FreeSWITCH uuid_record | Native, no Python audio handling, WAV output | ✓ |
| Python-side recording | More control but adds latency/complexity | |
| Both (redundant) | Maximum safety but wasteful | |

**User's choice:** [auto] FreeSWITCH native recording — simplest, most reliable
**Notes:** Post-call transcript via faster-whisper as background task. Does not block call flow.

---

## Audit Log Format

| Option | Description | Selected |
|--------|-------------|----------|
| JSONL + SQLite index | Immutable JSONL primary, queryable SQLite secondary | ✓ |
| SQLite only | Queryable but mutable | |
| JSONL only | Immutable but not queryable | |

**User's choice:** [auto] JSONL + SQLite — best of both: immutability + queryability
**Notes:** Daily file rotation. Write-once (no updates, no deletes). Primary legal defense asset.

---

## Claude's Discretion

- Redis key naming and TTL values
- SQLite schema details
- FreeSWITCH uuid_record parameters
- Area code → timezone mapping data source
- Background task runner for transcription
- Error handling for compliance failures

## Deferred Ideas

- STIR/SHAKEN attestation — v2 (cert registration lead time)
- State-level US overlays — v2
- UK country module — v2 community contribution
- Webhook notifications — Phase 3 or v2

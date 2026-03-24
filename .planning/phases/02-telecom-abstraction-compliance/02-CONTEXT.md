# Phase 2: Telecom Abstraction + Compliance - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Calls become session-aware, number-pool-managed, jurisdiction-routed, and structurally blocked from reaching PSTN without passing a compliance gateway. Delivers: DID number pool (checkout/release), telecom session state, jurisdiction router, US compliance module (TCPA, DNC, time-of-day), consent/opt-out state machine, compliance audit log, call recording (WAV), and post-call transcript generation. Country module plugin interface with template scaffold.

</domain>

<decisions>
## Implementation Decisions

### Number pool management
- **D-01:** DID pool stored in Redis SET. Checkout via atomic `SPOP`, release via `SADD`. Redis already runs in Docker Compose from Phase 1.
- **D-02:** Pool initialized on startup from a config-defined list of DIDs (environment variable or config file). No carrier provisioning API — operator manages DIDs with their trunk provider.
- **D-03:** No call can originate without a checked-out DID. The originate path must acquire a DID before calling `esl.originate()`. If pool is empty, call fails with a clear error.

### Session state architecture
- **D-04:** Telecom session state stored in-memory as Python dataclass (dict keyed by call_uuid). Sufficient for single-process v1 deployment. Redis session persistence deferred to v2 when multi-process/replicated deployment is needed. Fields: session_uuid, call_uuid, did, destination, compliance_result, consent_status, recording_path, timestamps.
- **D-05:** New `TelecomSession` class wraps Phase 1's `VoiceSession`. TelecomSession adds DID allocation, compliance state, recording reference, and jurisdiction context. VoiceSession remains voice-pipeline-only (STT/TTS/LLM state). Composition, not inheritance.
- **D-06:** Session state is the single source of truth for call lifecycle. All components (compliance gateway, recording, audit log) read/write through the session object.

### Compliance gateway architecture
- **D-07:** Compliance gateway is a pre-originate gate in the ESL call control layer. The check runs BEFORE the FreeSWITCH originate command is issued. There is no code path that bypasses the gateway — it is structurally impossible to place an unchecked outbound call.
- **D-08:** Country module plugin interface: each module implements `check_outbound(destination, session) -> ComplianceResult` (allow/deny with reason and audit fields). The jurisdiction router calls the correct module based on E.164 prefix.
- **D-09:** Jurisdiction router maps E.164 country code prefix to the correct country module. If no module exists for a destination, the call is denied by default (fail-closed).
- **D-10:** Country module template (`countries/_template/`) scaffolds a new jurisdiction with the plugin interface contract, example checks, and documentation.

### US compliance module
- **D-11:** US module enforces TCPA: verifies prior consent record exists, checks caller identification requirement, enforces time-of-day restrictions (8am-9pm in recipient's local time zone, derived from area code).
- **D-12:** DNC (Do Not Call) check runs against a local DNC list loaded into SQLite. The list is operator-managed (import from FTC DNC registry or custom). Check runs before every outbound call to a US number.
- **D-13:** Time-of-day check uses area code to timezone mapping (NANPA data). If destination timezone cannot be determined, the call is denied (fail-closed).

### Consent and opt-out state machine
- **D-14:** Consent records stored in SQLite (append-only). Schema: phone_number, consent_type (express/written), granted_at, revoked_at, source (api/call/sms), call_uuid. Append-only — revocations are new rows, not updates.
- **D-15:** Opt-out capture via two channels: DTMF detection in FreeSWITCH (configurable key, default `9`) and keyword detection via live STT transcript (configurable keywords: "stop", "remove me", "do not call"). Both channels write to consent DB immediately.
- **D-16:** Once opt-out is recorded, all subsequent calls to that number are blocked by the compliance gateway. The opt-out is permanent until explicitly re-consented via API.

### Call recording and transcript
- **D-17:** Call recording via FreeSWITCH native `uuid_record` ESL command. Recording starts when call connects, stops on hangup. Output format: WAV (16-bit PCM, 8kHz). Files stored in a configurable directory (default: `./recordings/`).
- **D-18:** Post-call transcript generated from the WAV recording using faster-whisper (same engine as live STT). Runs as a background task after call ends — does not block the call flow. Transcript stored as JSON alongside the WAV file.
- **D-19:** Recording and transcript paths stored in the telecom session and audit log for retrieval.

### Audit log
- **D-20:** Every compliance check produces an audit log entry: timestamp, call_uuid, session_uuid, check_type (tcpa/dnc/tod/consent), destination, result (allow/deny), reason, DID used, operator context.
- **D-21:** Audit log written as append-only JSONL file (one JSON object per line). Additionally indexed in SQLite for queryable compliance reporting. JSONL is the primary immutable record; SQLite is a derived index.
- **D-22:** Audit log is the primary legal defense asset. It must be write-once (no updates, no deletes). File rotation by date (one file per day).

### Claude's Discretion
- Redis key naming conventions and TTL values
- SQLite schema details beyond the specified fields
- Exact FreeSWITCH `uuid_record` parameters and file naming
- Area code to timezone mapping data source and update mechanism
- Background task runner for post-call transcription
- Error handling for compliance check failures (network, DB)
- Logging format for compliance events (beyond audit log)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value, constraints, key decisions (compliance as mandatory gateway)
- `.planning/REQUIREMENTS.md` — CALL-04, CALL-05, TEL-01..03, COMP-01..07 requirement definitions

### Research
- `.planning/research/STACK.md` — Redis, SQLite, library versions
- `.planning/research/ARCHITECTURE.md` — Component boundaries, compliance gateway placement, data flow
- `.planning/research/PITFALLS.md` — TCPA pitfalls, STIR/SHAKEN cert lead time, DNC enforcement

### Phase 1 implementation (build on these)
- `holler/core/freeswitch/esl.py` — FreeSwitchESL client (originate, hangup) — compliance gate goes here
- `holler/core/freeswitch/events.py` — EventRouter, CallState, ActiveCall — session state extends this
- `holler/core/voice/pipeline.py` — VoiceSession — TelecomSession wraps this
- `holler/config.py` — HollerConfig — add compliance, recording, pool config
- `holler/main.py` — Main entry point — integrate compliance gateway into startup
- `docker/docker-compose.yml` — Redis already configured

### External concept documents
- `/Users/paul/paul/brains/docs/drafts/2026-03-24-agentic-telecom-concept-brief.html` — US compliance section (TCPA, STIR/SHAKEN, state overlays), jurisdiction router design

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FreeSwitchESL.originate()` in `esl.py` — compliance gate wraps this method
- `EventRouter` / `ActiveCall` in `events.py` — session lifecycle hooks for recording start/stop
- `VoiceSession` in `pipeline.py` — composition target for TelecomSession
- `STTEngine.transcribe_buffer()` in `stt.py` — reuse for post-call transcript generation
- `HollerConfig.from_env()` in `config.py` — extend with compliance/recording/pool config
- Redis already running in Docker Compose (`docker/docker-compose.yml`)

### Established Patterns
- Async throughout (asyncio) — all new components must be async-compatible
- Config-from-environment via dataclass `from_env()` pattern
- Deferred initialization (models loaded on first use, not import)
- Docker Compose for service orchestration

### Integration Points
- `esl.originate()` — compliance gateway wraps this call
- `events.on_answer` / `events.on_hangup` — recording lifecycle hooks
- `pipeline.create_session()` — TelecomSession creation point
- `config.HollerConfig` — add new config sections
- `main.py` — initialize compliance gateway, number pool, recording

</code_context>

<specifics>
## Specific Ideas

- From concept brief: "The system is architecturally incapable of placing a non-compliant call" — the compliance gateway must be in the ONLY code path to PSTN, not an optional middleware
- From concept brief: "The audit trail is the primary legal defense asset" — immutability of the audit log is non-negotiable
- From concept brief: jurisdiction router pattern — `+1 (US) → US Compliance Gateway`, `+44 (UK) → UK overlay`, unknown → denied by default
- Country module directory structure: `holler/countries/us/`, `holler/countries/uk/`, `holler/countries/_template/`

</specifics>

<deferred>
## Deferred Ideas

- STIR/SHAKEN A-level attestation — requires STI-PA certificate registration (bureaucratic lead time), v2 requirement (XCOMP-02)
- State-level US compliance overlays (California SB 1001, Florida written consent) — v2, after federal baseline works
- UK country module (Ofcom rules) — v2 requirement (XCOMP-01), community-contributed
- Webhook notifications for compliance events — Phase 3 or v2 (MON-03)

</deferred>

---

*Phase: 02-telecom-abstraction-compliance*
*Context gathered: 2026-03-24*

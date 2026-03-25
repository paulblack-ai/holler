---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: v1.0 milestone complete
stopped_at: Completed quick/260324-ubt-fix-holler-init-kokoro-onnx-model-downlo/260324-ubt-PLAN.md
last_updated: "2026-03-25T03:00:45.267Z"
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 16
  completed_plans: 16
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-24)

**Core value:** An AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation — no vendor accounts, no API keys, no human in the loop.
**Current focus:** Phase 05 — sms-inbound-stt-optout-wiring

## Current Position

Phase: 05
Plan: Not started

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01-freeswitch-voice-pipeline P01 | 2 | 3 tasks | 14 files |
| Phase 01-freeswitch-voice-pipeline P02 | 4 | 3 tasks | 11 files |
| Phase 01-freeswitch-voice-pipeline P03 | 3 | 2 tasks | 3 files |
| Phase 01-freeswitch-voice-pipeline P04 | 3min | 2 tasks | 4 files |
| Phase 01 P05 | 4 | 2 tasks | 6 files |
| Phase 02-telecom-abstraction-compliance P02 | 3 | 3 tasks | 7 files |
| Phase 02-telecom-abstraction-compliance P01 | 5min | 3 tasks | 10 files |
| Phase 02-telecom-abstraction-compliance P03 | 15min | 3 tasks | 6 files |
| Phase 02-telecom-abstraction-compliance P04 | 4 | 2 tasks | 6 files |
| Phase 02-telecom-abstraction-compliance P05 | 4min | 3 tasks | 6 files |
| Phase 03-sms-agent-interface-cli P02 | 3min | 1 tasks | 5 files |
| Phase 03-sms-agent-interface-cli P01 | 15min | 2 tasks | 6 files |
| Phase 03-sms-agent-interface-cli P03 | 5min | 2 tasks | 3 files |
| Phase 03-sms-agent-interface-cli P04 | 5min | 2 tasks | 6 files |
| Phase 04-cli-docker-onboarding-fixes P01 | 2m 19s | 2 tasks | 5 files |
| Phase 05-sms-inbound-stt-optout-wiring P01 | 9min | 1 tasks | 5 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- FreeSWITCH over Asterisk/Kamailio (pending confirmation)
- Compliance as mandatory call-path gateway, not optional middleware (pending confirmation)
- Numbers as ephemeral pool (pending confirmation)
- Python core + C/Rust voice pipeline (pending confirmation)
- Local-first inference (pending confirmation)
- [Phase 01-freeswitch-voice-pipeline]: FreeSWITCH uses host network mode in Docker — RTP port range (16384-32768) cannot be published via Docker port mapping
- [Phase 01-freeswitch-voice-pipeline]: mod_audio_stream from amigniter open-source fork — Apache 2.0 compatible, avoids commercial SignalWire dependency
- [Phase 01-freeswitch-voice-pipeline]: ESL listens on 0.0.0.0:8021 so Python orchestrator on host can connect to FreeSWITCH inside Docker
- [Phase 01-freeswitch-voice-pipeline]: soxr as primary resampler with scipy fallback; HAS_SOXR feature flag for graceful degradation
- [Phase 01-freeswitch-voice-pipeline]: Deferred model loading pattern: STTEngine/TTSEngine initialize() called once at startup, not in __init__
- [Phase 01-freeswitch-voice-pipeline]: VAD set_pipeline_state() accepts optional timestamp for deterministic testing without mocking
- [Phase 01-freeswitch-voice-pipeline]: _make_inbound() factory method separates Genesis import for testability without Genesis installed
- [Phase 01-freeswitch-voice-pipeline]: asyncio.get_event_loop().run_until_complete() used in tests since pytest-asyncio not installed on system Python
- [Phase 01-freeswitch-voice-pipeline]: asyncio.Queue token_queue pattern: LLM streams into queue, TTS consumes from same queue — enables streaming TTS before LLM response complete (pipeline coordinator)
- [Phase 01-freeswitch-voice-pipeline]: _tts_cancel asyncio.Event for barge-in coordination: shared between feed_tokens() and TTS loop, avoids hard task cancellation race conditions
- [Phase 01-freeswitch-voice-pipeline]: base64-encoded JSON for TTS audio to FreeSWITCH (mod_audio_stream protocol) — safer than raw binary, optimize later
- [Phase 01-freeswitch-voice-pipeline]: Python 3.9 compat: use Optional[T] not T|None union syntax in main.py
- [Phase 01-freeswitch-voice-pipeline]: websockets 15.x: handler takes single websocket arg; path via websocket.request.path
- [Phase 02-telecom-abstraction-compliance]: Append-only consent: revocations are INSERT rows with revoked_at populated — never UPDATE, legally required per D-14
- [Phase 02-telecom-abstraction-compliance]: AuditLog dual-write: JSONL is primary immutable record, SQLite is derived queryable index per D-21
- [Phase 02-telecom-abstraction-compliance]: ComplianceModule ABC defined with single abstract check_outbound() method — country modules implement only this one contract
- [Phase 02-telecom-abstraction-compliance]: TelecomSession uses composition not inheritance — voice_session field is Optional[VoiceSession], set after call answers
- [Phase 02-telecom-abstraction-compliance]: NumberPool uses TYPE_CHECKING guard for redis import — avoids hard import error when redis-py not installed
- [Phase 02-telecom-abstraction-compliance]: ComplianceGateway in gateway.py alongside ABC — structural guarantee explicit in single file
- [Phase 02-telecom-abstraction-compliance]: JurisdictionRouter longest-prefix-match via sorted(keys, key=len, reverse=True) — simple, correct for <50 country modules
- [Phase 02-telecom-abstraction-compliance]: TemplateComplianceModule denies all calls (fail-closed default) — prevents accidentally allowing non-compliant calls from unimplemented template
- [Phase 02-telecom-abstraction-compliance]: check_time_of_day() accepts optional now parameter for deterministic testing without mocking
- [Phase 02-telecom-abstraction-compliance]: US compliance check order: DNC -> time-of-day -> consent (cheapest-first I/O)
- [Phase 02-telecom-abstraction-compliance]: Transcript WhisperModel is a separate CPU instance from live STT model — Pitfall 6 prevents model contention
- [Phase 02-telecom-abstraction-compliance]: stop_recording() sends explicit uuid_record stop — does not rely on RECORD_STOP event (Pitfall 1)
- [Phase 02-telecom-abstraction-compliance]: telecom_sessions dict in main() closure — scoped to call path lifetime
- [Phase 03-sms-agent-interface-cli]: prompt parameter on call tool uses nullable type pattern [string, null] per OpenAI strict mode Pitfall 4
- [Phase 03-sms-agent-interface-cli]: ToolExecutor catches ComplianceBlockError specifically before generic Exception — ensures D-02 structured response never masked
- [Phase 03-sms-agent-interface-cli]: Shared delivery_store dict between SMSClient and HollerHook — hook updates in-place, client reads; avoids separate sync mechanism
- [Phase 03-sms-agent-interface-cli]: HollerHook duck-typed (no AbstractHook inheritance at class definition) to avoid hard aiosmpplib import at module load
- [Phase 03-sms-agent-interface-cli]: sms_checked() reuses ComplianceModule.check_outbound() for SMS — same contract as voice; gateway method differentiates the action
- [Phase 03-sms-agent-interface-cli]: tool_calls_accumulator dict keyed by chunk index — reassembles fragmented tool_calls from streaming delta chunks
- [Phase 03-sms-agent-interface-cli]: TTS queue flushed via None sentinel before tool execution — prevents pipeline deadlock (Pitfall 2)
- [Phase 03-sms-agent-interface-cli]: extra_history scoped to turn — tool results not added to session.history until turn completes (clean rollback semantics)
- [Phase 03-sms-agent-interface-cli]: load_dotenv override=False: .holler.env file values never override shell env vars -- explicit env always wins
- [Phase 03-sms-agent-interface-cli]: SMS client optional init: SMSClient object always created but initialize() called only if password is non-empty -- safe no-op when SMSC absent
- [Phase 03-sms-agent-interface-cli]: ToolExecutor created before VoicePipeline: executor needs esl+sms+compliance+pool; pipeline receives executor as constructor arg
- [Phase 03-sms-agent-interface-cli]: Click --pass alias: trunk command exposes both --password and --pass via Click option name list per D-15
- [Phase 04-cli-docker-onboarding-fixes]: __file__-based _get_project_root() navigates commands.py -> cli/ -> holler/ -> project_root/ for CWD-independent compose path
- [Phase 04-cli-docker-onboarding-fixes]: docker compose --project-directory set to docker/ dir so relative volume paths resolve correctly from any CWD
- [Phase 04-cli-docker-onboarding-fixes]: ${VAR:-} syntax in docker-compose.yml environment block allows unset trunk vars without compose errors
- [Phase 04-cli-docker-onboarding-fixes]: X-PRE-PROCESS defaults in vars.xml ensure FreeSWITCH starts cleanly when trunk not yet configured
- [Phase 05-sms-inbound-stt-optout-wiring]: Inline import of check_optout_keywords inside _respond() to avoid circular import (telecom.__init__ -> telecom.session -> voice.pipeline)
- [Phase 05-sms-inbound-stt-optout-wiring]: telecom_sessions dict moved before pipeline/SMS init so _handle_stt_optout closure captures it at definition time
- [Phase 05-sms-inbound-stt-optout-wiring]: VoicePipeline.__init__ backward compatible: on_optout/opt_out_keywords params default to None/[] respectively
- [Phase quick]: HOLLER_COMPOSE_FILE env var override in _start_services() — env var takes priority over __file__-based and CWD resolution
- [Phase quick]: CWD fallback in _start_services() — Path.cwd()/docker/ checked when __file__-based path has no docker-compose.yml; handles pip install scenario
- [Phase quick]: FreeSWITCH Docker build uses 7-stage Alpine source build (signalwire/freeswitch v1.10.12) — libks and spandsp compiled from source since Alpine 3.21 has no packages for them; no SignalWire PAT required

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2 prep]: STIR/SHAKEN STI-PA certificate registration has bureaucratic lead time — begin registration during Phase 2, not after
- [Phase 2]: Research flag on compliance gateway — STIR/SHAKEN cert integration and 2025 FCC opt-out expansion warrant research before coding
- [Phase 1]: Research flag on voice pipeline — mod_audio_stream WebSocket integration and faster-whisper streaming config warrant research before coding

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260324-r7i | Align README, create missing docs (CONTRIBUTING.md, LICENSE) | 2026-03-25 | 9b6fa15 | [260324-r7i-align-the-readme-missing-docs-quick-pass](./quick/260324-r7i-align-the-readme-missing-docs-quick-pass/) |
| 260324-ubt | Fix holler init: correct Kokoro ONNX HF repo (fastrtc/kokoro-onnx) + CWD fallback for docker-compose.yml | 2026-03-25 | 60c2072 | [260324-ubt-fix-holler-init-kokoro-onnx-model-downlo](./quick/260324-ubt-fix-holler-init-kokoro-onnx-model-downlo/) |
| 260325-cmo | Remove SignalWire PAT requirement: FreeSWITCH source build on Alpine, zero vendor accounts | 2026-03-25 | 4d90c79 | [260325-cmo-audit-and-fix-vendor-dependencies-contra](./quick/260325-cmo-audit-and-fix-vendor-dependencies-contra/) |
| 260325-iha | Fix FreeSWITCH Docker build: Alpine 3.20, spandsp autoreconf, disable-libvpx, runtime libs | 2026-03-25 | 79fd918 | [260325-iha-fix-freeswitch-docker-build-failure-at-b](./quick/260325-iha-fix-freeswitch-docker-build-failure-at-b/) |
| 260325-kq8 | Fix FreeSWITCH doubled config path (--sysconfdir=/etc) + consent_db mkdir parent dir | 2026-03-25 | 298bc55 | [260325-kq8-fix-freeswitch-doubled-config-path-conse](./quick/260325-kq8-fix-freeswitch-doubled-config-path-conse/) |

## Session Continuity

Last session: 2026-03-25T14:14:56Z
Stopped at: Completed quick/260325-cmo-audit-and-fix-vendor-dependencies-contra/260325-cmo-PLAN.md
Resume file: None

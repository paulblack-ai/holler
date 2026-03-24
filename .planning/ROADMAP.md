# Roadmap: Holler

## Overview

Three phases build from raw infrastructure to a fully operable, legally compliant, agent-native telecom stack. Phase 1 proves the core thesis by putting a working voice call through local hardware. Phase 2 makes calls production-ready by adding compliance, session state, and call records. Phase 3 delivers the complete agent interface — SMS, tool-use protocol, and four-command onboarding.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: FreeSWITCH + Voice Pipeline** - Working voice call through local hardware with streaming STT/TTS under 800ms
- [x] **Phase 2: Telecom Abstraction + Compliance** - Session state, number pool, mandatory compliance gateway, US module, call records (completed 2026-03-24)
- [ ] **Phase 3: SMS + Agent Interface + CLI** - SMPP messaging, tool-use protocol, and four-command onboarding

## Phase Details

### Phase 1: FreeSWITCH + Voice Pipeline
**Goal**: A voice call can be placed and received through local FreeSWITCH infrastructure with a fully local STT/TTS loop completing under 800ms
**Depends on**: Nothing (first phase)
**Requirements**: CALL-01, CALL-02, CALL-03, CALL-06, VOICE-01, VOICE-02, VOICE-03, VOICE-04, VOICE-05, VOICE-06, VOICE-07
**Success Criteria** (what must be TRUE):
  1. Python can originate and hang up a raw outbound SIP call via FreeSWITCH ESL against a configured SIP trunk
  2. Python can answer an inbound SIP call and connect it to a voice session
  3. Audio from the caller flows through local faster-whisper STT and produces a partial transcript stream; local Kokoro TTS produces audio streamed back to the call
  4. The full voice loop (human speaks → VAD gates → STT partial → LLM response → TTS first chunk delivered) completes in under 800ms measured end-to-end
  5. Human barge-in stops TTS playback mid-utterance; silence gates STT to prevent hallucination
**Plans**: 5 plans

Plans:
- [x] 01-01-PLAN.md — Project skeleton, Docker Compose (FreeSWITCH + Redis), FreeSWITCH configuration
- [x] 01-02-PLAN.md — Voice pipeline components: STT, TTS, VAD, audio resampler
- [x] 01-03-PLAN.md — FreeSWITCH ESL call control: originate, answer, hangup, event routing
- [x] 01-04-PLAN.md — Audio bridge WebSocket server, LLM client, streaming pipeline coordinator
- [ ] 01-05-PLAN.md — Application entry point, config, integration tests, live verification

**UI hint**: no

### Phase 2: Telecom Abstraction + Compliance
**Goal**: Calls are session-aware, number-pool-managed, jurisdiction-routed, and structurally blocked from reaching PSTN without passing the compliance gateway — with a working US compliance module, consent state machine, call recording, and post-call transcript
**Depends on**: Phase 1
**Requirements**: CALL-04, CALL-05, TEL-01, TEL-02, TEL-03, COMP-01, COMP-02, COMP-03, COMP-04, COMP-05, COMP-06, COMP-07
**Success Criteria** (what must be TRUE):
  1. A DID is atomically checked out from the number pool at session start and released on call end; no call can originate without a pool DID
  2. An outbound call to a US number fails to connect (not bypassed, explicitly blocked) if the destination is on the DNC list, outside 8am–9pm recipient local time, or lacks prior consent record
  3. A caller who opts out mid-call via DTMF or spoken keyword is immediately logged to the append-only consent DB and subsequent calls to that number are blocked
  4. Every compliance check (TCPA, DNC, time-of-day, consent) produces an immutable audit log entry with timestamp, result, and call context
  5. The call recording (WAV) and post-call transcript are persisted and retrievable after the call ends
**Plans**: 5 plans

Plans:
- [x] 02-01-PLAN.md — Foundational types (ComplianceModule ABC, TelecomSession), NumberPool, config extensions
- [x] 02-02-PLAN.md — Data layer: ConsentDB (append-only), DNCList, AuditLog (JSONL + SQLite)
- [x] 02-03-PLAN.md — ComplianceGateway (mandatory pre-originate check), JurisdictionRouter, country template
- [x] 02-04-PLAN.md — US compliance module: TCPA time-of-day, DNC check, consent verification
- [x] 02-05-PLAN.md — Call recording, post-call transcription, opt-out capture, main.py integration

### Phase 3: SMS + Agent Interface + CLI
**Goal**: An LLM can use Holler as a tool — initiating calls, sending and receiving SMS, and completing the full workflow in four CLI commands from a clean install
**Depends on**: Phase 2
**Requirements**: SMS-01, SMS-02, SMS-03, AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06
**Success Criteria** (what must be TRUE):
  1. An LLM issues a `call`, `sms`, `hangup`, or `transfer` tool invocation and the corresponding action executes through Holler without any code outside the tool protocol
  2. The same agent code works unchanged against any LLM that supports function/tool calling (OpenAI, Anthropic, local Ollama — no adapter required)
  3. An outbound SMS sent via `sms()` tool invocation delivers via SMPP, and delivery status (sent/delivered/failed) is returned to the agent; an inbound SMS routes to an agent session
  4. Running `pip install holler`, `holler init`, `holler trunk add`, `holler call` on a machine with a GPU and SIP trunk credentials completes without error and places a live call
**Plans**: 4 plans

Plans:
- [ ] 03-01-PLAN.md — SMS client (aiosmpplib ESME), delivery receipts, inbound routing, compliance SMS extension
- [ ] 03-02-PLAN.md — Tool definitions (call/sms/hangup/transfer), ToolExecutor, Anthropic adapter
- [ ] 03-03-PLAN.md — LLM tool-call streaming, VoicePipeline tool-call interception and agent loop
- [ ] 03-04-PLAN.md — Config extension (.holler.env), Click CLI (init/trunk/call), main.py integration

**UI hint**: no

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. FreeSWITCH + Voice Pipeline | 4/5 | In Progress|  |
| 2. Telecom Abstraction + Compliance | 5/5 | Complete   | 2026-03-24 |
| 3. SMS + Agent Interface + CLI | 0/4 | Not started | - |

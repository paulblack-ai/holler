# Requirements: Holler

**Defined:** 2026-03-24
**Core Value:** An AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation — no vendor accounts, no API keys, no human in the loop.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Call Management

- [x] **CALL-01**: Agent can initiate an outbound voice call to a PSTN number via FreeSWITCH ESL
- [x] **CALL-02**: FreeSWITCH softswitch routes SIP calls to/from a configured SIP trunk
- [x] **CALL-03**: Agent can answer and route an inbound call to an agent session
- [ ] **CALL-04**: Call recording captures audio and stores as retrievable file (WAV/MP3)
- [ ] **CALL-05**: Post-call transcript is generated and persisted alongside recording
- [x] **CALL-06**: Call terminates gracefully on agent instruction, error, or remote hangup

### Voice Pipeline

- [x] **VOICE-01**: STT runs locally via faster-whisper with streaming partial transcripts
- [x] **VOICE-02**: TTS runs locally via Kokoro-ONNX (default) with streaming audio output
- [x] **VOICE-03**: Full voice loop (STT → LLM → TTS) completes in under 800ms round-trip
- [x] **VOICE-04**: Voice Activity Detection (VAD) gates STT to prevent hallucination on silence
- [x] **VOICE-05**: Turn detection identifies when human stops speaking using VAD + silence threshold
- [x] **VOICE-06**: Barge-in detection stops TTS playback when human interrupts mid-utterance
- [x] **VOICE-07**: Audio resampling handles 8kHz PSTN G.711 to 16kHz Whisper input without quality loss

### Telecom Abstraction

- [ ] **TEL-01**: Number pool manager checks out a DID per session and releases it on call end
- [ ] **TEL-02**: Session state tracks conversation context, turn history, and tool-call state for the call lifetime
- [ ] **TEL-03**: Jurisdiction router maps E.164 destination prefix to the correct country compliance module

### Compliance

- [ ] **COMP-01**: Compliance gateway is mandatory in the outbound call path — no bypass route exists
- [ ] **COMP-02**: US module enforces TCPA: prior consent verification, caller identification, time-of-day restrictions (8am-9pm recipient local time)
- [ ] **COMP-03**: US module performs DNC (Do Not Call) list check before call connects
- [ ] **COMP-04**: Consent/opt-out state machine captures and enforces opt-out requests (DTMF or spoken) during call
- [ ] **COMP-05**: Audit log records every compliance check with timestamp, result, and call context
- [ ] **COMP-06**: Country module plugin interface allows adding new jurisdictions without modifying core
- [ ] **COMP-07**: Country module template (`_template/`) scaffolds a new jurisdiction with documented contract

### SMS

- [ ] **SMS-01**: Agent can send an SMS to a phone number via SMPP protocol
- [ ] **SMS-02**: Agent can receive inbound SMS and route to an agent session
- [ ] **SMS-03**: SMS delivery status (sent, delivered, failed) is reported back to the agent

### Agent Interface

- [ ] **AGENT-01**: Tool-use protocol exposes `call`, `sms`, `hangup`, `transfer` actions as LLM tool invocations
- [ ] **AGENT-02**: Agent interface is LLM-agnostic — works with any model that supports tool/function calling
- [ ] **AGENT-03**: CLI provides `holler init` to download models and start local services
- [ ] **AGENT-04**: CLI provides `holler trunk add` to configure SIP trunk credentials
- [ ] **AGENT-05**: CLI provides `holler call` to make a call with an agent prompt in one command
- [ ] **AGENT-06**: Four-command onboarding: install → init → trunk → call

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Agent Mesh

- **MESH-01**: Agent-to-agent voice communication via WebRTC without PSTN
- **MESH-02**: Janus WebRTC gateway handles SDP negotiation between agent endpoints
- **MESH-03**: Agent mesh operates with zero carrier involvement and zero cost

### Advanced Voice

- **ADVV-01**: Orpheus TTS available as premium voice option for GPU-rich deployments
- **ADVV-02**: Multi-GPU session dispatcher routes concurrent calls to least-loaded GPU worker
- **ADVV-03**: Whisper.cpp (C/Rust) available as optimized STT alternative to faster-whisper

### Monitoring

- **MON-01**: Structured JSON call logs with duration, transcript, tool calls, compliance checks
- **MON-02**: Prometheus metrics for call latency, error rates, concurrent sessions
- **MON-03**: Webhook/event callbacks notify external systems of call events (answered, ended, transcript ready)

### Extended Compliance

- **XCOMP-01**: UK country module (Ofcom rules)
- **XCOMP-02**: STIR/SHAKEN A-level attestation with STI-PA certificate registration

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud-hosted SaaS offering | Contradicts permissionless core; would require carrier licenses and create vendor dependency |
| Built-in LLM / bundled language model | Forces model choice; out of scope for telecom infra; tool-use protocol is LLM-agnostic |
| No-code visual flow builder / GUI | Diverges from CLI/API philosophy; agent logic stays in agent code |
| Per-agent static number assignment | Wastes DIDs; breaks ephemeral pool model; identity travels with session context |
| WhatsApp / RCS integration | Requires Business API accounts; regulatory complexity; defer to v2+ community modules |
| Built-in CRM / contact management | Out of scope for telecom infra; creates GDPR/CCPA surface area |
| Automated outbound dialing campaigns | TCPA/DNC exposure; campaign orchestration is the agent's job, not Holler's |
| Voice cloning / custom voice models | Ethical/legal risk; Kokoro/Orpheus defaults are sufficient |
| Carrier / number provisioning API | Would require carrier relationships and telecom licenses |
| Real-time dashboard GUI | Frontend scope; operators use structured logs + Grafana |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CALL-01 | Phase 1 | Complete |
| CALL-02 | Phase 1 | Complete |
| CALL-03 | Phase 1 | Complete |
| CALL-04 | Phase 2 | Pending |
| CALL-05 | Phase 2 | Pending |
| CALL-06 | Phase 1 | Complete |
| VOICE-01 | Phase 1 | Complete |
| VOICE-02 | Phase 1 | Complete |
| VOICE-03 | Phase 1 | Complete |
| VOICE-04 | Phase 1 | Complete |
| VOICE-05 | Phase 1 | Complete |
| VOICE-06 | Phase 1 | Complete |
| VOICE-07 | Phase 1 | Complete |
| TEL-01 | Phase 2 | Pending |
| TEL-02 | Phase 2 | Pending |
| TEL-03 | Phase 2 | Pending |
| COMP-01 | Phase 2 | Pending |
| COMP-02 | Phase 2 | Pending |
| COMP-03 | Phase 2 | Pending |
| COMP-04 | Phase 2 | Pending |
| COMP-05 | Phase 2 | Pending |
| COMP-06 | Phase 2 | Pending |
| COMP-07 | Phase 2 | Pending |
| SMS-01 | Phase 3 | Pending |
| SMS-02 | Phase 3 | Pending |
| SMS-03 | Phase 3 | Pending |
| AGENT-01 | Phase 3 | Pending |
| AGENT-02 | Phase 3 | Pending |
| AGENT-03 | Phase 3 | Pending |
| AGENT-04 | Phase 3 | Pending |
| AGENT-05 | Phase 3 | Pending |
| AGENT-06 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0

---
*Requirements defined: 2026-03-24*
*Last updated: 2026-03-24 after roadmap creation*

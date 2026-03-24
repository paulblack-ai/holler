# Project Research Summary

**Project:** Holler — self-hosted agentic telecom infrastructure
**Domain:** AI voice + SMS infrastructure for autonomous agents
**Researched:** 2026-03-24
**Confidence:** MEDIUM-HIGH

## Executive Summary

Holler sits at the intersection of two mature domains — production VoIP (FreeSWITCH, SIP, PSTN) and real-time AI voice pipelines (STT/TTS, streaming inference) — that are rarely combined in a fully self-hosted, agent-native configuration. Building this correctly requires expert-level understanding of both domains simultaneously: telecom operators know how to run FreeSWITCH but not how to stream audio into Whisper; AI voice developers know how to run STT pipelines but not how to handle 8 kHz G.711 codec negotiation, NAT traversal, or TCPA compliance. The research confirms the stack is well-defined and the patterns are clear, but the integration complexity is high and almost every pitfall comes from the boundary between these two worlds.

The recommended approach is a dependency-respecting seven-phase build order anchored by FreeSWITCH as the softswitch core. The voice pipeline (faster-whisper + Kokoro) connects to FreeSWITCH via mod_audio_stream WebSocket, controlled via ESL using the Genesis library. Critically, the compliance gateway must be structurally non-bypassable from Phase 3 onward — not optional middleware. The entire architecture's legal credibility rests on the compliance gateway being the only exit path for outbound calls. The project's clearest market differentiator is that no existing platform (commercial or open-source) enforces compliance in-path as a structural guarantee, and no commercial platform is self-hosted without vendor accounts.

The top risks are latency (blowing the 800ms budget before the LLM produces a token), TCPA legal exposure (from any bypass path in the compliance gateway), and audio codec mismatch (8 kHz PSTN vs 16 kHz Whisper input). All three are preventable with deliberate design choices from Phase 1. STIR/SHAKEN certificate registration with the STI-PA has bureaucratic lead time and must begin before the US compliance module is coded. The four-command onboarding goal is achievable but must be built last — building it early produces a fragile wrapper around unfinished components.

---

## Key Findings

### Recommended Stack

The stack is fully open-source and production-proven. FreeSWITCH 1.10.12 is the right softswitch (not Asterisk — FreeSWITCH scales to thousands of concurrent calls and has first-class WebRTC support; Asterisk is monolithic and harder to scale beyond a few hundred). Python 3.11+ is the orchestration language; Genesis (v2026.3.21, asyncio-native, 29 releases) is the ESL client. The voice pipeline uses faster-whisper for STT (4x faster than openai/whisper, built-in Silero VAD v6) and Kokoro ONNX for TTS (82M parameters, 96x real-time on GPU, real-time on CPU, Apache 2.0). Orpheus TTS is available as a premium upgrade for GPU-rich deployments. Janus Gateway handles WebRTC for agent-to-agent mesh. Redis handles hot session state; PostgreSQL handles durable compliance records.

**Core technologies:**
- FreeSWITCH 1.10.12: SIP softswitch, RTP anchoring, codec bridging — only mature open-source softswitch that scales to multi-hundred concurrent calls with WebRTC support built in
- faster-whisper 1.2.1: streaming STT — 4x faster than vanilla Whisper, built-in VAD, Python-first API
- Kokoro ONNX 0.5.x: primary TTS — real-time on CPU, Apache 2.0, 54 voices, best speed/quality/cost balance
- Janus Gateway 1.4.0: WebRTC media server — bridges WebRTC to SIP, enables agent-to-agent mesh without PSTN
- Genesis 2026.3.21: FreeSWITCH ESL via asyncio — actively maintained, OpenTelemetry support, MIT license
- Redis 7.x: session state and number pool — sub-millisecond reads, EXPIRE-based DID cleanup, pubsub
- Python 3.11+: orchestration — asyncio is non-negotiable for concurrent call handling

**Do not use:** rhasspy/piper (archived October 2025), openai/whisper original (4x slower), Twilio/Vonage/Vapi/Bland (cloud vendor, violates permissionless core), switchio (maintenance uncertain), gevent for new code.

See `.planning/research/STACK.md` for full version matrix and deployment variants by GPU profile.

### Expected Features

The feature set divides cleanly into three tiers. The MVP must prove the core thesis: an AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation. The competitor analysis shows that no commercial platform (Vapi, Retell, Bland, Synthflow) and no open-source alternative (jambonz, LiveKit Agents) occupies the "zero vendor accounts + structural compliance enforcement" position. That is Holler's uncontested space.

**Must have (table stakes) — v1:**
- Outbound voice call via tool invocation — proves the primary thesis
- Local STT + TTS pipeline — faster-whisper + Piper/Kokoro; no cloud dependencies
- FreeSWITCH + SIP trunk connectivity — PSTN access; RTP media handling
- Sub-800ms round-trip latency — requires streaming at every pipeline stage
- Turn detection and barge-in handling — VAD + two-layer detection to avoid false interruptions
- DID pool manager (ephemeral checkout/release) — numbers as resources, not identities
- Session state tracking — conversation context for call lifetime
- US compliance gateway (TCPA + STIR/SHAKEN + DNC) — legally required; proves country module pattern
- Consent/opt-out state machine — enforced in call path, not advisory
- Country module plugin interface + `_template/` — extensibility; enables community contributions
- Call recording + post-call transcript — audit trail; compliance requirement
- SMS send/receive via SMPP — secondary channel; simpler than voice
- Four-command onboarding — `holler init`, configure trunk, `holler call`

**Should have (competitive) — v1.x:**
- Agent-to-agent WebRTC mesh — zero-cost, zero-regulation agent communication; true differentiator vs all competitors
- Inbound call handling — natural extension once outbound proven
- Live transcription streaming — real-time transcript events during call
- Jurisdiction router — E.164 prefix to country module dispatch
- Warm call transfer (AI to human) — escalation workflows
- Webhooks / event callbacks — HTTP callbacks for call events
- Structured monitoring and metrics — Prometheus + structured JSON logs

**Defer (v2+):**
- UK country module (community-contributed after template + US prove the pattern)
- Multi-GPU call scaling (only needed when single-GPU concurrency saturates)
- Post-call analytics with tool-call trace
- WhatsApp/RCS channel modules
- GSM modem fallback for SMS

**Anti-features to reject explicitly:** cloud SaaS option (contradicts permissionless core), built-in LLM (out of scope), no-code visual flow builder (diverges from CLI/API philosophy), per-agent static number assignment (wastes DIDs), voice cloning (ethical/legal risk, out of scope).

See `.planning/research/FEATURES.md` for full prioritization matrix and competitor comparison table.

### Architecture Approach

The architecture is a strict layered pipeline: Agent Runtime → Telecom Abstraction Layer → Voice Pipeline → Compliance Gateway → FreeSWITCH → PSTN/WebRTC. Each layer has a single job and clean boundaries. The compliance gateway sits structurally between the voice pipeline and FreeSWITCH — there is no code path that bypasses it. The voice pipeline uses streaming at every stage (partial STT transcripts feed the LLM while the user is still speaking; TTS begins synthesis on the first sentence fragment while the LLM generates the second). Call infrastructure transitions are controlled by a deterministic Python state machine; the LLM requests actions, the state machine executes them via ESL. Two parallel connections from Python to FreeSWITCH serve different jobs: ESL TCP is the control plane (one persistent connection, many calls), mod_audio_stream WebSocket is the media plane (one connection per active call).

**Major components:**
1. Agent Runtime — LLM session management, tool dispatch (`call()`, `sms()`, `transfer()`, `hangup()`), conversation context
2. Telecom Abstraction Layer — number pool checkout/release, session state (Redis hot + PostgreSQL durable), jurisdiction routing
3. Voice Pipeline — streaming VAD → STT → LLM → TTS loop; Python async; faster-whisper + Kokoro
4. Compliance Gateway — mandatory plugin interface; US module ships with core; no bypass path exists
5. FreeSWITCH — SIP signaling, RTP anchoring, codec bridging, recording; controlled via ESL TCP
6. Janus WebRTC Gateway — agent-to-agent mesh; independent of PSTN path; can be parallelized
7. SMS Handler — SMPP to carrier SMSC or gammu/kannel for GSM modem; independent of voice pipeline
8. Consent DB + Audit Logger — PostgreSQL append-only; immutable; never mutable

See `.planning/research/ARCHITECTURE.md` for full data flow diagrams, component boundary table, and build order rationale.

### Critical Pitfalls

1. **8 kHz / 16 kHz codec mismatch** — PSTN delivers G.711 at 8 kHz; faster-whisper expects 16 kHz. Configure FreeSWITCH to transcode to 16 kHz L16 at ingest. Never skip a codec negotiation test against a real SIP trunk before claiming the pipeline works. (Phase 1)

2. **Latency budget exhausted before LLM first token** — VAD delay + non-streaming STT + LLM network hop can exceed 800ms before TTS begins. Design streaming end-to-end from day one. Set per-stage budgets: VAD < 50ms, STT first segment < 200ms, LLM first token < 300ms, TTS first chunk < 100ms. Instrument from the start. (Phase 2)

3. **TCPA compliance gateway bypassed** — A single call to a DNC-listed number without consent = $500-$1,500 TCPA fine; class action exposure is measured in hundreds of millions. Make the compliance gateway structurally non-bypassable. The gateway object is always instantiated and always called — test mode returns PASS, not bypass. (Phase 4; must not be deferred past first outbound call capability)

4. **NAT traversal unsolved for SIP and WebRTC simultaneously** — One-way audio is the most reported VoIP bug. Set `ext-rtp-ip` and `ext-sip-ip` explicitly in FreeSWITCH sofia profile; disable SIP ALG on any router in the path; deploy coturn as a first-class requirement for Janus (15-20% of real connections require TURN). Use `--network=host` for FreeSWITCH in Docker (Docker cannot forward the full RTP port range). (Phase 1)

5. **STIR/SHAKEN certificate registration not started early** — FCC September 2025 mandates self-hosted operators obtain their own SPC token. STI-PA registration is a bureaucratic process with lead time. Begin registration in parallel with US module development, not after it. (Phase 4 prep)

6. **LLM driving call infrastructure state** — LLMs hallucinate. A production system where the LLM can directly hang up, transfer, or enter hold states will fail at scale. LLM emits tool requests; a deterministic Python state machine evaluates and executes them via ESL.

7. **GPU memory contention on single-GPU deployments** — faster-whisper + Kokoro + local LLM on the same RTX 3060 (12GB VRAM) causes model eviction and multi-second reload times. Pin each model at startup with allocated VRAM. On CPU-constrained hardware: use Kokoro ONNX on CPU (fast enough at 50-100ms) and a quantized LLM (Q4_K_M, 4-6GB).

See `.planning/research/PITFALLS.md` for the full pitfall list including phase-specific warning table.

---

## Implications for Roadmap

The architecture research provides a dependency-respecting seven-phase build order. The sequence below follows those hard dependencies with minor grouping adjustments based on pitfall priorities.

### Phase 1: FreeSWITCH Foundation and SIP Connectivity

**Rationale:** Nothing else exists without a working softswitch. Every downstream component — voice pipeline, compliance gateway, session state — depends on FreeSWITCH being able to place and receive calls. NAT traversal and codec configuration must be resolved here because they cannot be diagnosed after higher layers are built.
**Delivers:** Python can originate and hang up a raw SIP call via ESL. SIP trunk is registered and verified. RTP port range is configured. ext-rtp-ip is explicit. SIP ALG is documented as a known kill switch.
**Addresses:** Outbound call initiation (table stakes), SIP trunk connectivity (table stakes)
**Avoids:** NAT one-way audio (Pitfall 5), FreeSWITCH B2BUA misunderstanding (Pitfall 3), default session limits too low (Pitfall 14), ext-rtp-ip autodiscovery failure (Pitfall 15), Docker RTP port range freeze (Pitfall 5), ESL connection state unreliability (Pitfall 9)
**Research flag:** Standard patterns — FreeSWITCH ESL integration is well-documented; skip research phase.

### Phase 2: Streaming Voice Pipeline

**Rationale:** The voice pipeline must be proven at the protocol level — including latency measurement — before session abstraction layers are added. Adding Redis, compliance logic, and call state on top of a pipeline with unknown latency produces a system where you cannot isolate the bottleneck.
**Delivers:** Full voice loop functional end-to-end. STT receives audio from FreeSWITCH via mod_audio_stream WebSocket. TTS sends audio back. Latency instrumented per stage. Sub-800ms round-trip verified. Whisper hallucination on silence suppressed via silero-VAD gating. Barge-in detection operational.
**Uses:** faster-whisper 1.2.1, Kokoro ONNX 0.5.x, silero-VAD 6.2.1, mod_audio_stream, Genesis ESL
**Implements:** Voice Pipeline component, VAD → STT → LLM → TTS streaming loop
**Avoids:** 8 kHz / 16 kHz codec mismatch (Pitfall 1 — critical), latency budget blow-out (Pitfall 2 — critical), Whisper hallucination on silence (Pitfall 18), barge-in on backchannels (Pitfall 8), codec transcoding compounding (Pitfall 12), GPU VRAM contention (Pitfall 11)
**Research flag:** Needs research phase — specific mod_audio_stream WebSocket integration patterns and faster-whisper streaming segment configuration warrant targeted investigation before coding.

### Phase 3: Telecom Abstraction Layer

**Rationale:** Session state and number pool management must exist before compliance checks can run (the compliance gateway needs session context: destination, consent reference, jurisdiction). The jurisdiction router must exist before country modules can be loaded.
**Delivers:** Session-aware calls with ephemeral DID management. Call state machine handles ESL events deterministically. Jurisdiction router resolves E.164 prefix to country plugin. Number pool uses atomic checkout with SELECT FOR UPDATE SKIP LOCKED. Redis for hot state; PostgreSQL schema for durable records.
**Uses:** Redis 7.x, PostgreSQL, Python asyncio
**Implements:** Number Pool Manager, Session Store, Call State Machine, Jurisdiction Router
**Avoids:** Number pool race conditions under concurrent load (Pitfall 7), LLM driving call infrastructure state (Anti-Pattern 2), tool call latency doubling LLM budget (Pitfall 10 — pre-fetch compliance/DNC at session init)
**Research flag:** Standard patterns — Redis pool management and PostgreSQL session schema are well-understood; skip research phase.

### Phase 4: Compliance Gateway and US Module

**Rationale:** This is the phase that makes the system legally operable. Compliance must be proven before declaring any call "production-ready." The US module ships with the core — it proves the country module plugin pattern and demonstrates the structural guarantee that no call exits without passing the gateway. Begin STI-PA registration in parallel with this phase, not after.
**Delivers:** Compliant US outbound calling. ComplianceGateway plugin interface is the only exit path. US module implements TCPA consent check, DNC scrub, time-of-day check, mandatory AI disclosure injection, and STIR/SHAKEN attestation handling. Consent DB is append-only and auditable. Audit logger is immutable. Country module `_template/` is documented for community contributors.
**Uses:** PostgreSQL (consent DB, audit log), Redis (DNC Bloom filter), STIR/SHAKEN certificate chain
**Implements:** Compliance Gateway, US Country Module, Consent DB, Audit Logger, Country Module Plugin Interface
**Avoids:** TCPA compliance bypass (Pitfall 4 — critical), STIR/SHAKEN certificate management ignored (Pitfall 6), call recording consent in all-party states (Pitfall 17), disclosure not wired as first utterance (Pitfall 4 new regulations)
**Research flag:** Needs research phase — STIR/SHAKEN certificate integration, STI-PA registration process, and FCC-mandated opt-out keyword handling (2025 expansion) are regulatory-domain topics that warrant dedicated research before implementation.

### Phase 5: SMS Channel

**Rationale:** SMS is architecturally independent of the voice pipeline but shares the session store and compliance gateway. It fits naturally after Phase 4 because the compliance hooks (10DLC registration, opt-out, consent for A2P) are the same gateway pattern proven in Phase 4.
**Delivers:** Outbound and inbound SMS via SMPP. Delivery receipt correlation. SMS compliance hooks through the same gateway interface. GSM modem fallback documented as a Phase 5 stretch goal.
**Uses:** aiosmpplib 0.7.x (preferred for asyncio), smpplib 2.2.4 (fallback), gammu (optional modem path)
**Implements:** SMS Handler, SMPP client, SMS compliance hooks
**Avoids:** SMPP connection keepalive failure (Pitfall 16), silent delivery receipt loss
**Research flag:** Standard patterns — SMPP 3.4 client integration is well-documented; skip research phase.

### Phase 6: Agent-to-Agent WebRTC Mesh

**Rationale:** Agent-to-agent communication is architecturally independent of the PSTN path. It can be parallelized with Phase 5 but is sequenced after it to keep the team focused on the PSTN-path MVP first. This is the feature with no analog in any commercial or open-source competitor.
**Delivers:** Two agents can communicate over WebRTC without PSTN involvement. Janus Gateway mediates sessions. `agent://` URI scheme dispatches to Janus instead of FreeSWITCH. No TCPA/STIR/SHAKEN compliance required (non-PSTN). coturn deployed as a first-class requirement.
**Uses:** Janus Gateway 1.4.0, mod_janus, aiortc 1.14.0
**Implements:** Janus WebRTC Gateway, agent-to-agent routing in Jurisdiction Router
**Avoids:** TURN server absent (Pitfall 5), Janus file descriptor limit at production volume (Pitfall 13)
**Research flag:** Needs research phase — Janus REST API, mod_janus configuration, and agent addressing scheme integration are lower-documentation areas relative to the core PSTN stack.

### Phase 7: CLI and Four-Command Onboarding

**Rationale:** The CLI wraps everything else. Building it early produces a fragile wrapper around unfinished components. At this phase, every component it initializes and validates is stable.
**Delivers:** `holler init` (generates config, verifies FreeSWITCH, checks trunk registration), `holler call` (invokes tool from CLI for testing), `holler status` (health checks all components). First-call experience requires four commands.
**Implements:** CLI, onboarding flow, health check system
**Avoids:** Fragile CLI built over unproven components, missing health checks that mask configuration errors
**Research flag:** Standard patterns — CLI tooling patterns are well-established; skip research phase.

### Phase Ordering Rationale

- FreeSWITCH first because there is no audio without the softswitch routing it. NAT and codec issues discovered here would corrupt all downstream work.
- Voice pipeline second because latency must be validated at protocol level before adding Python abstraction layers. You cannot debug latency when compliance checks, session lookups, and state machines are also in the hot path.
- Session abstraction before compliance because the compliance gateway needs session context (destination, consent reference, jurisdiction) that the abstraction layer creates.
- Compliance before any production claim — the architecture's legal credibility is the gateway. A system that can place outbound calls to PSTN without a proven compliance gate is not Holler, it's a liability.
- SMS after compliance because A2P SMS compliance (10DLC, opt-out) uses the same gateway pattern. Implementing SMS before the gateway is proven would require retrofitting.
- WebRTC after PSTN path because it is architecturally independent and the PSTN path is the core thesis. Proving the PSTN path first also validates the FreeSWITCH + session + compliance stack that WebRTC calls share.
- CLI last because the CLI is only as good as what it wraps.

### Research Flags

Phases likely needing `/gsd:research-phase` during planning:
- **Phase 2 (Voice Pipeline):** mod_audio_stream WebSocket integration details and faster-whisper streaming segment configuration are not deeply documented in official sources; community implementations vary.
- **Phase 4 (Compliance Gateway):** STIR/SHAKEN certificate integration with STI-PA, 2025 FCC opt-out keyword expansion, and California AB 2905/Texas SB 140 disclosure requirements are regulatory-domain topics requiring authoritative source review before coding.
- **Phase 6 (WebRTC Mesh):** Janus REST API integration patterns and `agent://` URI scheme design are lower-documentation relative to the core PSTN stack.

Phases with standard patterns (skip research phase):
- **Phase 1 (FreeSWITCH Foundation):** FreeSWITCH ESL and Sofia SIP profile configuration is extensively documented.
- **Phase 3 (Telecom Abstraction):** Redis pool management and PostgreSQL session schema are standard patterns.
- **Phase 5 (SMS):** SMPP 3.4 client integration is a mature, well-documented protocol.
- **Phase 7 (CLI):** CLI tooling patterns are standard.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Most versions cross-checked against official GitHub releases and PyPI. Only silero-vad and aiortc verified via WebSearch (MEDIUM). Jasmin maintenance trajectory is uncertain (last release Nov 2023) — favor aiosmpplib for SMS core path. |
| Features | MEDIUM-HIGH | Commercial platform features observed via documentation and third-party reviews; open-source features from official repos. Competitor compliance claims are partially vendor-authored. |
| Architecture | HIGH | FreeSWITCH ESL, mod_audio_stream, and streaming pipeline patterns sourced from official docs and verified community implementations. Build order derived from hard dependency analysis, not opinion. |
| Pitfalls | MEDIUM-HIGH | FreeSWITCH-specific pitfalls from official docs (HIGH). TCPA/FCC regulatory pitfalls from official FCC documents (HIGH). Audio codec, NAT, and latency pitfalls from community post-mortems and production reports (MEDIUM). |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Jasmin maintenance status:** Jasmin SMS gateway last released November 2023. Evaluate aiosmpplib as primary SMPP path in Phase 5 planning rather than Jasmin; only adopt Jasmin if routing complexity warrants it.
- **STIR/SHAKEN STI-PA registration process:** Bureaucratic lead time is documented but process specifics are not. Research Phase 4 should include contacting a STI-CA early to understand current timelines.
- **mod_audio_stream WebSocket specifics:** The module is community-maintained (amigniter); official FreeSWITCH docs are sparse. Research Phase 2 should examine actual implementation source and community examples before coding the bridge.
- **whisper.cpp vs faster-whisper boundary:** The CLAUDE.md mentions a "C/Rust voice pipeline component." If a Rust pipeline is a real requirement (not just aspiration), whisper.cpp integration details need dedicated research. Current research assumes Python-primary with faster-whisper.
- **State-level US compliance overlays:** TCPA federal rules are well-researched. California, Florida, Washington, and other state-level rules for AI voice are noted but not fully detailed. Phase 4 research should enumerate state overlays that must be in the initial US module.

---

## Sources

### Primary (HIGH confidence)
- FreeSWITCH GitHub releases — v1.10.12 confirmed: https://github.com/signalwire/freeswitch/releases
- FreeSWITCH Event Socket Library docs: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Client-and-Developer-Interfaces/Event-Socket-Library/
- FreeSWITCH NAT Traversal docs: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Networking/NAT-Traversal_3375417/
- faster-whisper GitHub releases — v1.2.1 confirmed: https://github.com/SYSTRAN/faster-whisper/releases
- Janus Gateway GitHub tags — v1.4.0 Feb 2026: https://github.com/meetecho/janus-gateway/tags
- Genesis GitHub — v2026.3.21 confirmed: https://github.com/Otoru/Genesis
- Kokoro GitHub — 82M params, Apache 2.0: https://github.com/hexgrad/kokoro
- Orpheus TTS GitHub — 3B Llama-based, Apache 2.0: https://github.com/canopyai/Orpheus-TTS
- rhasspy/piper — archived Oct 6, 2025: https://github.com/rhasspy/piper
- FCC confirms TCPA applies to AI-generated voices: https://www.fcc.gov/document/fcc-confirms-tcpa-applies-ai-technologies-generate-human-voices
- LiveKit Agents — open-source repo: https://github.com/livekit/agents
- mod_audio_stream module: https://github.com/amigniter/mod_audio_stream
- mod_janus FreeSWITCH module: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Modules/mod_janus_20709557/

### Secondary (MEDIUM confidence)
- AssemblyAI voice AI stack guide 2026 — architecture patterns and latency benchmarks
- LiveKit blog: turn detection for voice agents — VAD + endpointing patterns
- Cresta engineering blog — real-time voice agent latency engineering
- SparkCo blog — barge-in detection pitfalls
- Janus 700-person call post-mortem — production fd limit discovery
- FreeSWITCH RTP port ranges in Docker — engagespark blog
- State-by-state call recording compliance 2025 — hostie.ai
- STIR/SHAKEN 2025 implementation checklist — Bandwidth
- Vapi, Retell AI, Bland AI, Synthflow — feature analysis via documentation and third-party reviews

### Tertiary (LOW confidence)
- FreeSWITCH vs Asterisk 2026 — Samcom Technologies (single commercial source)
- Whisper streaming strategy — community forum thread (hallucination on silence patterns)

---
*Research completed: 2026-03-24*
*Ready for roadmap: yes*

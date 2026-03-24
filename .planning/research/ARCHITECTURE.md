# Architecture Research

**Domain:** Self-hosted agentic telecom infrastructure (voice + SMS for AI agents)
**Researched:** 2026-03-24
**Confidence:** HIGH — primary sources are FreeSWITCH official docs, verified community implementations, and the project's own concept brief

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT RUNTIME LAYER                                                 │
│                                                                      │
│  LLM emits tool calls: call("+1...", objective="schedule appt")      │
│  sms("+1...", body="..."), transfer(to="human"), hangup()            │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  TELECOM ABSTRACTION LAYER (Python core)                     │    │
│  │                                                              │    │
│  │  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │    │
│  │  │  Number Pool   │  │ Session Store  │  │ Jurisdiction  │  │    │
│  │  │  Manager       │  │ (call context, │  │ Router        │  │    │
│  │  │  (checkout/    │  │  history,      │  │ (dest → rules │  │    │
│  │  │   release DIDs)│  │  consent ref)  │  │  + DID select)│  │    │
│  │  └────────────────┘  └────────────────┘  └───────────────┘  │    │
│  └────────────────────────────┬─────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────▼─────────────────────────────────┐    │
│  │  VOICE PIPELINE (Python orchestration + local inference)     │    │
│  │                                                              │    │
│  │  mod_audio_stream ─ WebSocket ─▶ VAD ─▶ STT (faster-whisper)│    │
│  │                                              │               │    │
│  │                                         partial transcript   │    │
│  │                                              │               │    │
│  │                                         LLM (streaming)      │    │
│  │                                              │               │    │
│  │                                         token stream         │    │
│  │                                              │               │    │
│  │  RTP ◀─ FreeSWITCH ◀─ WebSocket ◀─── TTS (Piper/Kokoro)     │    │
│  └────────────────────────────┬─────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────▼─────────────────────────────────┐    │
│  │  COMPLIANCE GATEWAY (per-jurisdiction plugin, mandatory)     │    │
│  │  Consent check → DNC scrub → time-of-day → disclosure inject │    │
│  │  → audit log. ALL PASS or call is blocked with reason code.  │    │
│  └────────────────────────────┬─────────────────────────────────┘    │
│                               │                                      │
│  ┌────────────────────────────▼─────────────────────────────────┐    │
│  │  SIP SOFTSWITCH (FreeSWITCH)                                 │    │
│  │  Call routing, codec negotiation, RTP anchoring, recording   │    │
│  │  ESL inbound/outbound for Python control plane               │    │
│  └───────┬─────────────────────────────┬────────────────────────┘    │
└──────────┼─────────────────────────────┼─────────────────────────────┘
           │                             │
    ┌──────▼──────┐  ┌────────────┐  ┌──▼─────────────────┐
    │  SIP Trunk  │  │  GSM Modem │  │  Janus WebRTC GW   │
    │  (PSTN out) │  │  (SMS/GSM) │  │  (agent-to-agent   │
    │  ~$0.01/min │  │  gammu/    │  │   + WebRTC inbound)│
    └─────────────┘  │  kannel    │  └────────────────────┘
                     └────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|---------------|------------------------|
| Agent Runtime | LLM session management, tool dispatch, conversation context | Python + any LLM SDK; tool-use protocol |
| Telecom Abstraction Layer | Number pool, session state, jurisdiction routing, recording orchestration | Python service; Redis or PostgreSQL for state |
| Number Pool Manager | DID checkout/release lifecycle, per-interaction assignment | Python with DB-backed pool; thread-safe checkout |
| Session Store | Call context, conversation history, consent reference, multi-modal state | Redis (hot) + PostgreSQL (durable) |
| Jurisdiction Router | Map destination number prefix → compliance plugin + DID selection | Python with prefix trie or lookup table |
| Voice Pipeline | Streaming STT → LLM → TTS loop, VAD, turn detection | Python async; faster-whisper + Piper/Kokoro |
| Compliance Gateway | Per-jurisdiction checks: consent, DNC, hours, disclosure, audit | Plugin interface; US module ships with core |
| FreeSWITCH | SIP signaling, RTP anchoring, codec bridging, ESL event bus | FreeSWITCH process; controlled via ESL TCP |
| mod_audio_stream | Bridge FreeSWITCH RTP to Python voice pipeline via WebSocket | C module compiled into FreeSWITCH |
| Janus WebRTC GW | Agent-to-agent WebRTC mesh, browser/WebRTC client bridging | Janus process; mod_janus in FreeSWITCH |
| SMS Handler | SMPP session to carrier SMSC, or gammu/kannel for GSM modem | python-smpplib or kannel gateway |
| Consent DB | Immutable consent records, opt-out registry, DNC scrub state | PostgreSQL (append-only, auditable) |
| Audit Logger | Call attempt records, compliance pass/fail, disclosure confirmation | PostgreSQL; append-only; never mutable |

---

## Recommended Project Structure

```
holler/
├── core/                      # Universal kernel — no jurisdiction-specific logic
│   ├── agent/                 # Tool dispatch, conversation lifecycle
│   │   ├── tools.py           # call(), sms(), transfer(), hangup() definitions
│   │   └── session.py         # Session context object passed through pipeline
│   ├── telecom/               # Abstraction layer
│   │   ├── pool.py            # Number pool — checkout/release, DID management
│   │   ├── router.py          # Jurisdiction routing — prefix → plugin + DID
│   │   └── session_store.py   # Redis/PG-backed call state
│   ├── voice/                 # Voice pipeline orchestration
│   │   ├── pipeline.py        # Async streaming STT→LLM→TTS coordinator
│   │   ├── stt.py             # faster-whisper wrapper + VAD
│   │   ├── tts.py             # Piper/Kokoro wrapper + streaming PCM output
│   │   └── websocket.py       # mod_audio_stream WebSocket bridge
│   ├── sms/                   # SMS channel
│   │   ├── smpp.py            # SMPP client (python-smpplib wrapper)
│   │   └── modem.py           # GSM modem interface (gammu/kannel bridge)
│   ├── freeswitch/            # FreeSWITCH integration
│   │   ├── esl.py             # ESL client (asyncio-based, Genesis or switchio)
│   │   ├── dialplan.py        # Dynamic dialplan generation
│   │   └── events.py          # Event handlers — call state transitions
│   ├── compliance/            # Plugin interface only — no jurisdiction code
│   │   ├── gateway.py         # Mandatory gateway base class + plugin loader
│   │   ├── consent_db.py      # Consent record schema and query interface
│   │   └── audit.py           # Immutable audit log writer
│   └── webrtc/                # Janus WebRTC integration
│       └── janus.py           # mod_janus / Janus REST client
│
├── countries/                 # Jurisdiction plugins
│   ├── us/                    # US compliance: TCPA, STIR/SHAKEN, DNC, state overlays
│   │   ├── gateway.py         # Implements ComplianceGateway interface
│   │   ├── tcpa.py            # Consent verification, hours, disclosures
│   │   ├── stir_shaken.py     # Attestation level handling
│   │   ├── dnc.py             # National DNC + internal opt-out registry
│   │   └── state_overlays/    # Per-state rules (CA, FL, WA, etc.)
│   ├── uk/                    # Ofcom rules (light — template demonstrates pattern)
│   └── _template/             # Scaffold for new country module
│       └── gateway.py         # Annotated interface to implement
│
├── contrib/                   # Community modules, experiments
│
├── config/
│   ├── freeswitch/            # FreeSWITCH XML config fragments
│   │   ├── dialplan/
│   │   └── sip_profiles/
│   └── settings.yaml          # Holler configuration
│
├── cli/
│   └── main.py                # `holler init`, `holler call`, `holler status`
│
└── tests/
    ├── unit/
    └── integration/           # Requires FreeSWITCH running
```

### Structure Rationale

- **core/**: All jurisdiction-agnostic logic. This is what makes Holler portable. Nothing in core/ should contain a phone number prefix, regulatory rule, or compliance check.
- **countries/**: Every file here is a plugin. Adding a country means adding a directory, never touching core.
- **core/freeswitch/**: ESL integration isolated here — FreeSWITCH is a dependency, not an architectural assumption. Future alternative softswitch replacement only touches this module.
- **core/voice/**: The pipeline lives here independently of FreeSWITCH. The WebSocket bridge is how FreeSWITCH delivers audio to it, but the pipeline could receive audio from any source.
- **core/compliance/**: Contains only the interface. The compliance gateway is not optional middleware — it is instantiated and called in the call path by the router. The base class makes it impossible to place a call that bypasses it.

---

## Architectural Patterns

### Pattern 1: Streaming Pipeline (Not Sequential)

**What:** Each voice stage passes partial output to the next stage before completing. STT sends partial transcripts to LLM. LLM sends token chunks to TTS. TTS begins PCM output before full sentence is synthesized.

**When to use:** Always — for any real-time voice interaction. Sequential pipelines produce 2-4 second response delays, which destroy conversation naturalness.

**Trade-offs:** Harder to reason about; requires handling partial states, sentence boundary detection for TTS, and careful interruption handling. The latency gain (sub-800ms vs 2-4s) is not optional — it's a product requirement.

**Example:**
```python
async def voice_loop(ws: WebSocket, session: CallSession):
    async for audio_chunk in ws:
        # VAD decides if this chunk is speech
        if vad.is_speech(audio_chunk):
            stt_stream.feed(audio_chunk)

        async for partial_transcript in stt_stream.partials():
            # LLM sees partial text as user speaks
            async for token in llm.stream(partial_transcript, session.history):
                tts_buffer.feed(token)
                # TTS synthesizes first complete sentence fragment
                async for pcm_chunk in tts_buffer.sentence_chunks():
                    await ws.send_bytes(pcm_chunk)
```

### Pattern 2: Compliance Gateway as Mandatory Kernel Object

**What:** The compliance gateway is not optional middleware. The call path instantiates it unconditionally. The router selects the jurisdiction plugin, but the gateway interface is always called. There is no code path from "agent requests call" to "FreeSWITCH dials" that does not traverse the gateway.

**When to use:** Always — this is the architectural invariant that makes the compliance story credible.

**Trade-offs:** Slightly more complex initialization (plugin loading); harder to write quick test scripts that bypass it. Both costs are acceptable — the guarantee they provide is the product's legal defense posture.

**Example:**
```python
class ComplianceGateway:
    """Base class. Must be subclassed per jurisdiction."""
    async def check(self, request: CallRequest) -> GatewayResult:
        raise NotImplementedError

    async def audit(self, result: GatewayResult) -> None:
        raise NotImplementedError

# In the router — no bypass path exists
async def route_call(request: CallRequest) -> None:
    gateway = plugins.load(jurisdiction_for(request.destination))
    result = await gateway.check(request)
    await gateway.audit(result)
    if not result.passed:
        raise ComplianceBlockError(result.reason_code)
    await freeswitch.originate(request, did=result.assigned_did)
```

### Pattern 3: ESL Inbound for Control Plane, mod_audio_stream for Media

**What:** Two parallel connections from Python to FreeSWITCH serve different purposes. ESL (TCP, inbound mode) is the control plane: originate calls, execute applications, receive call state events. mod_audio_stream (WebSocket, per-call) is the media plane: raw PCM audio in/out for the voice pipeline.

**When to use:** This is the standard integration pattern for AI voice + FreeSWITCH. ESL handles call lifecycle; mod_audio_stream handles the audio stream that feeds STT and delivers TTS.

**Trade-offs:** Two connection types to manage, but their responsibilities are cleanly separated. ESL is long-lived (one connection, many calls). mod_audio_stream is per-call (one WebSocket per active call, created on answer, closed on hangup).

**Example:**
```python
# Control plane — one persistent ESL connection
esl = ESLClient(host="127.0.0.1", port=8021)
await esl.connect()
await esl.subscribe("CHANNEL_ANSWER", "CHANNEL_HANGUP", "DTMF")

# On CHANNEL_ANSWER event, FreeSWITCH dialplan triggers mod_audio_stream
# which creates a WebSocket connection to our voice pipeline server

# Media plane — WebSocket server receives per-call connections
@app.websocket("/voice/{call_uuid}")
async def voice_handler(ws: WebSocket, call_uuid: str):
    session = session_store.get(call_uuid)
    await run_voice_pipeline(ws, session)
```

### Pattern 4: Event-Driven Call State (Not LLM-Driven)

**What:** Call state transitions (answered, held, transferred, hungup, compliance-blocked) are managed by a deterministic state machine in Python. The LLM controls conversation content and tool invocation decisions. The state machine controls call infrastructure transitions.

**When to use:** Always. Letting the LLM drive infrastructure state transitions (e.g., "LLM decides when to hang up") produces unpredictable behavior in production. The LLM can request a hangup, but the state machine executes it via ESL.

**Trade-offs:** More code than naive LLM-as-orchestrator; prevents a category of production failures where LLM hallucination or model degradation causes bad call outcomes.

**Example:**
```python
class CallStateMachine:
    states = ["dialing", "ringing", "answered", "processing", "transferring", "hungup"]

    async def on_esl_event(self, event: ESLEvent):
        if event.type == "CHANNEL_ANSWER":
            await self.transition("answered")
            await self.start_voice_pipeline()
        elif event.type == "CHANNEL_HANGUP":
            await self.transition("hungup")
            await self.cleanup_session()

    async def handle_tool_call(self, tool: str, args: dict):
        if tool == "hangup":
            # LLM requests hangup — state machine executes it
            await esl.execute("hangup", self.call_uuid)
        elif tool == "transfer":
            await self.transition("transferring")
            await esl.execute("transfer", args["destination"])
```

---

## Data Flow

### Outbound Call Flow

```
Agent tool call: call(destination="+14155551234", objective="...")
    │
    ▼
Telecom Abstraction Layer
    │ session_id = create_session(objective, context)
    │ jurisdiction = router.resolve("+14155551234")  → "us"
    ▼
Compliance Gateway (US plugin)
    │ consent_check(destination)   → PASS / BLOCK
    │ dnc_scrub(destination)       → PASS / BLOCK
    │ time_of_day_check(timezone)  → PASS / BLOCK
    │ select_did(attestation="A")  → did="+12125559876"
    │ audit_log(session_id, all checks, result)
    ▼
FreeSWITCH ESL (originate command)
    │ originate {session_uuid=...,compliance_cleared=true}
    │          sofia/gateway/sip_trunk/ +14155551234
    │          &playback(disclosure_audio.wav)
    ▼
FreeSWITCH dials via SIP Trunk
    │
    ▼ (CHANNEL_ANSWER event received)
Python ESL Event Handler
    │ session_store.update(uuid, state="answered")
    │ inject_disclosure_into_dialplan()  ← mandatory first utterance
    ▼
mod_audio_stream activated (WebSocket opens to voice pipeline)
    │
    ├──[audio in]──▶ VAD ──▶ STT (faster-whisper streaming)
    │                                │
    │                          partial transcript
    │                                │
    │                          LLM (streaming response)
    │                                │
    │                          TTS (Piper, sentence-at-a-time)
    │                                │
    └──[audio out]◀─────────── PCM chunks via WebSocket
```

### SMS Flow

```
Agent tool call: sms(destination="+14155551234", body="...")
    │
    ▼
Compliance Gateway (US plugin)
    │ 10DLC registration check (carrier approval)
    │ opt-out check
    │ consent_check (written consent for A2P)
    │ audit_log
    ▼
SMS Handler
    │
    ├─[SMPP path]──▶ SMPP connection to carrier SMSC
    │                    submit_sm PDU → delivery_sm receipt
    │
    └─[GSM path]───▶ gammu/kannel ──▶ GSM modem ──▶ SIM ──▶ carrier
```

### Agent-to-Agent WebRTC Flow

```
Agent A: call(destination="agent://agent-b-id", type="webrtc")
    │
    ▼
Router detects "agent://" scheme → no compliance gateway (no PSTN)
    │
    ▼
Janus WebRTC Gateway (via mod_janus or direct Janus API)
    │ create_room(session_id)
    │ add_participant(agent_a_rtp_endpoint)
    │ add_participant(agent_b_webrtc_endpoint)
    ▼
Direct peer audio — Opus codec, encrypted, no per-minute cost
```

### Call State Events

```
ESL Event Stream (TCP, persistent)
    │
    ├── CHANNEL_ORIGINATE  → session created, compliance cleared
    ├── CHANNEL_RINGING    → update session state
    ├── CHANNEL_ANSWER     → start voice pipeline WebSocket
    ├── DTMF               → pass to LLM as tool input event
    ├── CHANNEL_HANGUP     → stop pipeline, release DID, close session
    └── RECORD_STOP        → finalize transcript, persist audit record
```

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SIP Trunk | SIP REGISTER + INVITE via FreeSWITCH sofia profile | Single account; only external dependency |
| GSM Modem | gammu serial or kannel over HTTP | For anonymous international SMS/calls |
| National DNC Registry (US) | FCC SOR subscription; local DB sync nightly | Never do live lookups; sync to local Bloom filter |
| STIR/SHAKEN attestation | US DID provider with A-level attestation | Small pool of US DIDs with carrier relationship |
| HLR lookup (optional) | REST API to HLR service | For number intelligence at call request time |

### Internal Component Boundaries

| Boundary | Protocol | Notes |
|----------|----------|-------|
| Agent Runtime ↔ Telecom Abstraction Layer | Python function call / async await | Same process; session object passed by reference |
| Telecom Abstraction Layer ↔ Compliance Gateway | Python plugin interface (ComplianceGateway.check()) | Plugins loaded by jurisdiction code at call time |
| Compliance Gateway ↔ FreeSWITCH | ESL TCP (inbound mode, port 8021) | asyncio ESL client; Genesis or switchio library |
| FreeSWITCH ↔ Voice Pipeline | WebSocket (mod_audio_stream) | Per-call WebSocket; 16kHz PCM mono; Python ws server |
| Voice Pipeline ↔ STT | Python in-process | faster-whisper runs in same Python process or subprocess |
| Voice Pipeline ↔ TTS | Python in-process (or subprocess for Piper binary) | Piper has Python bindings; also runs as subprocess |
| FreeSWITCH ↔ Janus | HTTP long-poll (mod_janus) or Janus API | For WebRTC bridging |
| SMS Handler ↔ SMPP | SMPP over TCP (python-smpplib) | Persistent ESME bind; async receiver for delivery receipts |

---

## Build Order (Dependency-Respecting)

The components have hard dependencies that dictate order. You cannot build higher layers before the lower ones work.

```
Phase 1: FreeSWITCH foundation
│  FreeSWITCH install + configuration
│  ESL TCP connection from Python (Genesis/switchio)
│  Basic originate/hangup via ESL
│  SIP trunk registration verified
│  → Milestone: Python can make a raw SIP call
│
Phase 2: Voice pipeline
│  mod_audio_stream WebSocket bridge
│  faster-whisper STT receiving audio from FreeSWITCH
│  Piper/Kokoro TTS sending audio back to FreeSWITCH
│  Streaming (partial transcripts → LLM → sentence-chunk TTS)
│  → Milestone: Full voice loop works, <800ms round-trip
│
Phase 3: Telecom abstraction
│  Session state (Redis + PostgreSQL)
│  Number pool manager (checkout/release)
│  Call state machine (ESL events → state transitions)
│  Jurisdiction router (prefix → plugin lookup)
│  → Milestone: Session-aware calls with DID management
│
Phase 4: Compliance gateway
│  ComplianceGateway plugin interface
│  US compliance module (TCPA, DNC, time-of-day, disclosure)
│  Consent DB schema and query interface
│  Audit log (append-only)
│  → Milestone: Compliant US outbound calling
│
Phase 5: SMS channel
│  SMPP client (python-smpplib)
│  SMS compliance hooks (opt-out, 10DLC check)
│  GSM modem fallback (kannel/gammu)
│  → Milestone: Outbound + inbound SMS working
│
Phase 6: Agent-to-agent WebRTC
│  Janus WebRTC gateway setup
│  mod_janus FreeSWITCH integration
│  Agent addressing scheme (agent:// URI)
│  → Milestone: Two agents can communicate without PSTN
│
Phase 7: CLI + onboarding
│  `holler init` (generate config, verify FreeSWITCH, check trunk)
│  `holler call` (invoke tool from CLI for testing)
│  `holler status` (health check all components)
│  → Milestone: Four-command install-to-first-call path
```

**Rationale for this order:**
- FreeSWITCH must be proven before the voice pipeline — there is no audio without the softswitch routing it.
- The voice pipeline must be proven before session abstraction — latency must be validated at the protocol level before adding Python layers.
- Session abstraction must exist before compliance — the compliance gateway needs session context (destination, consent reference, jurisdiction).
- Compliance must be proven before declaring the system "production-ready" — it is the call path, not an afterthought.
- SMS is parallel to voice in the architecture but depends on the same session store and compliance gateway, so it fits naturally after Phase 4.
- WebRTC (agent-to-agent) is architecturally independent of the PSTN path and can be parallelized once FreeSWITCH is solid.
- CLI is the last thing — it wraps everything else; building it early produces a fragile wrapper around unfinished components.

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-4 concurrent calls | Single machine, single GPU. All components co-located. FreeSWITCH + Python on same host. |
| 5-16 concurrent calls | Dedicate GPU to STT; run TTS on separate CPU threads. FreeSWITCH can handle this without changes. Consider Redis for session state even single-node (for durability). |
| 16-64 concurrent calls | Multi-GPU. STT worker pool. TTS worker pool. FreeSWITCH cluster (2-3 nodes). PostgreSQL for compliance DB becomes important. |
| 64+ concurrent calls | Separate media servers (multiple FreeSWITCH). Compliance gateway as microservice. STT cluster. Number pool manager as dedicated service with distributed locking. |

### Scaling Priorities

1. **First bottleneck: GPU for STT.** faster-whisper is the latency-critical path. A single RTX 3060 handles ~4 concurrent calls at real-time factor < 0.1x. Add GPUs before adding other capacity.
2. **Second bottleneck: number pool contention.** At high concurrency, DID checkout/release becomes a hotspot. Use database row-level locking with timeout, not application-level locks. Redis SET with NX flag works well for pool management.

---

## Anti-Patterns

### Anti-Pattern 1: Compliance Gateway as Optional Middleware

**What people do:** Add compliance checks as `if compliance_enabled: check()` flags, or as optional middleware the caller can skip for "testing."

**Why it's wrong:** A bypass path is legally equivalent to no compliance at all. If the code path exists, a misconfiguration will use it. In TCPA litigation, the existence of a bypass path undermines the "systematic compliance" defense.

**Do this instead:** Make the compliance gateway unconditional in the call path. The gateway can return PASS immediately in test mode, but the gateway object is always instantiated and always called.

### Anti-Pattern 2: LLM Driving Call Infrastructure State

**What people do:** Give the LLM tools like `transition_to_transfer_state()` or let the LLM decide when to hang up by calling `hangup()` directly.

**Why it's wrong:** LLMs hallucinate. A production voice system where the LLM can decide to hang up, transfer, or enter hold states based on conversational context (without a deterministic check) will eventually do the wrong thing at the wrong moment. At scale, this produces real calls with real humans experiencing bad outcomes.

**Do this instead:** The LLM emits tool calls (`request_hangup`, `request_transfer`). A deterministic state machine in Python evaluates whether the request is valid in the current state and executes it via ESL. The LLM drives conversation; Python drives infrastructure.

### Anti-Pattern 3: Sequential (Non-Streaming) Voice Pipeline

**What people do:** Wait for STT to complete the full utterance, then call the LLM, then wait for the full response, then call TTS, then play audio.

**Why it's wrong:** Sequential pipeline produces 2-4 second response delays. At 2 seconds, human callers disengage. At 4 seconds, callers assume the system crashed and hang up or start talking over the response.

**Do this instead:** Stream at every stage. STT sends partial transcripts. LLM generates before full utterance arrives. TTS begins synthesis on first sentence fragment while LLM generates the second. Total latency collapses from 2-4s to 300-800ms.

### Anti-Pattern 4: Per-Agent Phone Number Allocation

**What people do:** Assign a dedicated phone number to each agent instance or each long-running agent session.

**Why it's wrong:** Phone numbers are $0.50-1.00/month. At any scale, per-agent allocation bloats number inventory, creates orphaned numbers, and accumulates calling reputation on numbers that may have been used for unrelated purposes. It also makes it harder to rotate numbers (a carrier reputation management necessity).

**Do this instead:** Pooled numbers. Each call checks out a DID at origination and releases it at hangup. Identity travels with the session context, not the number. The pool size is determined by peak concurrent calls, not total agent count.

### Anti-Pattern 5: Direct Python-to-SIP Without a Softswitch

**What people do:** Use a Python SIP library (pjsua2, linphone bindings) to make calls directly without FreeSWITCH.

**Why it's wrong:** Python SIP libraries are fragile, lack production codec support, don't handle PSTN edge cases (DTMF, hold, transfer, call waiting, codec negotiation with legacy equipment), and make it impossible to leverage FreeSWITCH's mature RTP handling and recording infrastructure.

**Do this instead:** FreeSWITCH handles all SIP/RTP complexity. Python communicates with FreeSWITCH via ESL (clean, stable, production-proven API). Python's job is orchestration, not media handling.

---

## Sources

- FreeSWITCH Event Socket Library: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Client-and-Developer-Interfaces/Event-Socket-Library/
- mod_janus FreeSWITCH module: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Modules/mod_janus_20709557/
- mod_audio_stream + AI voice agent implementation: https://www.cyberpunk.tools/jekyll/update/2025/11/18/add-ai-voice-agent-to-freeswitch.html
- mod_audio_stream module (amigniter): https://github.com/amigniter/mod_audio_stream
- Genesis (asyncio ESL): https://github.com/Otoru/Genesis
- switchio (asyncio FreeSWITCH cluster control): https://github.com/friends-of-freeswitch/switchio
- greenswitch (production ESL, Gevent): https://github.com/EvoluxBR/greenswitch
- faster-whisper streaming architecture: https://github.com/SYSTRAN/faster-whisper
- whisper_streaming (realtime wrapper): https://github.com/ufal/whisper_streaming
- LiveKit voice agent architecture (streaming pipeline patterns): https://livekit.com/blog/voice-agent-architecture-stt-llm-tts-pipelines-explained
- Janus + FreeSWITCH integration: https://github.com/giavac/janus_freeswitch_integration
- Voice agent state machine patterns: https://voxam.hashnode.dev/stop-letting-llm-drive-voice-agent-state-machine
- python-smpplib: https://github.com/python-smpplib/python-smpplib
- Piper TTS + LiveKit low-latency implementation: https://medium.com/@mail2chasif/livekit-piper-tts-building-a-low-latency-local-voice-agent-with-real-time-latency-tracking-92a1008416e4
- Project concept brief (primary source): `/Users/paul/paul/brains/docs/drafts/2026-03-24-agentic-telecom-concept-brief.html`

---
*Architecture research for: self-hosted agentic telecom infrastructure (Holler)*
*Researched: 2026-03-24*

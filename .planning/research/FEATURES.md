# Feature Research

**Domain:** Self-hosted agentic telecom infrastructure (voice + SMS for AI agents)
**Researched:** 2026-03-24
**Confidence:** MEDIUM-HIGH (commercial platforms well-documented; open-source agentic-telecom niche is emerging)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that developers and operators assume exist. Missing these = the platform feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Inbound + outbound voice calls | Every phone platform does this; missing either kills 50% of use cases | MEDIUM | FreeSWITCH handles both natively via SIP dialplan |
| SIP trunk connectivity (PSTN) | The only way to reach actual phone numbers; assumed as baseline | LOW | Standard SIP/TLS + RTP; FreeSWITCH has first-class support |
| STT + TTS pipeline (local) | Without speech understanding and synthesis, there is no voice agent | HIGH | faster-whisper for STT; Piper/Kokoro for TTS; streaming required for latency budget |
| Sub-800ms round-trip latency | Natural conversation requires <1s response; >1.5s feels broken | HIGH | Requires streaming STT, streaming LLM, streaming TTS, and local inference |
| Turn detection / endpointing | Without knowing when the user stops speaking, conversation is incoherent | MEDIUM | VAD + silence detection as baseline; transformer-based semantic turn detection as upgrade |
| Barge-in / interruption handling | Users interrupt; ignoring it feels robotic and frustrating | MEDIUM | Must stop TTS playback mid-stream and reset context on interruption |
| Phone number management (DID pool) | Agent needs a "from" number to make calls; number allocation is assumed | MEDIUM | Pool model: checkout/release per-session rather than per-agent static allocation |
| Session state tracking | Conversation context must persist for the life of a call | MEDIUM | Maps call-leg ID to conversation history, turn count, tool call state |
| Call recording | Operators assume recordings exist for quality, compliance, replay | MEDIUM | Audio capture at media layer; store as WAV/MP3; accessible via API |
| Basic transcription | Raw audio alone is not useful; developers expect searchable text | MEDIUM | Whisper model produces transcripts as a side-effect of STT; persist alongside recording |
| Inbound call handling (answer, route) | IVR is table stakes; agents need to answer and route calls | LOW | FreeSWITCH dialplan handles routing; agent gets audio stream |
| Outbound call initiation via API / tool call | Core value: agent invokes a call as a tool | LOW | FreeSWITCH ESL or REST originate API; 1-line invocation |
| SMS send/receive | Text messaging is a parallel channel; often expected alongside voice | MEDIUM | SMPP protocol or GSM modem (gammu/kannel/jasmin); separate from voice pipeline |
| Webhooks / event callbacks | Developers need call events (answered, ended, transcript ready) | LOW | Standard HTTP POST on call events; async delivery |
| Graceful call termination | Hangup on completion, error, or agent instruction | LOW | FreeSWITCH hangup cause codes; session cleanup |
| Basic monitoring / logging | Operators need to see what happened; missing = flying blind | MEDIUM | Call logs, latency metrics, error rates; structured JSON logs |

### Differentiators (Competitive Advantage)

Features that set Holler apart. These are where the project competes on its stated value proposition: permissionless, self-hosted, agent-native infrastructure.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Zero vendor accounts (permissionless core) | No Twilio, no ElevenLabs, no OpenAI API required — total data sovereignty | HIGH | Entire stack local: FreeSWITCH + faster-whisper + Piper/Kokoro + local LLM; SIP trunk is the only external dependency |
| Compliance as mandatory call-path gateway | Structurally impossible to place a non-compliant call; legal defense posture | HIGH | Country module plugged into the call path before PSTN egress; not opt-in middleware |
| Country module plugin system | Community-contributed jurisdiction compliance without forking core | HIGH | Plugin interface with documented contract; `countries/us/`, `countries/uk/`, `countries/_template/`; TCPA + STIR/SHAKEN enforced for US |
| Numbers as ephemeral pool | DIDs allocated per-interaction and released; lower cost, better privacy | MEDIUM | Pool manager with checkout/release lifecycle; identity travels with session context, not with number |
| Agent-to-agent WebRTC mesh | Agents call each other directly, no PSTN, no regulation, near-zero cost | HIGH | Janus WebRTC gateway; SDP negotiation between agent endpoints; zero carrier involvement |
| Local-first inference (STT + TTS) | No per-minute API costs, no data leaving infrastructure, lower latency | HIGH | faster-whisper + Whisper.cpp for STT; Piper/Kokoro/Orpheus for TTS; GPU required for concurrent calls |
| Tool-use protocol agent interface | Treats phone calls as tool invocations — same abstraction as any other agent tool | MEDIUM | Python SDK emitting `call`, `sms`, `transfer` actions; LLM-agnostic |
| Four-command onboarding | `pip install holler` → `holler init` → configure trunk → `holler call` | MEDIUM | CLI scaffolding, sane defaults, single config file; opinionated but escapable |
| Consent / opt-out state machine in call path | Enforced, not advisory; cannot be bypassed in the dialplan | HIGH | DNC list check, consent verification, opt-out DTMF/spoken capture; mandatory for US module |
| STIR/SHAKEN attestation (US) | Caller ID authentication; without it, calls get flagged or blocked by carriers | HIGH | Requires certificate authority integration; A/B/C attestation based on number ownership |
| Multi-GPU concurrent call scaling | Local inference scales horizontally across GPUs for high-volume deployments | HIGH | Session dispatcher routes to least-loaded GPU worker; 16-64 concurrent calls on multi-GPU |
| Jurisdiction router | Call dispatch auto-selects the correct country module based on dialed number | MEDIUM | E.164 prefix matching → country module lookup → compliance gateway injection |
| Live transcription streaming | Real-time transcript available during call (not just post-call) | MEDIUM | Whisper streaming mode; transcript events published to session bus |
| Post-call analytics (structured) | Machine-readable call outcomes, sentiment, tool-call trace | MEDIUM | JSON call summary: duration, transcript, tool calls made, compliance checks passed |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem valuable but introduce structural problems, scope creep, or undermine Holler's design principles.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Cloud-hosted SaaS option | "Just host it for me" reduces friction | Contradicts permissionless core; creates vendor dependency; requires carrier licenses; becomes Twilio | Document one-click self-deploy to bare metal / home server; Docker Compose first |
| Built-in LLM (bundled language model) | Convenience; one-stop shop | Forces model choice; huge binary; obsoletes quickly; out of scope of telecom infra | Tool-use protocol is LLM-agnostic; local Ollama or any OpenAI-compatible endpoint |
| No-code visual flow builder | Appeal to non-developers | Adds GUI surface area; diverges from CLI/API philosophy; tools like Synthflow already own this space | Rich Python SDK + documented patterns; agent logic stays in agent code, not in a GUI |
| Per-agent static number assignment | "My agent has its own phone number" feels intuitive | Wastes DIDs; increases cost; breaks multi-modal identity model | Ephemeral pool + session context carries identity; caller sees consistent caller ID from pool |
| WhatsApp / RCS integration (v1) | Rich messaging channels are valuable | Requires Business API accounts (WhatsApp); regulatory maze; distinct from telecom infra | SMPP SMS as v1; WhatsApp/RCS as community-contributed channel modules in v2+ |
| Built-in CRM / contact management | "Store my contacts here" reduces external dependencies | Turns telecom infra into a data store; out of scope; creates GDPR/CCPA surface area | Tool-use protocol lets agent query its own CRM as a tool call; Holler is stateless about contacts |
| Automated outbound dialing campaigns | High-volume dialer is a natural extension | TCPA/DNC exposure; easily misused; legal risk without consent verification | Compliance gateway enforces consent pre-call; campaign orchestration is the agent's job, not Holler's |
| Voice cloning / custom voice models | Branded voice is a differentiator for commercial platforms | High compute cost; ethical/legal risk (deepfake adjacent); out of scope | Piper/Kokoro/Orpheus cover quality range; voice selection is config, not a Holler feature |
| Carrier / number provisioning API | "Buy a number from Holler" is convenient | Requires carrier relationships and telecom licenses; turns project into a telco | SIP trunk is the carrier interface; operator provisions DIDs from their trunk provider |
| Real-time dashboard GUI | Operators want to watch calls live | Adds significant frontend scope; not agent-native; operational monitoring is better via metrics | Structured JSON logs + Prometheus metrics + Grafana; agents consume observability via tool calls |

---

## Feature Dependencies

```
[PSTN Connectivity — SIP Trunk]
    └──required by──> [Outbound Voice Call]
    └──required by──> [Inbound Call Handling]
    └──required by──> [STIR/SHAKEN Attestation]

[FreeSWITCH Softswitch]
    └──required by──> [Outbound Voice Call]
    └──required by──> [Inbound Call Handling]
    └──required by──> [Call Recording]
    └──required by──> [Call Transfer]

[STT Pipeline — faster-whisper]
    └──required by──> [Live Transcription]
    └──required by──> [Turn Detection / Endpointing]
    └──required by──> [Post-Call Transcript]
    └──required by──> [Voice Conversation Loop]

[TTS Pipeline — Piper/Kokoro]
    └──required by──> [Voice Conversation Loop]
    └──required by──> [Barge-In / Interruption Handling]

[Voice Conversation Loop]  (STT → LLM → TTS)
    └──required by──> [Sub-800ms Latency Target]
    └──required by──> [Agent Tool-Use Interface]

[Session State Tracking]
    └──required by──> [Multi-Turn Conversation]
    └──required by──> [Consent/Opt-Out State Machine]
    └──required by──> [Post-Call Analytics]
    └──required by──> [Agent-to-Agent Handoff]

[DID Number Pool Manager]
    └──required by──> [Ephemeral Number Allocation]
    └──required by──> [Outbound Call Initiation]

[Compliance Gateway (Country Module)]
    └──required by──> [TCPA Enforcement — US]
    └──required by──> [STIR/SHAKEN — US]
    └──required by──> [DNC Check — US]
    └──required by──> [Consent/Opt-Out State Machine]
    └──required by──> [Time-of-Day Restrictions — US]
    └──is populated by──> [Jurisdiction Router]

[Jurisdiction Router]
    └──required by──> [Multi-country Compliance]
    └──depends on──> [Country Module Plugin System]

[Janus WebRTC Gateway]
    └──required by──> [Agent-to-Agent Direct Communication]

[SMPP / GSM Modem Layer]
    └──required by──> [SMS Send/Receive]
    └──separate from──> [Voice Pipeline]  (independent subsystem)

[STT Pipeline] ──enhances──> [Barge-In / Interruption Handling]
[Live Transcription] ──enhances──> [Post-Call Analytics]
[Call Recording] ──enhances──> [Post-Call Transcript]
[Session State Tracking] ──enhances──> [Warm Transfer with Context]
```

### Dependency Notes

- **Voice Conversation Loop requires both STT and TTS**: The loop cannot function if either pipeline is absent; both must be operational before any voice agent test is meaningful.
- **Compliance Gateway must precede PSTN egress**: Architecturally enforced — the gateway is in the call path, not optional middleware. Country modules must be at least stubbed before calls can legally egress.
- **DID Pool required before outbound calls**: An agent cannot make a call without a source number; pool manager must initialize before the call API is usable.
- **Session State underpins compliance**: The consent/opt-out state machine reads and writes session state; these two components are tightly coupled.
- **Janus is independent**: Agent-to-agent WebRTC is a parallel path, not a dependency of the PSTN voice pipeline. Can be built and tested independently.
- **SMS is fully independent**: SMPP/GSM modem layer shares no components with the voice pipeline; it can be shipped as a separate milestone without blocking voice functionality.

---

## MVP Definition

### Launch With (v1)

Minimum to validate the core thesis: "An AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation."

- [ ] **Outbound voice call via tool invocation** — proves the primary thesis; agent emits `call` action, phone rings
- [ ] **Local STT + TTS pipeline** — faster-whisper + Piper; no cloud dependencies; sub-800ms loop
- [ ] **FreeSWITCH softswitch with SIP trunk** — PSTN connectivity; RTP media handling
- [ ] **DID pool manager (checkout/release)** — agent can make a call without static number assignment
- [ ] **Session state tracking** — conversation context persists for call lifetime
- [ ] **US compliance gateway (TCPA + STIR/SHAKEN + DNC)** — legally required for US outbound; proves country module pattern works
- [ ] **Consent / opt-out state machine** — mandatory for TCPA compliance; enforced in call path
- [ ] **Country module plugin interface + template** — proves extensibility; community can add countries
- [ ] **Call recording + post-call transcript** — operators need audit trail; compliance requires it
- [ ] **Four-command onboarding** — install, init, configure trunk, call; validates developer experience
- [ ] **SMS send/receive via SMPP** — secondary channel but in active requirements; SMPP is simpler than voice

### Add After Validation (v1.x)

Features to add once core voice loop is proven and one real call has been made.

- [ ] **Agent-to-agent WebRTC** — add Janus gateway after PSTN path proven; different user population (agent mesh)
- [ ] **Inbound call handling** — answer and route inbound; natural extension once outbound works
- [ ] **Live transcription streaming** — real-time transcript events; needed for agent decision-making mid-call
- [ ] **Jurisdiction router** — E.164 prefix to country module dispatch; needed when second country module exists
- [ ] **Warm call transfer (AI to human)** — needed for escalation workflows; depends on multi-agent session handoff
- [ ] **Webhooks / event API** — HTTP callbacks for call events; developers need this for integration
- [ ] **Structured monitoring / metrics** — Prometheus + structured logs; needed for production operations

### Future Consideration (v2+)

Features to defer until project has users and validated direction.

- [ ] **UK country module** — community-contributed; template + US module prove the pattern first
- [ ] **Multi-GPU call scaling** — relevant only when single-GPU concurrency (4-8 calls) is saturated
- [ ] **Post-call analytics (structured)** — JSON call summaries with tool-call trace; valuable but not MVP
- [ ] **Voice cloning / voice selection** — Piper/Kokoro defaults are sufficient for v1; voice customization is v2
- [ ] **GSM modem fallback for SMS** — SMPP via trunk is v1; modem as backup is v2
- [ ] **WhatsApp / RCS channel module** — distinct channel; post-MVP community contribution

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Outbound voice call via tool invocation | HIGH | MEDIUM | P1 |
| Local STT + TTS pipeline | HIGH | HIGH | P1 |
| FreeSWITCH + SIP trunk connectivity | HIGH | MEDIUM | P1 |
| Sub-800ms latency (streaming pipeline) | HIGH | HIGH | P1 |
| DID pool manager | HIGH | MEDIUM | P1 |
| Session state tracking | HIGH | MEDIUM | P1 |
| US compliance gateway | HIGH | HIGH | P1 |
| Call recording + transcript | HIGH | MEDIUM | P1 |
| Four-command onboarding / CLI | HIGH | MEDIUM | P1 |
| SMS via SMPP | MEDIUM | MEDIUM | P1 |
| Country module plugin interface | HIGH | MEDIUM | P1 |
| Turn detection / barge-in | HIGH | MEDIUM | P1 |
| Agent-to-agent WebRTC | HIGH | HIGH | P2 |
| Inbound call handling | HIGH | LOW | P2 |
| Live transcription streaming | MEDIUM | MEDIUM | P2 |
| Webhooks / event callbacks | MEDIUM | LOW | P2 |
| Jurisdiction router | MEDIUM | LOW | P2 |
| Warm call transfer | MEDIUM | MEDIUM | P2 |
| Structured monitoring / metrics | MEDIUM | MEDIUM | P2 |
| Post-call analytics (structured) | MEDIUM | MEDIUM | P3 |
| Multi-GPU scaling | LOW | HIGH | P3 |
| UK / additional country modules | MEDIUM | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch (v1 MVP)
- P2: Should have, add after core is proven
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

Commercial platforms compared: Vapi, Retell AI, Bland AI, Synthflow AI.
Open-source compared: LiveKit Agents, Pipecat, jambonz, Bolna.

| Feature | Vapi | Retell AI | Bland AI | Jambonz | LiveKit Agents | Holler Approach |
|---------|------|-----------|----------|---------|----------------|-----------------|
| Outbound voice call | Yes | Yes | Yes | Yes | Yes | Yes — tool invocation primitive |
| Inbound call handling | Yes | Yes | Yes | Yes | Yes | Yes — in v1.x |
| Local STT | No (cloud providers) | No (cloud) | No (cloud) | Yes (BYO) | Yes (BYO) | Yes — faster-whisper, no cloud |
| Local TTS | No (cloud providers) | No (cloud) | No (cloud) | Yes (BYO) | Yes (BYO) | Yes — Piper/Kokoro, no cloud |
| SIP trunk connectivity | Yes | Yes | Yes | Yes | Yes | Yes — core |
| Agent tool-use interface | Yes (function calling) | Yes | Yes (pathways) | No (dialplan) | Yes (MCP) | Yes — LLM-agnostic tool-use |
| Multi-agent / squads | Yes (Squads) | Limited | Yes (pathways) | No | Yes (handoffs) | Yes — via agent mesh + WebRTC |
| Agent-to-agent (no PSTN) | No | No | No | No | Yes (WebRTC) | Yes — WebRTC mesh; key differentiator |
| Call recording | Yes | Yes | Yes | Yes | Yes | Yes — P1 |
| Live transcription | Yes | Yes | Yes | Yes | Yes | Yes — P2 |
| Compliance (TCPA/STIR) | Partial | Yes (verified numbers) | Partial | No native | No native | Yes — mandatory in-path gateway |
| DNC enforcement | No native | Partial | Partial | No | No | Yes — US compliance module |
| Number pool mgmt | Yes | Yes | Yes | Manual | Manual | Yes — ephemeral checkout/release |
| SMS | No native | No native | Yes | No | No | Yes — SMPP/modem |
| Self-hosted / no vendor | No | No | No | Yes | Yes | Yes — core design |
| Zero vendor accounts | No | No | No | No | No | Yes — key differentiator |
| Country module system | No | No | No | No | No | Yes — unique |
| Latency target | <600ms | ~780ms | Not stated | <500ms | Variable | <800ms full loop |
| Pricing | $0.05/min + providers | $0.07/min | $0.09/min | Free + infra | Free + infra | Free (infra cost only) |
| Open source | No | No | No | Yes (MIT) | Yes (Apache 2.0) | Yes (Apache 2.0) |

**Key gaps this analysis reveals:**

1. No existing platform (commercial or open-source) enforces compliance in-path as a structural guarantee. All compliance in the market is advisory or bolt-on.
2. No commercial platform is self-hosted without vendor accounts. LiveKit/jambonz are self-hosted but still assume cloud STT/TTS.
3. No platform treats agent-to-agent communication as a first-class primitive separate from PSTN.
4. The "no vendor accounts" constraint is completely unoccupied in the commercial market — this is Holler's clearest differentiator.

---

## Sources

**Commercial AI voice platforms (features observed 2026-03):**
- [Vapi Documentation — Introduction](https://docs.vapi.ai/quickstart/introduction) (MEDIUM confidence — intro page only)
- [Vapi Review 2026 — Coval](https://www.coval.dev/blog/vapi-review-2026-is-this-voice-ai-platform-right-for-your-project) (MEDIUM confidence — third-party review)
- [Retell AI vs Bland AI Comparison — Retell AI](https://www.retellai.com/blog/retell-ai-vs-bland-ai-choose-the-right-voice-agent-for-your-business) (MEDIUM confidence — vendor-authored comparison)
- [Synthflow AI Review 2025 — Skywork AI](https://skywork.ai/skypage/en/Synthflow-AI-In-Depth-Review-(2025)-The-Ultimate-Guide-to-AI-Voice-Agents/1976166557443747840) (MEDIUM confidence)
- [Top 10 AI Voice Agent Platforms Guide 2026 — Vellum AI](https://vellum.ai/blog/ai-voice-agent-platforms-guide) (MEDIUM confidence)

**Open-source platforms:**
- [LiveKit Agents — GitHub](https://github.com/livekit/agents) (HIGH confidence — official repo)
- [Pipecat — GitHub](https://github.com/pipecat-ai/pipecat) (HIGH confidence — official repo)
- [Jambonz — official site](https://www.jambonz.org/) (MEDIUM confidence — marketing page)
- [Bolna — GitHub](https://github.com/bolna-ai/bolna) (MEDIUM confidence — official repo)

**Compliance research:**
- [FCC confirms TCPA applies to AI voice](https://www.fcc.gov/document/fcc-confirms-tcpa-applies-ai-technologies-generate-human-voices) (HIGH confidence — official FCC)
- [AI Voice TCPA Compliance Guide — Henson Legal](https://www.henson-legal.com/newsroom/ai-voice-tcpa-compliance-guide) (MEDIUM confidence — legal analysis)
- [TCPA Compliance 2025 — SecurePrivacy](https://secureprivacy.ai/blog/telephone-consumer-protection-act-compliance-tcpa-2025-full-guide) (MEDIUM confidence)

**Voice pipeline / turn detection:**
- [Turn Detection for Voice Agents — LiveKit Blog](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection) (HIGH confidence — technical blog)
- [Barge-In Detection Optimization 2025 — SparkCo](https://sparkco.ai/blog/optimizing-voice-agent-barge-in-detection-for-2025) (MEDIUM confidence)
- [Endpointing Guide — AssemblyAI](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent) (HIGH confidence — technical)

**Number management:**
- [Twilio Phone Number Pool Management](https://www.twilio.com/docs/proxy/understanding-phone-number-management) (HIGH confidence — official docs)

**Observability:**
- [Voice Agent Observability — Hamming AI](https://hamming.ai/blog/voice-agent-observability-voice-observability) (MEDIUM confidence)
- [Production Monitoring for Voice Agents — Hamming AI](https://hamming.ai/blog/monitor-voice-agents-in-production) (MEDIUM confidence)

---
*Feature research for: self-hosted agentic telecom infrastructure (voice + SMS for AI agents)*
*Researched: 2026-03-24*

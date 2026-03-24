# Domain Pitfalls: Agentic Telecom / AI Voice Infrastructure

**Domain:** Self-hosted AI voice + SMS infrastructure with compliance enforcement
**Researched:** 2026-03-24
**Overall confidence:** MEDIUM-HIGH (verified across multiple sources; some items FreeSWITCH-specific from docs, others from community/production reports)

---

## Critical Pitfalls

Mistakes that cause rewrites, legal liability, or hard failures in production.

---

### Pitfall 1: Treating 8 kHz Telephony Audio as a First-Class Input

**What goes wrong:** PSTN delivers audio at 8 kHz (G.711 µ-law/a-law). Whisper and faster-whisper expect 16 kHz. If you pipe telephony audio straight into the STT model without resampling, you get garbage transcripts — random words, high WER, or silent failures depending on implementation.

**Why it happens:** Developers test with microphone recordings (44.1 kHz or 16 kHz) and ship. The codec negotiation with FreeSWITCH defaults to PCMU/PCMA at 8 kHz. The mismatch goes undetected until a call comes in from an actual PSTN endpoint.

**Consequences:** STT accuracy degrades to 6-10% WER on the best day; in practice the feature extractor will either resample automatically (introducing artifacts) or silently produce corrupted output. The voice pipeline appears to work in dev but fails in production PSTN calls.

**Prevention:**
- Explicitly configure FreeSWITCH to transcode to 16 kHz (L16 or OPUS wideband) before handing audio to the STT pipeline.
- Or: accept 8 kHz and resample in the pipeline explicitly (SoX or scipy) — log the resample step so it is visible.
- Never skip a codec negotiation test against a real SIP trunk before claiming the pipeline works.

**Detection:** WER suddenly high on PSTN calls but normal on recorded tests. Check FreeSWITCH `sofia status profile` to confirm negotiated codec.

**Phase:** Voice Pipeline (Phase 1 or 2).

---

### Pitfall 2: Latency Budget Blown Before a Single Byte Reaches the LLM

**What goes wrong:** The 800ms round-trip target is consumed before the LLM produces its first token. Typical distribution: VAD delay (50-150ms) + STT (200-400ms on non-streaming Whisper) + network hop to LLM (50-200ms) = budget exhausted before TTS synthesis even starts.

**Why it happens:** Each component is optimized in isolation. Integration testing only measures the happy path under light load. Streaming is added as an afterthought rather than the design starting point.

**Consequences:** Conversations feel robotic, users hang up. Perceived latency over 300ms breaks immersion; over 1.5s causes abandonment.

**Prevention:**
- Design streaming end-to-end from the start: streaming VAD → streaming STT (whisper_streaming or silero-based) → streaming LLM token output → sentence-boundary TTS trigger.
- Never batch; pipeline each audio chunk. faster-whisper supports streaming segments — use them.
- Instrument the pipeline with per-stage timing from day one. Set per-stage budgets: VAD < 50ms, STT first segment < 200ms, LLM first token < 300ms, TTS first audio chunk < 100ms.
- On local LLM: use quantized models (4-bit GGUF or CTranslate2 int8). The RTX 3060 mentioned in constraints will bottleneck on unquantized 7B+ models.

**Detection:** End-to-end latency logging from call-accept event to first TTS audio byte sent. If any stage shows p95 > half its budget, fix it before moving on.

**Phase:** Voice Pipeline foundation (Phase 1). Revisit at each milestone.

---

### Pitfall 3: FreeSWITCH B2BUA Misunderstood as SIP Proxy

**What goes wrong:** FreeSWITCH is a Back-to-Back User Agent (B2BUA), not a SIP proxy. It parses, terminates, and re-originates every SIP message. Teams that come from Kamailio/OpenSIPS backgrounds try to use it as a transparent proxy — forwarding SIP registrations, passing calls through unchanged — and hit inexplicable failures.

**Why it happens:** The distinction isn't obvious until calls start failing. Asterisk developers may also misapply Asterisk mental models.

**Consequences:** Registration forwarding fails silently. Call routing behaves unexpectedly because FreeSWITCH re-writes SIP headers. Debugging is hard because the problem is architectural, not configurational.

**Prevention:**
- Document the B2BUA constraint explicitly for every contributor.
- Route all calls through FreeSWITCH's dialplan — never try to pass them through.
- Use `mod_sofia` for SIP profiles and understand that each profile is an independent SIP UA.

**Detection:** Calls that work in isolation fail when chained. SIP traces show header rewriting. `fs_cli -x "sofia status"` shows unexpected endpoint state.

**Phase:** FreeSWITCH integration (Phase 1 or 2).

---

### Pitfall 4: TCPA Compliance Treated as a Feature, Not an Invariant

**What goes wrong:** The compliance gateway is implemented as optional middleware that can be bypassed — "we'll add compliance after the MVP works." An agent makes a single outbound call to a number on the National DNC Registry without consent. TCPA fines: $500-$1,500 per call. Class action exposure: $925M+ verdicts on record.

**Why it happens:** Compliance feels like plumbing, not product. It slows down early demos. The FCC's February 2024 ruling confirming AI-generated voices fall under TCPA is recent enough that many developers don't know about it.

**Consequences:** Legal liability from day one of any real usage. The architecture states "compliance as mandatory call-path gateway" — if this is not enforced structurally (i.e., calls cannot physically route without passing the compliance module), it will be violated.

**New in 2025:**
- FCC April 11, 2025: expanded opt-out keywords (STOP, QUIT, CANCEL, UNSUBSCRIBE) must be honored within 10 business days. Opt-out processing is now mandatory, not best-effort.
- California AB 2905 (January 2025): every AI interaction must disclose AI use upfront. $500 fine per undisclosed call.
- Texas SB 140 (September 2024): mandatory AI disclosure within first 30 seconds. $1,000-$10,000 per violation.
- FCC September 2025: providers must use their own SPC token for STIR/SHAKEN — outsourcing attestation decisions is no longer allowed.

**Prevention:**
- Make the compliance gateway the only exit path for outbound calls in the dial plan. There is no "bypass" mode. Tests run against a compliance stub, not a bypass.
- DNC check must be synchronous and atomic with call initiation — not a pre-flight check that can be skipped.
- Consent state machine must be enforced in the call path, not the application layer.
- AI disclosure must be the first utterance in every call, hardcoded in the TTS pipeline, not configurable by the caller.

**Detection:** Any code path that can originate a PSTN call without calling `compliance.check()` is a bug. Add a static analysis lint rule. Integration tests must simulate DNC-listed numbers and verify rejection.

**Phase:** Compliance gateway (Phase 2 or 3). Must not be deferred past first outbound call capability.

---

### Pitfall 5: NAT Traversal Not Solved for Both SIP and WebRTC Simultaneously

**What goes wrong:** SIP and WebRTC have separate NAT traversal requirements. Solving one doesn't solve the other. NAT problems cause 80% of one-way audio failures in SIP, and 80% of WebRTC connectivity problems originate from network configuration.

**Why it happens:** Developers test in a flat network (all on same LAN or public IPs). NAT traversal is only discovered when deploying to a real network. SIP ALG — a "feature" on most consumer and enterprise routers — rewrites SIP headers and causes registration and in-call failures that are extremely hard to diagnose.

**Consequences:** One-way audio (the most reported VoIP bug). Call connects, signaling works, but no voice heard. Can manifest only on certain network topologies.

**Prevention:**
- For FreeSWITCH SIP: set `ext-rtp-ip` and `ext-sip-ip` explicitly in `sofia.conf.xml`. Never rely on autodiscovery in production.
- SIP ALG: document in the quickstart that SIP ALG must be disabled on any router between FreeSWITCH and the SIP trunk. This is the single most common one-way audio fix.
- For WebRTC (Janus): deploy a TURN server (coturn) as a first-class requirement, not an optional component. Approximately 15-20% of real-world connections require TURN relaying. Without it, agent-to-agent WebRTC on different networks will randomly fail.
- RTP port range: configure `rtp-start-port` and `rtp-end-port` explicitly in `switch.conf.xml`. Open the full range (default 16384-32768) in firewall rules.
- Docker note: Docker does not support forwarding large port ranges — port mapping 16384-32768 will freeze the host. Use `--network=host` for FreeSWITCH in Docker, or assign a smaller RTP range with explicit firewall pass-through.

**Detection:** Wireshark/tcpdump on media port range. One-way audio = NAT/firewall. No audio = TURN missing. Call drops at ICE negotiation = TURN authentication failure.

**Phase:** Infrastructure setup (Phase 1). Fix before any call quality work.

---

### Pitfall 6: STIR/SHAKEN Certificate Management Ignored

**What goes wrong:** Self-hosted VoIP operators are now required (FCC September 2025) to obtain their own SPC token and certificate from an authorized STI-CA and sign calls themselves. Many self-hosted deployments use their SIP trunk provider's attestation, which was valid until September 2025 — it is no longer allowed as a substitute.

**Why it happens:** STIR/SHAKEN is perceived as a carrier problem. It isn't — it is now mandatory for providers making outbound calls, even via a SIP trunk.

**Consequences:** Calls from unsigned or incorrectly attested DIDs receive Level C attestation or are flagged as potential spam by terminating carriers. Deliverability degrades. Some carriers will drop unsigned calls outright.

**Prevention:**
- Register with the STIR/SHAKEN Policy Administrator (STI-PA) early — this is a bureaucratic process with lead time.
- Build certificate lifecycle management into the project (certificate rotation, expiry monitoring).
- Attestation level matters: Level A requires that you own the number; Level B requires authorization to use it; Level C is everything else. Aim for Level A on owned DIDs.

**Detection:** Calls tagged as "Spam Likely" on terminating carriers. Check with tools like TransNexus CNAM lookup.

**Phase:** US compliance module (Phase 3). Begin STI-PA registration before building the US module.

---

## Moderate Pitfalls

---

### Pitfall 7: Number Pool Race Conditions Under Concurrent Load

**What goes wrong:** When multiple agent sessions request a DID simultaneously, two sessions check out the same number if the allocation is not atomic. The second caller hears the first caller's audio or calls fail with confusing errors.

**Why it happens:** Number pool queries are often implemented as SELECT + UPDATE without a transaction or row-level lock. Under any concurrency (even 2 simultaneous calls), the race can trigger.

**Prevention:**
- Implement pool allocation as `SELECT FOR UPDATE SKIP LOCKED` in a single transaction (PostgreSQL / SQLite WAL mode).
- Use a lease model with TTL: numbers are reserved for the duration of a call plus a cleanup window. An orphaned lease expires automatically.
- Load-test pool allocation explicitly at 10x expected concurrent calls before shipping.

**Detection:** Two sessions sharing a number (check call logs for overlap). Race condition may only manifest under load.

**Phase:** Number pool management (Phase 2).

---

### Pitfall 8: Barge-In Detection Using VAD Alone

**What goes wrong:** Voice Activity Detection triggers on "mm-hmm", coughs, background music, and typing. The agent interrupts itself or the user mid-sentence. Conversely, a high-sensitivity threshold causes the agent to ignore real interruptions.

**Why it happens:** VAD is the easiest thing to wire up, and it works well in demo conditions. Production has noise.

**Consequences:** Conversations require 3-5x more turns. Users abandon calls. The agent sounds broken.

**Prevention:**
- Implement a two-layer interruption detector: VAD as the first gate (is there any audio?), plus a short ASR segment as the second gate (is it a backchannel or a real utterance?).
- Backchannels ("yeah", "uh-huh", "okay") should not interrupt; treat them as acknowledgments and continue.
- Build a "grace window" — do not barge-in during the first 500ms of the agent's response, when the TTS hasn't said anything meaningful yet.
- Use silero-VAD (free, fast, good noise robustness) rather than WebRTC VAD.

**Detection:** Monitor interruption rate in production. If > 15% of agent utterances are interrupted in the first 500ms, barge-in detection is too aggressive.

**Phase:** Voice pipeline (Phase 2).

---

### Pitfall 9: FreeSWITCH ESL Python Binding Is Not Actually Connected When `con.connected` Is True

**What goes wrong:** The official Python ESL binding's `con.connected` property returns `True` even when connected to a port with nothing listening. Connection state detection is unreliable.

**Why it happens:** The SWIG-generated binding does not check socket state properly.

**Prevention:**
- Use `greenswitch` (gevent-based) or `switchio` (asyncio-based) instead of the raw Python ESL module for production code.
- Always verify connection by sending a `api status` command after connecting and checking for a valid response.
- Never rely on `con.connected` alone in any retry or health-check logic.

**Detection:** ESL shows connected but events are not received. Health checks pass but calls fail.

**Phase:** FreeSWITCH integration (Phase 1).

---

### Pitfall 10: Tool Call Latency Doubles the LLM Budget

**What goes wrong:** When the agent needs to look something up (DNC check, CRM lookup, compliance state query) via a tool call before composing a reply, the effective LLM latency becomes `LLM_latency + tool_latency + LLM_first_token_latency`. On a 300ms LLM budget, this is instantly fatal.

**Why it happens:** Tool calls feel like "the agent just does something", not like "the agent pauses the entire voice pipeline."

**Prevention:**
- Distinguish between pre-call tool calls (run before call starts, results cached in session context) and mid-call tool calls (block the pipeline).
- DNC checks, consent state, and compliance rules must be pre-fetched at session initialization, not at first LLM invocation.
- For mid-call lookups, use a "thinking" filler utterance ("Let me check that...") triggered immediately while the tool call runs in parallel.
- Design tool call patterns around streaming partial completions — the LLM should start generating a response that doesn't depend on tool output, then incorporate it.

**Detection:** Profile the pipeline. Any tool call that blocks the STT→LLM→TTS pipeline for > 100ms is a latency hazard.

**Phase:** Agent interface design (Phase 2).

---

### Pitfall 11: GPU Memory Contention Between STT, TTS, and Local LLM

**What goes wrong:** Running faster-whisper, Piper/Kokoro, and a local LLM on the same GPU causes memory pressure and context-switching overhead. Under concurrent call load, one model gets evicted from VRAM and reload time (seconds) blows the latency budget.

**Why it happens:** Single-GPU development machines look fine in testing. The RTX 3060 (12GB VRAM) is tight for even one medium-sized LLM plus STT model.

**Constraints from PROJECT.md:** "1-4 concurrent calls single GPU, 16-64 with multi-GPU."

**Prevention:**
- Allocate dedicated GPU memory for each model at startup. Do not allow dynamic loading/unloading in the hot path.
- For single-GPU setups: use a quantized LLM (GGUF Q4_K_M fits in 4-6GB), faster-whisper `small.en` (244MB), and CPU-based Piper for TTS (Piper is CPU-native and fast enough at 50-100ms).
- For multi-GPU: pin STT to GPU 0, LLM to GPU 1, TTS to CPU.
- Document minimum VRAM requirements in the setup guide.

**Detection:** VRAM usage monitoring during call load tests. Any model reload during an active call is a symptom.

**Phase:** Hardware benchmarking (Phase 1). Do not proceed to multi-call support without profiling VRAM.

---

### Pitfall 12: Codec Transcoding Compounds Audio Quality Loss

**What goes wrong:** G.711 (8 kHz, narrowband) is the PSTN standard. Every transcoding step degrades audio. G.711 → G.722 → Opus → pipeline input means three lossy transforms before STT sees the audio.

**Prevention:**
- Define a single canonical audio format for the entire pipeline (16 kHz, mono, 16-bit PCM) and convert once at the PSTN boundary.
- Configure FreeSWITCH to do the single conversion at ingest. All internal pipeline components use the canonical format.
- For agent-to-agent WebRTC: negotiate Opus directly (48 kHz, then downsample once to 16 kHz for STT). Never G.711 between agents.
- Never use G.729 with synthetic TTS output — its compression artifacts make synthesized voices sound especially unnatural.

**Detection:** "Tinny" or "robotic" audio that worsens over a call. Check codec negotiation logs.

**Phase:** Voice pipeline (Phase 1).

---

### Pitfall 13: Janus File Descriptor Limit at Production Call Volume

**What goes wrong:** Each WebRTC session in Janus consumes multiple file descriptors (RTP/RTCP sockets, DTLS state). The default Linux `ulimit -n` is 1024. At ~200 concurrent sessions, Janus silently starts rejecting new connections without clear error messages in its logs.

**Why it happens:** Never hits in development. Developers don't know about OS-level fd limits.

**Prevention:**
- Set `LimitNOFILE=65536` in the systemd unit for Janus.
- Also set for FreeSWITCH: add to `/etc/systemd/system/freeswitch.service`.
- Add fd limit monitoring to operational dashboards.
- Do not run post-call recording processing (janus-pp-rec, ffmpeg) on the same server handling live calls — it causes CPU/IO spikes at exactly the wrong moment.

**Detection:** New connections silently rejected at high load. Check `/proc/$(pgrep janus)/fd | wc -l` under load.

**Phase:** Infrastructure (Phase 1, operational setup).

---

## Minor Pitfalls

---

### Pitfall 14: max-sessions and sessions-per-second Not Tuned in FreeSWITCH

**What goes wrong:** Default FreeSWITCH configuration caps concurrent sessions far below hardware capability. Under load, new calls are rejected with no clear error.

**Prevention:** Edit `autoload_configs/switch.conf.xml` and set `max-sessions` and `sessions-per-second` to values appropriate for the hardware. Add load testing before considering any call concurrency target "achieved."

**Phase:** FreeSWITCH setup (Phase 1).

---

### Pitfall 15: SIP Profile ext-rtp-ip Autodiscovery Fails on Multi-Homed Hosts

**What goes wrong:** FreeSWITCH's `auto-nat` feature tries to discover the external IP. On hosts with multiple network interfaces (common in cloud or containerized deployments), it picks the wrong one.

**Prevention:** Always set `ext-rtp-ip` and `ext-sip-ip` explicitly in the SIP profile XML. Use `$${external_rtp_ip}` variable tied to a known-good IP, not autodiscovery.

**Phase:** FreeSWITCH + SIP trunk integration (Phase 1).

---

### Pitfall 16: SMPP Connection Not Keeping Alive Under Inactivity

**What goes wrong:** SMPP connections time out after periods of inactivity. The application assumes the connection is alive, submits a message, and gets a silent failure or a confusing ESME_RINVBNDSTS error.

**Prevention:** Implement ENQUIRE_LINK heartbeats on the SMPP session. Monitor for ESME_RTHROTTLED (temporary backpressure) vs ESME_RMSGQFUL (permanent queue full) — they require different retry strategies.

**Phase:** SMS integration (Phase 3 or later).

---

### Pitfall 17: Call Recording Compliance Is Jurisdiction-Specific and Asymmetric

**What goes wrong:** 13 US states require all-party consent for call recording (California, Florida, Illinois, etc.). Recording without disclosure in these states is a criminal offense, not just a civil violation. A "record everything" default silently creates liability in 13 states.

**Prevention:**
- The consent/recording module must check the called party's area code / geographic jurisdiction and apply the correct consent rule.
- Default: do not record unless consent is affirmative and jurisdiction-specific rules are satisfied.
- The AI disclosure requirement (California AB 2905, Texas SB 140) means the agent must announce it is AI-generated at the start of every call regardless of recording.

**Phase:** Compliance gateway / US module (Phase 3).

---

### Pitfall 18: Whisper Hallucination on Silence and Background Noise

**What goes wrong:** Whisper is known to hallucinate plausible-sounding transcription ("Thank you for watching", "Please subscribe") on silent or very noisy audio segments. In a voice pipeline, this produces phantom agent responses mid-silence.

**Why it happens:** Whisper was trained on a corpus that includes YouTube videos. It learned to predict likely audio conclusions, including silent video endings.

**Prevention:**
- Gate Whisper input with a silence/noise detector (silero-VAD). Only pass audio segments with confirmed speech energy.
- Discard Whisper output when the no-speech probability exceeds a threshold (faster-whisper exposes `no_speech_prob` per segment).
- Set minimum segment length — do not transcribe sub-500ms chunks.

**Detection:** Agent responds to silence. Check `no_speech_prob` values in transcription logs.

**Phase:** Voice pipeline (Phase 1-2).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| FreeSWITCH install | B2BUA misunderstanding; default session limits too low; SIP ALG on dev router | Read architecture docs; set max-sessions; disable SIP ALG at network boundary |
| Voice pipeline | 8 kHz / 16 kHz codec mismatch; Whisper hallucination on silence; batch-mode latency | Resample at ingest; silero-VAD gating; streaming STT from day one |
| SIP trunk integration | NAT / one-way audio; SIP ALG interference; ext-rtp-ip wrong | Explicit ext-rtp-ip; full RTP range in firewall; test against real trunk early |
| Number pool | Race conditions on concurrent checkout | SELECT FOR UPDATE SKIP LOCKED; lease + TTL pattern |
| Compliance gateway | TCPA / DNC bypassed in dev; FCC AI disclosure not wired | Make gateway structurally non-bypassable; wire disclosure into TTS |
| STIR/SHAKEN | Certificate registration not started early enough | Begin STI-PA registration in parallel with US module development |
| Barge-in | VAD triggers on backchannels | Two-layer detection (VAD + short ASR); grace window |
| Agent tool calls | Tool call latency doubles LLM budget | Pre-fetch compliance/DNC state at session init; filler utterance for mid-call lookups |
| WebRTC agent mesh | TURN missing; Janus fd limits | coturn as first-class requirement; ulimit in systemd unit |
| Multi-call GPU | VRAM contention; model reload during hot path | Pin models at startup; CPU TTS; quantized LLM |
| Call recording | All-party consent states; AI disclosure | Jurisdiction check on area code; AI disclosure hardcoded as first utterance |

---

## Sources

- [FreeSWITCH Common Errors](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Troubleshooting-Debugging/Common-Errors_1966723/) — MEDIUM confidence
- [FreeSWITCH NAT Traversal](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Networking/NAT-Traversal_3375417/) — HIGH confidence (official docs)
- [FreeSWITCH Bypass Media Overview](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Codecs-and-Media/Bypass-Media-Overview/) — HIGH confidence (official docs)
- [Python ESL Documentation](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Client-and-Developer-Interfaces/Python-ESL/) — HIGH confidence (official docs)
- [faster-whisper 8 kHz issue thread](https://github.com/SYSTRAN/faster-whisper/issues/931) — MEDIUM confidence (community)
- [whisper.cpp 8 kHz feature request](https://github.com/ggml-org/whisper.cpp/issues/1844) — MEDIUM confidence (community)
- [FCC confirms TCPA applies to AI-generated voices](https://www.fcc.gov/document/fcc-confirms-tcpa-applies-ai-technologies-generate-human-voices) — HIGH confidence (official)
- [TCPA compliance for AI calls 2025](https://www.ringly.io/blog/is-your-ai-phone-agent-breaking-the-law-5-rules-you-need-to-know-2025) — MEDIUM confidence
- [State-by-state call recording compliance 2025](https://hostie.ai/resources/state-by-state-call-recording-compliance-ai-virtual-hosts-2025) — MEDIUM confidence
- [STIR/SHAKEN 2025 implementation checklist](https://www.bandwidth.com/resources/stir-shaken-implementation-checklist/) — MEDIUM confidence
- [STIR/SHAKEN RMD filing requirements 2025](https://viirtue.com/stir-shaken-and-the-robocall-mitigation-database-what-msps-and-voip-providers-must-file-in-2025/) — MEDIUM confidence
- [SIP trunk NAT traversal failures](https://www.sip.us/blog/latest-news/common-sip-trunk-troubleshooting-tips-and-fixes/) — MEDIUM confidence
- [SIP ALG and VoIP](https://www.sip.us/blog/latest-news/sip-alg-and-voip-what-it-is/) — MEDIUM confidence
- [Voice AI latency engineering at Cresta](https://cresta.com/blog/engineering-for-real-time-voice-agent-latency) — MEDIUM confidence
- [Barge-in detection pitfalls](https://sparkco.ai/blog/master-voice-agent-barge-in-detection-handling) — MEDIUM confidence
- [Janus production pitfalls (700-person call post-mortem)](https://dev.to/newlc/i-built-a-700-person-video-call-without-zoom-heres-every-mistake-i-made-5dam) — MEDIUM confidence
- [Janus hardened deployment](https://webrtc.ventures/2021/08/hardened-janus-gateway/) — MEDIUM confidence
- [TURN server for WebRTC](https://www.videosdk.live/developer-hub/webrtc/turn-server-for-webrtc) — MEDIUM confidence
- [FreeSWITCH RTP port range in Docker](https://www.engagespark.com/blog/rtp-port-ranges-for-freeswitch-in-docker/) — MEDIUM confidence
- [Real-time voice AI infrastructure guide](https://introl.com/blog/voice-ai-infrastructure-real-time-speech-agents-asr-tts-guide-2025) — MEDIUM confidence
- [Whisper streaming strategy](https://community.openai.com/t/whisper-streaming-strategy/885324) — LOW confidence (community forum)
- [Voice AI codec comparison](https://telnyx.com/resources/voice-ai-hd-codecs) — MEDIUM confidence

# Phase 1: FreeSWITCH + Voice Pipeline - Context

**Gathered:** 2026-03-24
**Status:** Ready for planning

<domain>
## Phase Boundary

A voice call can be placed and received through local FreeSWITCH infrastructure with a fully local STT/TTS loop completing under 800ms. This phase delivers: outbound call origination, inbound call answering, SIP trunk connectivity, local STT (faster-whisper), local TTS (Kokoro-ONNX), streaming voice loop, VAD gating, turn detection, barge-in handling, and 8kHz→16kHz audio resampling.

</domain>

<decisions>
## Implementation Decisions

### FreeSWITCH integration
- **D-01:** Use Genesis ESL library (asyncio-native, v2026.3.21) as the primary Python-to-FreeSWITCH interface. Do not use greenswitch (gevent), switchio (unmaintained), or raw SWIG ESL bindings.
- **D-02:** Use ESL inbound mode — Python connects to FreeSWITCH ESL socket (port 8021). Simpler than outbound mode and standard for programmatic call control.
- **D-03:** Dev environment is Docker Compose — FreeSWITCH and Redis as services, FreeSWITCH config volume-mounted for iteration. Python orchestrator runs on host during dev.

### Audio streaming architecture
- **D-04:** Use mod_audio_stream to stream per-call audio from FreeSWITCH to Python via WebSocket. Each active call gets its own WebSocket connection carrying raw PCM audio bidirectionally.
- **D-05:** FreeSWITCH decodes G.711 (PSTN codec) internally. Python receives linear PCM and resamples from 8kHz to 16kHz before feeding to faster-whisper. Use scipy or librosa for resampling.
- **D-06:** Audio format through the pipeline: G.711 (SIP/RTP) → PCM 8kHz (FreeSWITCH) → PCM 16kHz (Python/Whisper) → text → LLM → text → PCM (Kokoro TTS) → 8kHz (FreeSWITCH) → G.711 (SIP/RTP).

### Voice pipeline orchestration
- **D-07:** Async streaming pipeline using Python asyncio. No stage waits for the previous stage to fully complete. STT streams partial transcripts. LLM begins generating on partial input. TTS begins synthesizing the first sentence while LLM generates the second.
- **D-08:** Silero VAD (built into faster-whisper) gates STT input — prevents hallucination on silence and provides speech onset/offset detection for turn-taking.
- **D-09:** Turn detection uses VAD + configurable silence threshold (default ~700ms of silence after speech = end of turn). Semantic turn detection is v2.
- **D-10:** Barge-in: when VAD detects speech during TTS playback, immediately cancel TTS output, flush audio buffers, and re-enter listening state. The interrupted partial response is discarded.

### LLM integration boundary
- **D-11:** LLM interface is OpenAI-compatible API (chat completions with streaming). Works with local Ollama, OpenAI API, Anthropic via adapter, or any OpenAI-compatible endpoint. LLM-agnostic from day one.
- **D-12:** Agent behavior defined via system message prompt. For Phase 1, the agent is a simple conversational responder — tool-use protocol (call/sms/transfer actions) comes in Phase 3.
- **D-13:** LLM is the one component that may be remote (cloud API) rather than local. The architecture must support both local and remote LLM with the same interface.

### Claude's Discretion
- Exact Docker Compose service configuration and networking
- FreeSWITCH dialplan XML structure
- Python project structure (packages, modules, entry points)
- Specific resampling library choice (scipy vs librosa vs custom)
- WebSocket server implementation details for mod_audio_stream
- Error handling and reconnection strategy for ESL connection
- Logging framework and format

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — Core value, constraints (language, latency budget, no vendor accounts), key decisions
- `.planning/REQUIREMENTS.md` — CALL-01..03, CALL-06, VOICE-01..07 requirement definitions

### Research
- `.planning/research/STACK.md` — Technology versions, library choices, compatibility matrix, what NOT to use
- `.planning/research/ARCHITECTURE.md` — Component boundaries, data flow, integration patterns, build order
- `.planning/research/PITFALLS.md` — Domain pitfalls: codec mismatch, SIP ALG, latency budget, FreeSWITCH ESL gotchas

### External concept documents
- `/Users/paul/paul/brains/docs/drafts/2026-03-24-agentic-telecom-concept-brief.html` — Full architecture diagrams, voice pipeline latency budget breakdown, hardware profiles

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None — patterns will be established in this phase

### Integration Points
- FreeSWITCH ESL socket (port 8021) — primary control plane interface
- mod_audio_stream WebSocket — per-call media plane interface
- Redis — session state and coordination (shared with Phase 2)

</code_context>

<specifics>
## Specific Ideas

- The onboarding experience should feel like the terminal mockup in the concept brief: `holler call +44XXXXXXXXXX --agent "..."` and the call just works (CLI is Phase 3, but the underlying capability must work here)
- Voice loop latency budget from concept brief: VAD <50ms, STT ~100-200ms, LLM ~200-400ms, TTS ~100-150ms. Total <800ms.
- The concept brief emphasizes "streaming throughout" — no stage waits for full completion of previous stage
- Hardware profile: minimum RTX 3060 for STT, CPU i7+ for TTS. Must work on single consumer GPU.

</specifics>

<deferred>
## Deferred Ideas

- Semantic turn detection (transformer-based, beyond VAD+silence) — v2 enhancement
- Multi-GPU session dispatcher for concurrent calls — Phase 2+ when scaling matters
- Whisper.cpp (C/Rust) as optimized STT alternative — v2, after Python pipeline is proven
- Call transfer between agents — Phase 3 (agent interface)

</deferred>

---

*Phase: 01-freeswitch-voice-pipeline*
*Context gathered: 2026-03-24*

# Phase 1: FreeSWITCH + Voice Pipeline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 01-freeswitch-voice-pipeline
**Areas discussed:** FreeSWITCH integration, Audio streaming architecture, Voice pipeline orchestration, LLM integration boundary
**Mode:** Auto (all recommended defaults selected)

---

## FreeSWITCH Integration

| Option | Description | Selected |
|--------|-------------|----------|
| Genesis (asyncio) | asyncio-native ESL, v2026.3.21, actively maintained, MIT license | ✓ |
| greenswitch (gevent) | gevent-based ESL, production-stable but heavier dependency | |
| switchio | 43 open issues, unclear maintenance | |

**User's choice:** [auto] Genesis — recommended by stack research as primary ESL choice
**Notes:** Inbound ESL mode selected (Python connects to FreeSWITCH socket). Docker Compose for dev environment.

---

## Audio Streaming Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| mod_audio_stream (WebSocket) | Per-call WebSocket stream of raw PCM, bidirectional | ✓ |
| ESL record + file polling | Record to file, poll for new audio — high latency | |
| mod_shout (HTTP streaming) | HTTP-based audio streaming — less bidirectional control | |

**User's choice:** [auto] mod_audio_stream — recommended for real-time bidirectional audio
**Notes:** G.711 decoded by FreeSWITCH, PCM resampled 8kHz→16kHz in Python for Whisper input.

---

## Voice Pipeline Orchestration

| Option | Description | Selected |
|--------|-------------|----------|
| Async streaming (asyncio) | No stage waits for full completion; partial results flow downstream | ✓ |
| Sequential batch | Each stage completes fully before next begins — simpler but 2-4s latency | |

**User's choice:** [auto] Async streaming — required to meet 800ms latency target
**Notes:** Silero VAD gates STT. Barge-in cancels TTS and re-enters listening state. Turn detection via VAD + silence threshold.

---

## LLM Integration Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| OpenAI-compatible API | Works with Ollama, OpenAI, Anthropic adapters — LLM-agnostic | ✓ |
| Direct model loading | Load model in-process — maximum control but couples to specific model | |
| Custom protocol | Custom agent-LLM protocol — flexibility but non-standard | |

**User's choice:** [auto] OpenAI-compatible API — industry standard, maximum interoperability
**Notes:** Agent behavior via system message. Both local and remote LLM supported. Tool-use protocol deferred to Phase 3.

---

## Claude's Discretion

- Docker Compose configuration
- FreeSWITCH dialplan structure
- Python project structure
- Resampling library choice
- WebSocket server implementation
- Error handling / reconnection
- Logging framework

## Deferred Ideas

- Semantic turn detection — v2 enhancement
- Multi-GPU dispatcher — Phase 2+
- Whisper.cpp C/Rust STT — v2
- Call transfer — Phase 3

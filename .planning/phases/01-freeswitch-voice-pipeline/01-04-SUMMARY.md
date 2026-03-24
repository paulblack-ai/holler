---
phase: 01-freeswitch-voice-pipeline
plan: 04
subsystem: voice
tags: [websockets, openai, asyncio, vad, stt, tts, llm, pipeline, audio-bridge, mod_audio_stream]

# Dependency graph
requires:
  - phase: 01-freeswitch-voice-pipeline plan 02
    provides: STTEngine, TTSEngine, VADState, VADEvent, PipelineState, VADConfig
  - phase: 01-freeswitch-voice-pipeline plan 03
    provides: resampler upsample_8k_to_16k, downsample_24k_to_8k

provides:
  - LLMClient: streaming OpenAI-compatible LLM client with async generator token streaming
  - LLMConfig: configurable endpoint, model, system prompt, history turns
  - VoicePipeline: streaming coordinator wiring STT->LLM->TTS with VAD and barge-in
  - VoiceSession: per-call state (history, audio buffer, VAD, TTS task, cancel event)
  - AudioBridge: WebSocket server handling mod_audio_stream binary PCM and JSON protocol
  - AudioBridgeConfig: configurable host/port for WebSocket server
  - start_audio_bridge: convenience factory function
  - holler.core.voice __init__: unified exports for all voice pipeline components

affects: [phase 01-05, phase 02, phase 03, any integration tests for voice pipeline]

# Tech tracking
tech-stack:
  added: [openai (AsyncOpenAI streaming), websockets (WebSocket server)]
  patterns:
    - Async token queue pattern connecting LLM stream to TTS stream
    - Fire-and-forget asyncio.Task for response pipeline (allows concurrent barge-in detection)
    - asyncio.Event (_tts_cancel) as coordination mechanism across LLM and TTS tasks
    - Energy-based speech detection as quick pre-filter before full VAD
    - base64-encoded JSON audio responses to FreeSWITCH (mod_audio_stream protocol)

key-files:
  created:
    - holler/core/voice/llm.py
    - holler/core/voice/pipeline.py
    - holler/core/voice/audio_bridge.py
  modified:
    - holler/core/voice/__init__.py

key-decisions:
  - "token_queue pattern: LLM streams into asyncio.Queue, TTS consumes from same queue — enables streaming TTS to begin before LLM response is complete"
  - "Fire-and-forget asyncio.Task for _respond: allows new audio frames to arrive (for barge-in detection) while TTS is playing"
  - "_tts_cancel asyncio.Event shared between feed_tokens() and TTS loop — coordinates barge-in cancellation without requiring task.cancel() on the LLM task"
  - "base64-encoded audio in JSON (not raw binary WebSocket frames) for FreeSWITCH response — safer interop, can optimize to binary later (RESEARCH Open Question 3)"
  - "Audio bridge receives 16kHz PCM directly (mod_audio_stream configured for 16k in dialplan) — no upsampling needed for STT input in Phase 1"

patterns-established:
  - "Pipeline coordinator pattern: one shared VoicePipeline, per-call VoiceSession isolation"
  - "Deferred initialization: all heavy models initialized via initialize(), not __init__()"
  - "Latency instrumentation: pipeline.first_audio event with total_latency_ms for VOICE-03 tracking"

requirements-completed: [VOICE-03, VOICE-06]

# Metrics
duration: 3min
completed: 2026-03-24
---

# Phase 1 Plan 4: Audio Bridge, LLM Client, and Pipeline Coordinator Summary

**WebSocket audio bridge for mod_audio_stream, streaming OpenAI-compatible LLM client, and async pipeline coordinator wiring STT->LLM->TTS with barge-in cancellation**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-24T17:44:12Z
- **Completed:** 2026-03-24T17:47:12Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- LLM client streams tokens from any OpenAI-compatible endpoint (Ollama, OpenAI, Anthropic adapter) with conversation history and configurable context window
- Pipeline coordinator connects STT, LLM, and TTS via async token queue — no stage waits for the previous to complete (D-07)
- Barge-in path cancels TTS task immediately via asyncio.Event and re-enters LISTENING state (D-10, VOICE-06)
- Audio bridge handles binary WebSocket frames from mod_audio_stream and sends base64-encoded TTS audio back per FreeSWITCH protocol

## Task Commits

Each task was committed atomically:

1. **Task 1: OpenAI-compatible streaming LLM client** - `4fb6c48` (feat)
2. **Task 2: Audio bridge, pipeline coordinator, and voice module exports** - `c1a8e7f` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `holler/core/voice/llm.py` - LLMConfig, LLMClient with async streaming token generator, DEFAULT_SYSTEM_PROMPT
- `holler/core/voice/pipeline.py` - VoicePipeline coordinator, VoiceSession per-call state, _respond() STT->LLM->TTS flow
- `holler/core/voice/audio_bridge.py` - AudioBridge WebSocket server, mod_audio_stream protocol handler
- `holler/core/voice/__init__.py` - Unified exports for all voice pipeline components via __all__

## Decisions Made

- Used `asyncio.Queue` as the coordination primitive between LLM streaming and TTS synthesis — allows TTS to begin on the first sentence while LLM is still generating later sentences
- Chose base64-encoded JSON for TTS audio sent back to FreeSWITCH — safer than raw binary WebSocket frames, can be optimized later
- `_tts_cancel` asyncio.Event rather than direct task cancellation — provides cleaner coordination between the `feed_tokens()` coroutine and the TTS iteration loop
- Energy threshold `> 0.01` for `_detect_speech()` is a simple pre-filter; actual VAD happens in faster-whisper's built-in Silero VAD

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `websockets` package not installed in system Python — installed via pip3. This is expected in a dev environment without the full `holler` package installed; documented as environment setup (not a bug).

## User Setup Required

None - no external service configuration required beyond what was established in prior plans.

## Known Stubs

None - all components are fully wired. LLM client requires a running OpenAI-compatible endpoint (Ollama locally or OpenAI API key) which is a runtime dependency, not a code stub.

## Next Phase Readiness

- All voice pipeline components are importable and wired: `from holler.core.voice import VoicePipeline, AudioBridge, LLMClient`
- Plan 05 (integration/verification) can now wire the full stack: ESL + AudioBridge + VoicePipeline
- Audio bridge and pipeline need runtime integration testing with live FreeSWITCH + mod_audio_stream

---
*Phase: 01-freeswitch-voice-pipeline*
*Completed: 2026-03-24*

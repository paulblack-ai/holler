# Phase 1: FreeSWITCH + Voice Pipeline - Research

**Researched:** 2026-03-24
**Domain:** VoIP softswitch integration, real-time STT/TTS, asyncio voice pipeline
**Confidence:** HIGH (core stack verified; some API details MEDIUM where official docs are thin)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Use Genesis ESL library (asyncio-native, v2026.3.21) as the primary Python-to-FreeSWITCH interface. Do not use greenswitch (gevent), switchio (unmaintained), or raw SWIG ESL bindings.
- **D-02:** Use ESL inbound mode — Python connects to FreeSWITCH ESL socket (port 8021). Simpler than outbound mode and standard for programmatic call control.
- **D-03:** Dev environment is Docker Compose — FreeSWITCH and Redis as services, FreeSWITCH config volume-mounted for iteration. Python orchestrator runs on host during dev.
- **D-04:** Use mod_audio_stream to stream per-call audio from FreeSWITCH to Python via WebSocket. Each active call gets its own WebSocket connection carrying raw PCM audio bidirectionally.
- **D-05:** FreeSWITCH decodes G.711 internally. Python receives linear PCM and resamples from 8kHz to 16kHz before feeding to faster-whisper. Use scipy or librosa for resampling.
- **D-06:** Audio format through the pipeline: G.711 (SIP/RTP) → PCM 8kHz (FreeSWITCH) → PCM 16kHz (Python/Whisper) → text → LLM → text → PCM (Kokoro TTS) → 8kHz (FreeSWITCH) → G.711 (SIP/RTP).
- **D-07:** Async streaming pipeline using Python asyncio. No stage waits for the previous stage to fully complete. STT streams partial transcripts. LLM begins generating on partial input. TTS begins synthesizing the first sentence while LLM generates the second.
- **D-08:** Silero VAD (built into faster-whisper) gates STT input — prevents hallucination on silence and provides speech onset/offset detection for turn-taking.
- **D-09:** Turn detection uses VAD + configurable silence threshold (default ~700ms of silence after speech = end of turn). Semantic turn detection is v2.
- **D-10:** Barge-in: when VAD detects speech during TTS playback, immediately cancel TTS output, flush audio buffers, and re-enter listening state. The interrupted partial response is discarded.
- **D-11:** LLM interface is OpenAI-compatible API (chat completions with streaming). Works with local Ollama, OpenAI API, Anthropic via adapter, or any OpenAI-compatible endpoint. LLM-agnostic from day one.
- **D-12:** Agent behavior defined via system message prompt. For Phase 1, the agent is a simple conversational responder — tool-use protocol comes in Phase 3.
- **D-13:** LLM is the one component that may be remote (cloud API) rather than local. The architecture must support both local and remote LLM with the same interface.

### Claude's Discretion
- Exact Docker Compose service configuration and networking
- FreeSWITCH dialplan XML structure
- Python project structure (packages, modules, entry points)
- Specific resampling library choice (scipy vs librosa vs custom)
- WebSocket server implementation details for mod_audio_stream
- Error handling and reconnection strategy for ESL connection
- Logging framework and format

### Deferred Ideas (OUT OF SCOPE)
- Semantic turn detection (transformer-based, beyond VAD+silence) — v2 enhancement
- Multi-GPU session dispatcher for concurrent calls — Phase 2+ when scaling matters
- Whisper.cpp (C/Rust) as optimized STT alternative — v2, after Python pipeline is proven
- Call transfer between agents — Phase 3 (agent interface)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CALL-01 | Agent can initiate an outbound voice call to a PSTN number via FreeSWITCH ESL | Genesis ESL `Inbound` mode + `originate` command via `client.send()` |
| CALL-02 | FreeSWITCH softswitch routes SIP calls to/from a configured SIP trunk | FreeSWITCH `sofia` external profile + gateway configuration XML |
| CALL-03 | Agent can answer and route an inbound call to an agent session | FreeSWITCH dialplan XML with `answer` + `park` apps; ESL `Consumer` mode for CHANNEL_ANSWER event |
| CALL-06 | Call terminates gracefully on agent instruction, error, or remote hangup | ESL `Consumer` mode handles CHANNEL_HANGUP; `Inbound.send("api uuid_kill <uuid>")` for agent-initiated hangup |
| VOICE-01 | STT runs locally via faster-whisper with streaming partial transcripts | `WhisperModel.transcribe()` returns a generator; `whisper_streaming` / `OnlineASRProcessor` for chunk-based real-time transcription |
| VOICE-02 | TTS runs locally via Kokoro-ONNX with streaming audio output | `kokoro-onnx` `Kokoro.create()` returns numpy array at 24kHz; sentence-chunking feeds TTS progressively |
| VOICE-03 | Full voice loop (STT → LLM → TTS) completes in under 800ms round-trip | Streaming pipeline design: VAD <50ms, STT first segment <200ms, LLM TTFT <300ms, TTS first chunk <100ms |
| VOICE-04 | VAD gates STT to prevent hallucination on silence | Silero VAD built into faster-whisper; `vad_filter=True` + `no_speech_prob` threshold check |
| VOICE-05 | Turn detection identifies when human stops speaking | VAD offset + configurable silence threshold (~700ms); implemented in the WebSocket audio consumer |
| VOICE-06 | Barge-in detection stops TTS playback when human interrupts | VAD onset during TTS playback triggers asyncio event; TTS generator cancelled; audio buffer flushed |
| VOICE-07 | Audio resampling handles 8kHz PSTN G.711 to 16kHz Whisper input | `soxr.ResampleStream` (best quality, no aliasing) or `scipy.signal.resample_poly` (built-in fallback) |
</phase_requirements>

---

## Summary

Phase 1 delivers the core voice call capability: FreeSWITCH routing calls over a SIP trunk, a Python ESL client controlling call lifecycle, and a full STT→LLM→TTS voice pipeline completing under 800ms. All three technical domains (FreeSWITCH integration, audio streaming, voice inference) are well-understood with verified library choices.

The primary integration point is `mod_audio_stream` — a third-party FreeSWITCH module that bridges call audio to a Python WebSocket server. This module requires building from source or using a pre-built Docker image and is the most operationally complex piece of Phase 1. The module streams L16 (linear PCM) audio bidirectionally: FreeSWITCH sends caller audio to Python, Python sends TTS audio back to FreeSWITCH.

The streaming pipeline architecture is non-negotiable for the 800ms latency target. Whisper's `transcribe()` generator provides progressive segment output; the `whisper_streaming` / `OnlineASRProcessor` pattern provides true chunk-based real-time transcription with VAD integration. TTS sentence-chunking (synthesize first sentence while LLM generates the second) is the key TTS latency technique.

**Primary recommendation:** Build the Docker Compose stack first (FreeSWITCH + Redis), verify ESL connectivity and a raw SIP call, then add mod_audio_stream and the voice pipeline incrementally — validating each layer before adding the next.

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 1 |
|-----------|------------------|
| Python core for orchestration | All call control, voice pipeline, and ESL code is Python 3.11+ |
| FreeSWITCH as softswitch | No Asterisk, no Kamailio — FreeSWITCH only |
| faster-whisper for STT | Use `WhisperModel` from `faster-whisper` package, not `openai-whisper` |
| Kokoro / Piper for TTS | Primary TTS is Kokoro-ONNX; Orpheus is v2 option |
| Local inference only | STT and TTS must run locally; LLM may be remote (D-13) |
| <800ms latency budget | Streaming pipeline from day one — no batch modes |
| Apache 2.0 license | All dependencies must be Apache 2.0, MIT, or BSD compatible |
| No vendor accounts | SIP trunk is the only external account required |

---

## Standard Stack

### Core Libraries for Phase 1

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Genesis | 2026.3.21 | FreeSWITCH ESL over asyncio | Locked (D-01). 29 releases, latest March 2026, MIT license, asyncio-native. Only maintained asyncio ESL library. |
| faster-whisper | 1.2.1 | STT with built-in Silero VAD | Locked (CLAUDE.md). 4x faster than openai-whisper, built-in VAD, generator-based streaming output. |
| kokoro-onnx | 0.5.x | Primary TTS | Locked (CLAUDE.md). 82M params, Apache 2.0, CPU-capable (~100-300ms), 24kHz PCM output. |
| soxr | 0.5.x | Audio resampling 8kHz→16kHz | Best-quality PCM resampling (SoX algorithm). `ResampleStream` for real-time chunked input. No aliasing artifacts. |
| websockets | 12.x | Python WebSocket server for mod_audio_stream | Standard asyncio WebSocket library. Receives audio from FreeSWITCH, sends TTS audio back. |
| openai | 1.x | OpenAI-compatible LLM streaming client | Locked (D-11). Works with Ollama, OpenAI API, any OpenAI-compatible endpoint via `base_url` param. |
| redis | 5.x | Session state (shared with Phase 2) | Locked (CLAUDE.md). Sub-millisecond reads, asyncio-compatible via `redis.asyncio`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| whisper_streaming (OnlineASRProcessor) | latest | Chunk-based real-time STT wrapper | Use when you need sub-second partial transcripts from audio chunks rather than complete utterances. Wraps faster-whisper. |
| scipy | 1.x | Audio resampling fallback | Fallback if soxr unavailable. Use `scipy.signal.resample_poly(audio, 2, 1)` for 8kHz→16kHz (exact 2:1 ratio). |
| numpy | 1.x / 2.x | PCM audio buffer manipulation | Required by faster-whisper and kokoro-onnx. Audio chunks are numpy arrays throughout the pipeline. |
| sounddevice | 0.4.x | Audio I/O for local dev/testing | Dev tool only — test VAD and TTS locally without FreeSWITCH. Not in production path. |
| structlog | 23.x | Structured logging | Recommended for call-correlated log events. JSON output with call_uuid, stage, latency fields. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| soxr | scipy.signal.resample_poly | scipy is a heavier dependency but already commonly installed. soxr has superior quality and is the reference implementation. Use soxr. |
| websockets | aiohttp WebSocket | aiohttp is heavier; websockets is the canonical async WebSocket library for Python. |
| openai Python SDK | httpx + manual SSE | Manual SSE parsing is error-prone. OpenAI SDK handles stream reconnection and delta accumulation correctly. |
| whisper_streaming | custom chunk buffer | whisper_streaming's "local agreement policy" avoids common pitfalls with mid-word cuts. Don't hand-roll. |

### Installation

```bash
# Python 3.11+ required (project constraint)
# Install uv first: pip install uv

uv pip install "genesis>=2026.3.21"
uv pip install "faster-whisper>=1.2.1"
uv pip install "kokoro-onnx>=0.5.0"
uv pip install "soxr>=0.3.7"
uv pip install "websockets>=12.0"
uv pip install "openai>=1.0"
uv pip install "redis>=5.0"
uv pip install "numpy>=1.26"
uv pip install "structlog>=23.0"

# System dependencies (Debian/Ubuntu in Docker)
# espeak-ng required by kokoro-onnx for phonemization
apt-get install -y espeak-ng

# Dev/test only
uv pip install "sounddevice>=0.4"
uv pip install "pytest>=8.0" "pytest-asyncio>=0.23"
```

**Version verification (run before using):**
```bash
python3 -m pip index versions genesis 2>/dev/null | head -1
python3 -m pip index versions faster-whisper 2>/dev/null | head -1
python3 -m pip index versions kokoro-onnx 2>/dev/null | head -1
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 1 scope)

```
holler/
├── core/
│   ├── voice/
│   │   ├── pipeline.py        # Async streaming coordinator (VAD→STT→LLM→TTS)
│   │   ├── stt.py             # faster-whisper wrapper + OnlineASRProcessor integration
│   │   ├── tts.py             # kokoro-onnx wrapper + sentence chunking
│   │   ├── vad.py             # VAD state machine (speech onset/offset, turn detection)
│   │   └── audio_bridge.py   # WebSocket server (receives from mod_audio_stream, sends TTS back)
│   └── freeswitch/
│       ├── esl.py             # Genesis ESL client (Inbound + Consumer modes)
│       ├── dialplan.py        # Dialplan XML fragments as Python strings
│       └── events.py          # ESL event handlers → call state transitions
├── config/
│   └── freeswitch/
│       ├── dialplan/
│       │   └── default.xml    # Inbound + outbound dialplan
│       └── sip_profiles/
│           └── external.xml   # SIP trunk gateway definition
├── docker/
│   ├── docker-compose.yml     # FreeSWITCH + Redis services
│   └── freeswitch/
│       └── Dockerfile         # Custom FS image with mod_audio_stream built in
└── tests/
    ├── unit/
    │   ├── test_stt.py
    │   ├── test_tts.py
    │   └── test_resampling.py
    └── integration/
        └── test_voice_loop.py  # Requires FreeSWITCH running
```

### Pattern 1: ESL Inbound Mode — Control Plane

**What:** Python connects to FreeSWITCH ESL port 8021 as a persistent client. All call control commands (originate, hangup, execute application) go through this connection. Uses Genesis `Inbound` and `Consumer` modes.

**When to use:** Always — this is the D-02 locked decision.

```python
# Source: https://github.com/Otoru/Genesis
import asyncio
from genesis import Inbound, Consumer

# Originate an outbound call
async def originate_call(destination: str, session_uuid: str) -> str:
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        # originate {session_uuid=X}sofia/gateway/sip_trunk/+14155551234 &park()
        cmd = (
            f"originate {{session_uuid={session_uuid}}}"
            f"sofia/gateway/sip_trunk/{destination} &park()"
        )
        result = await client.send(f"api {cmd}")
        return result  # returns the call UUID

# Subscribe to call events
app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("CHANNEL_ANSWER")
async def on_answer(event):
    call_uuid = event.get("Unique-ID")
    # Trigger mod_audio_stream for this call
    await start_audio_stream(call_uuid)

@app.handle("CHANNEL_HANGUP")
async def on_hangup(event):
    call_uuid = event.get("Unique-ID")
    await cleanup_session(call_uuid)

asyncio.run(app.start())
```

**Note on connection verification:** After connecting, send `api status` and verify response. Do not rely on connection state property alone (Pitfall 9).

### Pattern 2: mod_audio_stream WebSocket Bridge — Media Plane

**What:** FreeSWITCH dialplan activates `mod_audio_stream` on call answer, which opens a WebSocket to the Python audio bridge server. Audio arrives as binary L16 PCM frames; Python sends TTS audio back as JSON with base64-encoded PCM.

**When to use:** On every answered call — this is the D-04 locked decision.

**FreeSWITCH Dialplan (for inbound calls):**
```xml
<!-- config/freeswitch/dialplan/default.xml -->
<extension name="inbound_agent">
  <condition field="destination_number" expression="^(\d+)$">
    <action application="set" data="STREAM_SAMPLE_RATE=16000"/>
    <action application="set" data="STREAM_BUFFER_SIZE=640"/>
    <action application="answer"/>
    <action application="set" data="api_on_answer=uuid_audio_stream ${uuid} start ws://host.docker.internal:8080/voice/${uuid} mono 16k"/>
    <action application="park"/>
  </condition>
</extension>
```

**Python WebSocket server receiving audio and sending TTS:**
```python
# Source: https://github.com/amigniter/mod_audio_stream
import websockets
import json
import base64
import numpy as np

async def voice_handler(websocket, path):
    # path = /voice/{call_uuid}
    call_uuid = path.split("/")[-1]
    session = await get_or_create_session(call_uuid)

    async for message in websocket:
        if isinstance(message, bytes):
            # Raw L16 PCM audio at 16kHz (mod_audio_stream configured for 16k)
            pcm_16k = np.frombuffer(message, dtype=np.int16)
            await audio_pipeline(websocket, pcm_16k, session)
        elif isinstance(message, str):
            # metadata JSON sent before audio begins
            meta = json.loads(message)

async def send_tts_audio(websocket, pcm_samples: np.ndarray, sample_rate: int):
    """Send TTS audio back to FreeSWITCH via mod_audio_stream."""
    # Resample TTS output (24kHz from Kokoro) down to 8kHz for FreeSWITCH
    import soxr
    pcm_8k = soxr.resample(pcm_samples.astype(np.float32), sample_rate, 8000)
    pcm_int16 = (pcm_8k * 32767).astype(np.int16)
    payload = {
        "type": "streamAudio",
        "data": {
            "audioDataType": "raw",
            "sampleRate": 8000,
            "audioData": base64.b64encode(pcm_int16.tobytes()).decode()
        }
    }
    await websocket.send(json.dumps(payload))
```

**Important:** `mod_audio_stream` is NOT a standard FreeSWITCH module. It must be compiled into the FreeSWITCH Docker image. Source: [amigniter/mod_audio_stream](https://github.com/amigniter/mod_audio_stream).

### Pattern 3: Real-Time STT with faster-whisper + VAD

**What:** `WhisperModel.transcribe()` returns a generator of segments. Wrap with `OnlineASRProcessor` from whisper_streaming for true chunk-based streaming. Silero VAD (built into faster-whisper) gates input.

**When to use:** For all STT in the voice pipeline (VOICE-01, VOICE-04).

```python
# Source: https://github.com/SYSTRAN/faster-whisper + https://github.com/ufal/whisper_streaming
from faster_whisper import WhisperModel
import numpy as np

# Initialize once at startup — not per-call
model = WhisperModel(
    "distil-large-v3",   # Recommended for latency/accuracy balance
    device="cuda",        # or "cpu" for CPU-only deployments
    compute_type="float16"  # "int8" for CPU
)

# Per-call VAD + transcription
async def transcribe_stream(audio_chunks: asyncio.Queue) -> asyncio.AsyncGenerator[str, None]:
    """Yields confirmed partial transcripts as they become available."""
    buffer = np.array([], dtype=np.float32)

    async for chunk in audio_queue_iter(audio_chunks):
        # chunk is np.int16 at 16kHz; normalize to float32 [-1, 1]
        float_chunk = chunk.astype(np.float32) / 32768.0
        buffer = np.concatenate([buffer, float_chunk])

        # Process when we have ~1 second of audio
        if len(buffer) >= 16000:
            segments, info = model.transcribe(
                buffer,
                language="en",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300, "threshold": 0.5},
            )
            for segment in segments:
                if segment.no_speech_prob < 0.6:  # Filter hallucinations
                    yield segment.text
            # Trim buffer — keep last 0.5s for context continuity
            buffer = buffer[-8000:]
```

**Critical:** `no_speech_prob` threshold prevents Whisper hallucination on silence (Pitfall 18). Default is 0.6 — tune based on noise floor.

### Pattern 4: Kokoro TTS with Sentence Chunking

**What:** Kokoro-ONNX synthesizes audio from text. For streaming, split LLM output at sentence boundaries and synthesize each sentence as it arrives from the LLM token stream.

**When to use:** For all TTS synthesis (VOICE-02, VOICE-03).

```python
# Source: https://github.com/thewh1teagle/kokoro-onnx
from kokoro_onnx import Kokoro
import numpy as np
import re

# Initialize once at startup
kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

SENTENCE_END = re.compile(r'(?<=[.!?])\s+')

async def tts_stream(token_queue: asyncio.Queue) -> asyncio.AsyncGenerator[np.ndarray, None]:
    """Yields PCM audio chunks (np.float32, 24kHz) sentence by sentence."""
    text_buffer = ""

    async for token in token_queue_iter(token_queue):
        text_buffer += token
        sentences = SENTENCE_END.split(text_buffer)

        # Synthesize all complete sentences, keep last fragment
        for sentence in sentences[:-1]:
            sentence = sentence.strip()
            if sentence:
                samples, sample_rate = kokoro.create(sentence, voice="af_sarah", speed=1.0, lang="en-us")
                # samples is np.ndarray float32, sample_rate is 24000
                yield samples, sample_rate

        text_buffer = sentences[-1]  # Keep the incomplete final sentence

    # Synthesize any remaining text
    if text_buffer.strip():
        samples, sample_rate = kokoro.create(text_buffer.strip(), voice="af_sarah", speed=1.0, lang="en-us")
        yield samples, sample_rate
```

**Audio output:** Kokoro produces 24kHz float32 numpy arrays. Must be resampled to 8kHz before sending back to FreeSWITCH via mod_audio_stream.

### Pattern 5: Audio Resampling — 8kHz↔16kHz

**What:** PSTN delivers 8kHz PCM. Whisper needs 16kHz. Kokoro outputs 24kHz. Use soxr for all conversions — it is the reference implementation with no aliasing artifacts.

**Decision note:** D-05 mentions scipy or librosa, but research confirms soxr is superior for voice quality and handles the 2:1 integer ratio cleanly. Recommend soxr; scipy is acceptable fallback.

```python
# Source: https://github.com/dofuuz/python-soxr
import soxr
import numpy as np

# 8kHz PCM int16 → 16kHz float32 for Whisper
def upsample_for_stt(pcm_8k: bytes) -> np.ndarray:
    audio = np.frombuffer(pcm_8k, dtype=np.int16).astype(np.float32) / 32768.0
    audio_16k = soxr.resample(audio, 8000, 16000, quality="HQ")
    return audio_16k  # float32, 16kHz

# For streaming (better for real-time chunks):
resampler = soxr.ResampleStream(8000, 16000, 1, dtype="float32", quality="HQ")
def upsample_chunk(chunk: bytes) -> np.ndarray:
    audio = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
    return resampler.resample_chunk(audio)

# 24kHz float32 Kokoro output → 8kHz int16 for FreeSWITCH
def downsample_for_fs(samples: np.ndarray) -> bytes:
    audio_8k = soxr.resample(samples, 24000, 8000, quality="HQ")
    return (audio_8k * 32767).astype(np.int16).tobytes()
```

**scipy fallback** (if soxr unavailable):
```python
from scipy.signal import resample_poly
# 8kHz → 16kHz: exact 2:1 ratio, clean for integer multiples
audio_16k = resample_poly(audio_8k, up=2, down=1)
```

### Pattern 6: OpenAI-Compatible LLM Streaming

**What:** Stream LLM token output using the openai Python SDK with `stream=True`. Works with any OpenAI-compatible endpoint — local Ollama, OpenAI API, etc.

**When to use:** For all LLM calls in the voice pipeline (D-11).

```python
# Source: https://developers.openai.com/api/reference/python
from openai import AsyncOpenAI

# Configure once — works with Ollama, OpenAI, or any compatible API
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",  # Ollama example; swap for OpenAI
    api_key="ollama"  # Placeholder for local models
)

async def stream_llm_response(transcript: str, history: list) -> asyncio.AsyncGenerator[str, None]:
    messages = history + [{"role": "user", "content": transcript}]
    async with client.chat.completions.create(
        model="llama3.2",
        messages=messages,
        stream=True,
        max_tokens=150,   # Keep responses short for voice
        temperature=0.7,
    ) as stream:
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
```

### Pattern 7: Docker Compose Setup

**What:** FreeSWITCH must run in a Docker container with `--network=host` (required for RTP port range). mod_audio_stream must be compiled into the image. Python orchestrator runs on host during dev.

**Critical:** The FreeSWITCH apt repository requires a free SignalWire Personal Access Token. Register at https://id.signalwire.com — this is necessary even for the open-source package.

```yaml
# docker/docker-compose.yml
version: "3.9"
services:
  freeswitch:
    build: ./freeswitch
    network_mode: "host"          # REQUIRED for RTP port range (16384-32768/udp)
    volumes:
      - ./config/freeswitch:/etc/freeswitch  # Config hot-reload during dev
      - freeswitch-logs:/var/log/freeswitch
    environment:
      - SIGNALWIRE_TOKEN=${SIGNALWIRE_TOKEN}  # Required for apt repo
    ports: []  # No ports needed with host networking
    healthcheck:
      test: ["CMD", "fs_cli", "-x", "status"]
      interval: 10s
      timeout: 5s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  freeswitch-logs:
  redis-data:
```

```dockerfile
# docker/freeswitch/Dockerfile
FROM debian:12-slim

ARG SIGNALWIRE_TOKEN
# Add SignalWire FreeSWITCH repository
RUN apt-get update && apt-get install -y wget gnupg && \
    TOKEN=${SIGNALWIRE_TOKEN} && \
    wget --http-user=signalwire --http-password=$TOKEN -O /usr/share/keyrings/signalwire-freeswitch-repo.gpg \
    https://freeswitch.signalwire.com/repo/deb/debian-release/bookworm/public.gpg && \
    echo "machine freeswitch.signalwire.com login signalwire password $TOKEN" > /etc/apt/auth.conf && \
    echo "deb [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] \
    https://freeswitch.signalwire.com/repo/deb/debian-release/bookworm/ bookworm main" \
    > /etc/apt/sources.list.d/freeswitch.list && \
    apt-get update && apt-get install -y freeswitch-meta-all

# Build mod_audio_stream from source
RUN apt-get install -y git cmake build-essential libfreeswitch-dev && \
    git clone https://github.com/amigniter/mod_audio_stream.git /tmp/mod_audio_stream && \
    cd /tmp/mod_audio_stream && mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc) && \
    cp mod_audio_stream.so /usr/lib/freeswitch/mod/

CMD ["freeswitch", "-nonat"]
```

### Anti-Patterns to Avoid

- **Sequential pipeline:** Never wait for full STT completion before calling LLM. Sequential delivery takes 2-4s — calls will sound robotic and callers will hang up.
- **Raw SWIG ESL bindings:** `con.connected` returns True even when disconnected. Use Genesis.
- **G.711 direct to Whisper:** Never feed 8kHz audio to faster-whisper without resampling. STT accuracy will be ~6-10% WER, effectively broken.
- **VAD-only barge-in without grace window:** Add a 500ms grace window after TTS starts before enabling barge-in. Without it, the first TTS audio chunk triggers immediate interruption.
- **docker compose with published RTP ports:** Port mapping 16384-32768/udp will freeze Docker. Use `network_mode: host` for FreeSWITCH.
- **Not verifying ESL connection:** Always send `api status` after connecting and verify response before sending originate commands.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Real-time STT chunking | Custom audio buffer + Whisper segment parser | `whisper_streaming` / `OnlineASRProcessor` | "Local agreement policy" avoids mid-word cuts; handles silence correctly; battle-tested against edge cases |
| Audio resampling | Custom numpy interpolation | `soxr.ResampleStream` | soxr is the reference implementation; custom polyphase filters introduce aliasing artifacts that degrade STT accuracy |
| SIP/RTP media handling | Python SIP library (pjsua2) | FreeSWITCH | PSTN codec edge cases (DTMF, hold, codec renegotiation) require a production softswitch |
| WebSocket audio protocol for FS | Custom binary framing | `mod_audio_stream` | Handles buffer sizing, heartbeat, binary/base64, reconnection |
| OpenAI-compatible streaming | Manual SSE parsing + delta accumulation | `openai` Python SDK | SDK handles stream reconnection, delta accumulation, error retries |
| FreeSWITCH ESL protocol | Raw TCP ESL protocol parser | Genesis | ESL protocol has edge cases (event accumulation, multi-line headers); Genesis handles them |
| Sentence boundary detection for TTS | Regex heuristics | NLTK `sent_tokenize` or simple punctuation split | Not critical to hand-roll at Phase 1 scale; regex `[.!?]\s+` is acceptable for MVP |

**Key insight:** The audio pipeline has several layers of protocol complexity (ESL over TCP, PCM over WebSocket, codec conversion). Each hand-rolled layer multiplies debugging surface area. Use the existing implementations for each protocol boundary.

---

## Common Pitfalls

### Pitfall 1: mod_audio_stream Licensing Confusion

**What goes wrong:** Multiple forks of mod_audio_stream exist. The most-referenced version (amigniter) is open source but requires building from source. Another version referenced in the cyberpunk.tools tutorial mentions "10 licenses" — this is a commercial fork.

**Why it happens:** The module appears in several GitHub repos and blog posts with inconsistent licensing information.

**How to avoid:** Use the open-source fork at `github.com/amigniter/mod_audio_stream`. Build it into the FreeSWITCH Docker image from source. Do not use the commercial version.

**Warning signs:** Any reference to license counts or paid access for mod_audio_stream is the commercial fork.

### Pitfall 2: FreeSWITCH ESL Authentication Failure in Docker

**What goes wrong:** Genesis cannot connect to ESL on port 8021. The default password is "ClueCon" and the default ESL config binds to localhost only (`::1` in IPv6). Inside Docker, the Python orchestrator on the host cannot reach it.

**Why it happens:** FreeSWITCH default config only allows ESL connections from localhost. Docker networking means the host is not localhost from FreeSWITCH's perspective.

**How to avoid:** In `autoload_configs/event_socket.conf.xml`, set `listen-ip` to `0.0.0.0` (or the Docker bridge IP). With `network_mode: host`, localhost works.

```xml
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="ClueCon"/>
    <param name="apply-inbound-acl" value="loopback.auto"/>
  </settings>
</configuration>
```

**Warning signs:** `ConnectionRefusedError` or `asyncio.TimeoutError` when Genesis tries to connect.

### Pitfall 3: RTP Port Range and Docker

**What goes wrong:** Publishing 16384-32768/udp in Docker Compose causes the host to stall or OOM trying to map the port range. No audio flows.

**Why it happens:** Docker's port proxy allocates one process per port. 16,384 ports = 16,384 processes.

**How to avoid:** Always use `network_mode: host` for FreeSWITCH. This is documented in the official FreeSWITCH Docker README.

**Warning signs:** Docker Compose hangs during `docker compose up`. Host becomes unresponsive. Or: calls connect but no audio (partial port mapping).

### Pitfall 4: Kokoro-ONNX Missing espeak-ng

**What goes wrong:** `kokoro-onnx` imports successfully but fails at synthesis with a phonemization error. Espeak-ng is a system dependency not installed by pip.

**Why it happens:** The ONNX model requires espeak-ng for text-to-phoneme conversion. It is not a Python dependency.

**How to avoid:** `apt-get install -y espeak-ng` in the Docker image. On macOS dev: `brew install espeak-ng`. Add to setup documentation.

**Warning signs:** `RuntimeError: espeak not found` or similar during first `kokoro.create()` call.

### Pitfall 5: Whisper Hallucination on Short Silence Chunks

**What goes wrong:** When VAD passes a short silence chunk or background noise to Whisper, the model generates plausible-sounding random text ("Thank you for watching", "Please subscribe"). This produces phantom responses from the agent.

**Why it happens:** Whisper was trained on YouTube data. It learned to complete audio with likely content.

**How to avoid:** Check `segment.no_speech_prob` for every segment. Discard segments where `no_speech_prob > 0.6`. Use `vad_filter=True` as the primary gate. Do not transcribe chunks shorter than 500ms.

**Warning signs:** Agent speaks without the user saying anything. Transcription log shows text after silence.

### Pitfall 6: SignalWire Token Required for FreeSWITCH Packages

**What goes wrong:** `apt-get install freeswitch` fails with authentication error. The FreeSWITCH apt repository requires a free SignalWire Personal Access Token (PAT) even for the open-source package.

**Why it happens:** SignalWire moved FreeSWITCH packages to an authenticated repository around 2021-2022.

**How to avoid:** Register for a free token at https://id.signalwire.com. Store as `SIGNALWIRE_TOKEN` environment variable. Reference in Dockerfile via `ARG`.

**Warning signs:** `apt-get update` fails with 401 Unauthorized on the FreeSWITCH repository.

### Pitfall 7: Python Version — Must be 3.11+

**What goes wrong:** Project constraint is Python 3.11+. The host machine runs Python 3.9.6. aiortc (Phase 2), faster-whisper, and Genesis have minimum version requirements around 3.9-3.10.

**Why it happens:** macOS ships with an older system Python. The dev machine is confirmed to have Python 3.9.6.

**How to avoid:** Use `uv` or `pyenv` to install Python 3.11 for this project. Do not use the system Python. Document in setup guide: `uv python install 3.11` or `pyenv install 3.11`.

**Warning signs:** Import errors for match statements or other 3.10+ features. aiortc install failure on Python <3.10.

### Pitfall 8: SIP Trunk Gateway Registration — External Profile

**What goes wrong:** Outbound calls fail because the SIP trunk gateway is not registered. FreeSWITCH uses the `external` sofia profile (port 5080) for SIP trunk connections, not the `internal` profile (port 5060).

**Why it happens:** FreeSWITCH's default config has two SIP profiles with different port/purpose. The external profile is for carrier trunks. Many tutorials accidentally configure gateways in the internal profile.

**How to avoid:** Place SIP trunk gateway config in `conf/sip_profiles/external.xml`. ESL originate command uses `sofia/gateway/<gateway-name>/+XXXXXXXXXX`.

**Warning signs:** `CHANNEL_HANGUP` immediately after `CHANNEL_ORIGINATE` with cause `NO_ROUTE_DESTINATION` or `SERVICE_UNAVAILABLE`.

---

## Code Examples

### Complete Outbound Call Origination via Genesis

```python
# Source: https://github.com/Otoru/Genesis (API verified)
import asyncio
from genesis import Inbound

async def make_call(destination: str, session_uuid: str) -> str:
    """Originate an outbound call. Returns FreeSWITCH call UUID."""
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        # Verify connection is alive
        status = await client.send("api status")
        if "UP" not in status:
            raise RuntimeError(f"FreeSWITCH not ready: {status}")

        # Originate with park — call waits in park until we start audio stream
        cmd = (
            f"api originate "
            f"{{session_uuid={session_uuid},ignore_early_media=true}}"
            f"sofia/gateway/sip_trunk/{destination} "
            f"&park()"
        )
        result = await client.send(cmd)
        # Result: "+OK <call-uuid>" or "-ERR <reason>"
        if not result.startswith("+OK"):
            raise RuntimeError(f"Originate failed: {result}")
        return result.split()[-1]
```

### SIP Trunk Gateway Configuration

```xml
<!-- config/freeswitch/sip_profiles/external.xml — gateway section -->
<gateways>
  <gateway name="sip_trunk">
    <param name="username" value="${TRUNK_USER}"/>
    <param name="password" value="${TRUNK_PASSWORD}"/>
    <param name="proxy" value="${TRUNK_HOST}"/>
    <param name="register" value="true"/>
    <param name="caller-id-in-from" value="false"/>
    <param name="codec-prefs" value="PCMU,PCMA"/>
    <!-- Explicit IPs prevent NAT autodiscovery failure on multi-homed hosts -->
    <param name="ext-sip-ip" value="${EXTERNAL_IP}"/>
    <param name="ext-rtp-ip" value="${EXTERNAL_IP}"/>
  </gateway>
</gateways>
```

### Switch.conf.xml — Session Limits

```xml
<!-- autoload_configs/switch.conf.xml — tune from defaults -->
<settings>
  <param name="max-sessions" value="1000"/>       <!-- default is 1000 -->
  <param name="sessions-per-second" value="30"/>  <!-- default is 30 -->
  <param name="rtp-start-port" value="16384"/>
  <param name="rtp-end-port" value="32768"/>
</settings>
```

### VAD + Barge-In State Machine

```python
import asyncio
from enum import Enum

class PipelineState(Enum):
    LISTENING = "listening"    # VAD active, feeding STT
    SPEAKING = "speaking"      # TTS playing, barge-in monitoring
    PROCESSING = "processing"  # STT→LLM in progress

class VoicePipeline:
    def __init__(self):
        self.state = PipelineState.LISTENING
        self.tts_cancel = asyncio.Event()

    async def on_audio_chunk(self, chunk: bytes, vad_is_speech: bool):
        if self.state == PipelineState.SPEAKING and vad_is_speech:
            # Barge-in: cancel TTS immediately
            self.tts_cancel.set()
            self.state = PipelineState.LISTENING

        elif self.state == PipelineState.LISTENING and vad_is_speech:
            await self.stt_buffer.put(chunk)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sequential STT→LLM→TTS pipeline | Streaming each stage (partial transcripts, token streaming, sentence-chunk TTS) | 2023-2024 | Latency drops from 2-4s to 300-800ms |
| openai/whisper directly | faster-whisper (CTranslate2) | 2023 | 4x faster, 60% less VRAM, built-in VAD |
| Whisper full-utterance batching | whisper_streaming / chunk-based with OnlineASRProcessor | 2023-2025 | Enables real-time partial transcripts |
| rhasspy/piper for TTS | Kokoro-ONNX (primary) / OHF-Voice piper1-gpl (if Piper needed) | rhasspy/piper archived Oct 2025 | Kokoro has better quality; piper's original repo is dead |
| greenswitch / raw ESL bindings for Python | Genesis (asyncio-native) | Genesis reached maturity 2025-2026 | No gevent monkey-patching; clean asyncio concurrency |
| whisper_streaming | SimulStreaming (Dominik Macháček, 2025) | 2025 | SimulStreaming faster and higher quality; whisper_streaming still widely supported |

**Deprecated/outdated:**
- `rhasspy/piper`: Archived October 2025 — read-only. Use OHF-Voice/piper1-gpl or Kokoro-ONNX.
- `openai/whisper` (original PyPI): 4x slower, no built-in VAD. Use faster-whisper.
- `switchio`: 43 open issues, last active development 2022. Use Genesis.
- `greenswitch` for new asyncio code: gevent monkey-patching incompatible with asyncio. Genesis only.

---

## Open Questions

1. **mod_audio_stream compilation in Docker**
   - What we know: Module must be built from source; it requires FreeSWITCH dev headers; amigniter is the open-source fork.
   - What's unclear: Build compatibility with FreeSWITCH 1.10.12 on Debian 12 has not been verified.
   - Recommendation: Build in CI early; if compilation fails, evaluate sptmru fork or FreeSWITCH's native `mod_http_cache` + direct RTP approach as fallback.

2. **Genesis originate command return format**
   - What we know: Genesis `Inbound.send()` accepts raw ESL command strings. The originate command returns "+OK <uuid>" or "-ERR <reason>".
   - What's unclear: Genesis may wrap the response in an object rather than a raw string — needs verification against actual Genesis 2026.3.21 API.
   - Recommendation: Write a minimal ESL connectivity test in Wave 0 to verify the exact response format before building call control logic on top.

3. **mod_audio_stream bidirectional audio — base64 vs raw binary**
   - What we know: Version 1.0.3+ supports both base64-encoded JSON response and raw binary WebSocket frames.
   - What's unclear: Whether `audioDataType: "raw"` in the JSON response envelope is reliably decoded by current mod_audio_stream build.
   - Recommendation: Start with base64 encoding (more explicit, easier to debug); optimize to raw binary after the pipeline is working.

4. **Kokoro-ONNX model download path**
   - What we know: Requires `kokoro-v1.0.onnx` and `voices-v1.0.bin` files; not downloaded by pip install.
   - What's unclear: Exact download URL / HuggingFace path for the ONNX model files.
   - Recommendation: Document the download step in setup guide. Model files live at `https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX`. Include `huggingface_hub` download in `holler init`.

5. **Python 3.11 on dev machine**
   - What we know: Dev machine runs macOS with Python 3.9.6 (Apple system Python). Project requires 3.11+.
   - What's unclear: Whether uv is installed or preferred over pyenv.
   - Recommendation: Add `uv python install 3.11 && uv venv --python 3.11` as first step in setup guide. Plan must include this.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | FreeSWITCH container | Yes | 29.1.5 | — |
| Docker Compose | Multi-service dev stack | Yes | v5.0.1 | — |
| Python 3.11+ | Project constraint | No | 3.9.6 (system) | Install via uv or pyenv |
| uv | Python package management | No | — | pip (already present) |
| Redis CLI | Redis dev access | No | — | `docker exec redis redis-cli` |
| FreeSWITCH | Softswitch | No | — | Runs in Docker container |
| espeak-ng | Kokoro-ONNX phonemization | No | — | Install via apt in Docker; brew install on macOS |
| SIPp | SIP load testing | No | — | Defer to post-Phase-1; manual testing sufficient for Phase 1 |
| CUDA / GPU | STT acceleration | No | M4 Pro (Apple Silicon) | CPU mode: `device="cpu", compute_type="int8"` — adequate for dev/single call |
| SignalWire PAT token | FreeSWITCH apt repo | Unknown | — | Required; register free at id.signalwire.com |

**Missing dependencies with no fallback:**
- **SignalWire PAT token**: Required to install FreeSWITCH from official packages. Must register at https://id.signalwire.com before running Docker build. Free registration.
- **Python 3.11+**: System Python 3.9.6 does not meet project constraint. Must install via `uv python install 3.11` or pyenv before Phase 1 work begins.

**Missing dependencies with fallback:**
- **GPU/CUDA**: Apple M4 Pro can run faster-whisper in CPU mode (`compute_type="int8"`). STT latency will be ~300-400ms (vs ~100ms GPU) — acceptable for dev/demo on single call. Multi-call GPU acceleration is Phase 2 concern.
- **Redis CLI**: Use `docker exec -it holler-redis-1 redis-cli` for dev access.

---

## Sources

### Primary (HIGH confidence)
- [Genesis GitHub — v2026.3.21](https://github.com/Otoru/Genesis) — API patterns, asyncio modes
- [amigniter/mod_audio_stream GitHub](https://github.com/amigniter/mod_audio_stream) — WebSocket protocol, dialplan, audio format
- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper) — transcribe() generator API, VAD filter, model options
- [kokoro-onnx GitHub (thewh1teagle)](https://github.com/thewh1teagle/kokoro-onnx) — TTS API, model init, audio output
- [python-soxr GitHub](https://github.com/dofuuz/python-soxr) — ResampleStream API for real-time resampling
- [FreeSWITCH Docker README](https://github.com/signalwire/freeswitch/blob/master/docker/README.md) — host networking requirement, port config
- [FreeSWITCH Gateways Configuration docs](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Configuration/Sofia-SIP-Stack/Gateways-Configuration_7144069/) — SIP trunk gateway XML
- [FreeSWITCH Event Socket Library docs](https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Client-and-Developer-Interfaces/Event-Socket-Library/) — ESL originate command format
- [Concept brief latency budget](file:///Users/paul/paul/brains/docs/drafts/2026-03-24-agentic-telecom-concept-brief.html) — VAD <50ms, STT ~100-200ms, LLM ~200-400ms, TTS ~100-150ms
- Project STACK.md (2026-03-24) — Pre-verified library versions and alternatives
- Project ARCHITECTURE.md (2026-03-24) — Component boundaries and data flow
- Project PITFALLS.md (2026-03-24) — 18 documented pitfalls with mitigations

### Secondary (MEDIUM confidence)
- [whisper_streaming GitHub](https://github.com/ufal/whisper_streaming) — OnlineASRProcessor chunk-based API
- [Cyberpunk.tools: Add AI Voice Agent to FreeSWITCH](https://www.cyberpunk.tools/jekyll/update/2025/11/18/add-ai-voice-agent-to-freeswitch.html) — Dialplan pattern for mod_audio_stream
- [OpenAI streaming docs](https://developers.openai.com/api/docs/guides/streaming-responses) — Stream API delta format
- [python-soxr PyPI](https://pypi.org/project/soxr/) — version and API

### Tertiary (LOW confidence — verify before implementing)
- [sptmru/freeswitch_mod_audio_stream](https://github.com/sptmru/freeswitch_mod_audio_stream) — Alternative fork, status unclear
- mod_audio_stream v1.0.3 raw binary response format — mentioned in GitHub issue #72, not formally documented

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified in STACK.md with sources; Genesis, faster-whisper, kokoro-onnx confirmed
- FreeSWITCH integration: HIGH — official docs, Docker README, ESL docs all reviewed
- mod_audio_stream protocol: MEDIUM — documented behavior verified; build compatibility with 1.10.12 unverified
- Audio resampling: HIGH — soxr is the reference implementation; verified API
- Voice pipeline patterns: MEDIUM-HIGH — patterns from multiple production implementations; exact Genesis API return format needs Wave 0 verification
- Environment gaps: HIGH — verified directly on target machine

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (30 days for this relatively stable stack)

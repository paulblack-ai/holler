# Stack Research

**Domain:** Self-hosted agentic telecom infrastructure (voice + SMS for AI agents)
**Researched:** 2026-03-24
**Confidence:** MEDIUM-HIGH (verified via official repos and release pages; some version numbers cross-checked against PyPI/GitHub tags)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| FreeSWITCH | 1.10.12 (Aug 2024) | SIP softswitch, call routing, media processing | Most scalable open-source softswitch; modular architecture handles thousands of concurrent calls; native WebRTC support via mod_verto; strong codec support; founded by Anthony Minessale, actively maintained by SignalWire. Chosen over Asterisk because Asterisk is monolithic and harder to scale beyond a few hundred concurrent calls. |
| faster-whisper | 1.2.1 (Oct 2024) | Speech-to-text, streaming transcription | CTranslate2-based reimplementation of Whisper — 4x faster than openai/whisper at same accuracy, uses less VRAM. Built-in Silero VAD v6, batched inference for throughput. The right choice over whisper.cpp when Python orchestration is primary because Python API is first-class; whisper.cpp requires FFI or subprocess. |
| whisper.cpp | 1.8.4 (Mar 2025) | STT alternative for latency-critical paths or CPU-only deployments | Pure C/C++ with no Python overhead; ~5-6x faster than vanilla Whisper; built-in VAD (Silero 6.2); stream example supports real-time mic capture. Use this for the C/Rust voice pipeline component where sub-200ms STT is required. |
| Kokoro (kokoro-onnx) | 0.5.x | Primary TTS — fast, lightweight, CPU-capable | 82M parameter model; 96x real-time on GPU, real-time on CPU; Apache 2.0 licensed; 8 languages, 54 voices in v1.0; ~100-300ms latency. Best balance of speed, quality, and resource cost for 1-16 concurrent calls. ONNX version avoids PyTorch dependency for deployment. |
| Orpheus TTS | 3B model (Mar 2025 release) | Premium TTS for high-quality interactions | Llama-3b backbone; ~200ms streaming latency; zero-shot voice cloning; emotion/intonation control via tags; Apache 2.0; trained on 100k+ hours of English. Use when voice quality matters more than resource cost (RTX 4090/M4 Max profile). |
| Janus Gateway | 1.4.0 (Feb 2026) | WebRTC media server for agent-to-agent mesh | Plugin-based architecture; SIP gateway plugin bridges WebRTC to SIP/FreeSWITCH; actively maintained by Meetecho; production-proven; C codebase so low overhead. Handles the WebRTC-to-PSTN bridge and agent mesh without adding a cloud dependency. |
| Python | 3.11+ | Core orchestration language | asyncio is table stakes for concurrent call handling; ecosystem breadth for LLM integration, tooling, and testing; 3.11 specifically for performance improvements vs 3.10. |
| Redis | 7.x | Session state, number pool, DLR tracking | Sub-millisecond reads for call state; natural fit for ephemeral number pool (EXPIRE-based cleanup); used by Jasmin for delivery receipt correlation; pubsub for cross-component signaling. |

### SIP / FreeSWITCH Integration

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Genesis | 2026.3.21 (Mar 2026) | FreeSWITCH ESL via asyncio | PRIMARY Python ESL choice. Built on asyncio, actively maintained (29 releases, latest March 2026), MIT license, OpenTelemetry support. Use for all inbound/outbound ESL commands from Python orchestrator. |
| greenswitch | 0.0.19 (Apr 2025) | FreeSWITCH ESL via gevent | FALLBACK if gevent-based concurrency is preferred. Battle-tested, production-stable, but gevent is a heavier dependency than asyncio. Supports Python 3.6-3.10 only. |
| mod_verto | (built into FreeSWITCH) | WebRTC endpoint in FreeSWITCH | Native FreeSWITCH module for WebRTC-to-SIP bridging. Used for agent-to-agent calls over WebRTC mesh. Depends on mod_rtc for secure media. |

### SMS Stack

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| smpplib | 2.2.4 (Jan 2025) | SMPP 3.4 client | SMPP ESME connections to SMS gateway or carrier SMSC. Synchronous; use in threaded executor or wrap with asyncio.run_in_executor. Stable, production-tested. |
| aiosmpplib | 0.7.x | Async SMPP 3.4 client | Preferred if the SMS path is high-volume and needs native asyncio. Supports message segmentation reassembly and delivery receipt correlation. No third-party deps. |
| Jasmin | 0.11.0 (Nov 2023) | Full SMS gateway (SMPP + HTTP + routing) | Use when a full SMS broker is needed with routing rules, rate limiting, and delivery tracking. Python/Twisted. Provides both SMPP server and HTTP API. Note: last release Nov 2023 — evaluate maintenance status before depending on it for core path. |
| gammu | (system package) | GSM modem interface | For deployments with physical GSM hardware (SIM card modem). Python bindings via python-gammu. Fallback/offline path when SMPP trunk is unavailable. |

### Voice Pipeline Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| silero-vad | 6.2.1 (Feb 2026) | Voice activity detection | Detect speech onset/offset for STT triggering. <1ms per 30ms audio chunk on CPU. Use before feeding audio to faster-whisper to avoid transcribing silence. MIT license. Built into faster-whisper as of v1.1.0 — often no separate integration needed. |
| aiortc | 1.14.0 (Oct 2025) | Python WebRTC (asyncio) | For implementing WebRTC peer connections directly in Python (agent-to-agent without Janus). Requires Python >=3.10. Use when direct P2P between Python agents is needed without a media server. |
| sounddevice | 0.4.x | Audio I/O (dev/test) | Capture/playback audio in Python during development and testing. Not used in production voice pipeline (FreeSWITCH handles media). |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker Compose | Local stack orchestration | FreeSWITCH + Janus + Redis + Python orchestrator as services. Use volume mounts for FreeSWITCH config during development. |
| pytest-asyncio | Testing async voice pipeline | Required for testing asyncio-based FreeSWITCH ESL handlers. |
| uv | Python package/env management | Faster pip alternative; use for reproducible installs in CI and Docker. |
| SIPp | SIP load testing | Simulate inbound/outbound calls against FreeSWITCH for latency benchmarking. |

---

## Installation

```bash
# Python core
pip install faster-whisper>=1.2.1
pip install kokoro-onnx>=0.5.0
pip install genesis>=2026.3.21   # FreeSWITCH ESL asyncio
pip install smpplib>=2.2.4
pip install aiosmpplib>=0.7.0
pip install silero-vad>=6.2.1
pip install redis>=5.0.0
pip install aiortc>=1.14.0

# For Orpheus TTS (heavy: requires vllm)
pip install vllm
# Model: canopylabs/orpheus-3b-0.1-ft (via huggingface_hub)

# For whisper.cpp (C binary, build from source or use prebuilt)
# git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp && make

# System dependencies (Debian/Ubuntu)
apt-get install -y freeswitch freeswitch-mod-verto \
                   espeak-ng \
                   redis-server
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| FreeSWITCH | Asterisk / FreePBX | Smaller deployments (<20 concurrent calls), teams with existing Asterisk expertise, simpler IVR use cases. Asterisk is easier to configure for basic scenarios but doesn't scale as well. |
| FreeSWITCH | Kamailio | When you only need SIP proxy/routing without media handling. Kamailio is a SIP proxy, not a softswitch — it doesn't do media. Use Kamailio in front of FreeSWITCH if you need advanced SIP routing at scale. |
| faster-whisper | whisper.cpp | When the voice pipeline must be implemented in C/Rust with zero Python in the hot path. whisper.cpp is the right choice for the Rust voice pipeline component described in CLAUDE.md. Use faster-whisper for Python orchestration layer. |
| Kokoro (ONNX) | Piper (OHF-Voice piper1-gpl) | When you need extremely low VRAM (Piper is ~50MB) or target embedded/edge hardware. Piper1-gpl (v1.4.1, Feb 2026) is the active successor to rhasspy/piper, but it's seeking maintainers. Kokoro has better voice quality and active development. |
| Kokoro (ONNX) | Orpheus TTS | When voice quality and naturalness are the top priority and a 3B+ GPU is available. Orpheus produces human-sounding speech with emotion control but needs ~8GB VRAM for the 3B model. Kokoro is the default; Orpheus is the premium option. |
| Genesis (ESL asyncio) | greenswitch (gevent) | When the codebase already uses gevent heavily (e.g., legacy Celery with gevent worker). greenswitch is production-proven but gevent introduces monkey-patching complications. |
| Janus Gateway | LiveKit | When you need a fully featured WebRTC SFU with agent framework, SIP integration, and managed scaling. LiveKit is excellent for agent voice pipelines and supports self-hosted deployment. However, it introduces a Go runtime and is a larger abstraction than Janus. For Holler's architecture (FreeSWITCH owns SIP; Janus owns WebRTC bridging), Janus is the lighter fit. |
| smpplib / aiosmpplib | Jasmin | When a full SMS broker with routing, rate limiting, and multi-SMSC support is needed. Jasmin adds RabbitMQ + Redis dependencies and is a standalone service. Use Jasmin if SMS routing complexity warrants it; use smpplib directly for simple send/receive. |
| Redis | PostgreSQL | When call state needs to survive reboots or be audited. Redis is faster for sub-second call state but is ephemeral by default. Use Redis for hot call state + Postgres for call records/audit log. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| rhasspy/piper (original) | Archived October 2025, no new releases. Read-only. | OHF-Voice/piper1-gpl (v1.4.1, Feb 2026) if you need Piper specifically, or Kokoro-ONNX as the primary TTS. |
| openai/whisper (original PyPI package) | 4x slower than faster-whisper, higher VRAM, no built-in VAD. Still actively updated but no performance advantages. | faster-whisper for Python, whisper.cpp for C/Rust pipeline. |
| Twilio / Vonage / Vapi / Bland AI / Retell | Cloud vendor dependency — adds per-minute cost, routes call audio through third-party servers, violates "permissionless core" principle. | FreeSWITCH + SIP trunk. |
| WebRTC without SRTP/DTLS | Security regression; modern WebRTC mandates encryption. Janus and FreeSWITCH both enforce it by default. | Use Janus or FreeSWITCH mod_verto with TLS/SRTP enabled (default in both). |
| Asterisk for STIR/SHAKEN | Asterisk has native STIR/SHAKEN (res_stir_shaken) but the implementation has known issues with third-party certificate authorities and has been deprecated in favor of a rewrite in Asterisk 21. | FreeSWITCH with a dedicated STIR/SHAKEN library (community module); or handle STIR/SHAKEN signing at the SIP trunk level with your carrier. |
| switchio | 43 open issues, unclear maintenance trajectory, last meaningful development was 2022. | Genesis (actively maintained, 29 releases, latest March 2026). |
| gevent for new code | Monkey-patching creates subtle bugs in asyncio contexts; Python's native asyncio is now the standard for async I/O. | asyncio + Genesis for FreeSWITCH ESL. |

---

## Stack Patterns by Variant

**If running on CPU-only hardware (no GPU):**
- Use kokoro-onnx (quantized, ~80MB, real-time on modern CPU) for TTS
- Use faster-whisper with `device="cpu"` and `compute_type="int8"` for STT
- Limit to 2-4 concurrent calls per CPU core
- Avoid Orpheus TTS (requires GPU for acceptable latency)

**If running on RTX 3060 (12GB VRAM):**
- Use faster-whisper with `device="cuda"` and `compute_type="float16"` for STT (distil-large-v3 model)
- Use kokoro-onnx (GPU-accelerated) for TTS
- Target 8-16 concurrent calls
- Orpheus 1B variant may be feasible if VRAM is not shared with STT

**If running on RTX 4090 / M4 Max:**
- Use faster-whisper `large-v3-turbo` for best STT accuracy
- Use Orpheus 3B for premium voice quality
- Target 32-64 concurrent calls
- Run local LLM (e.g., Llama 3.1 70B quantized) for closed-loop inference

**For agent-to-agent WebRTC mesh (no PSTN):**
- Use aiortc for Python-native peer connections between agent processes
- Or use Janus room plugin for multi-agent conference rooms
- No FreeSWITCH or SIP trunk required for this path
- No TCPA/STIR/SHAKEN compliance required (not PSTN)

**For SMS via GSM modem (no carrier SMPP account):**
- Use gammu-smsd (system daemon) + python-gammu bindings
- Suitable for low-volume, offline, or development use
- Not suitable for >100 SMS/hour (hardware throughput limit)

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| faster-whisper 1.2.1 | CTranslate2 4.x, CUDA 12, cuDNN 9 | GPU inference requires CUDA 12 + cuDNN 9 specifically. CUDA 11 not supported in CTranslate2 4.x. |
| aiortc 1.14.0 | Python >=3.10 | Will not install on Python 3.9 or earlier. |
| silero-vad 6.2.1 | Python 3.8-3.15 | Already bundled into faster-whisper; only install separately for standalone VAD use. |
| Genesis | Python 3.9+ (estimated) | Poetry-managed; check pyproject.toml for exact constraint. Latest release 2026-03-21. |
| smpplib 2.2.4 | Python 2.7, 3.9-3.13 | Broad compatibility; SMPP 3.4 only (SMPP 5.0 not supported). |
| kokoro-onnx | Python 3.8+ | Requires espeak-ng system package for phonemization. |
| FreeSWITCH 1.10.12 | Debian 11/12, Ubuntu 20.04/22.04 | ARM64 support added in 1.10.12. OpenSSL 3 support added in 1.10.10. |
| Janus 1.4.0 | libsrtp2, libusrsctp, libwebsockets | Build from source on most distros; Docker image available from Meetecho. |

---

## Sources

- **faster-whisper GitHub releases** — v1.2.1 confirmed (HIGH confidence): https://github.com/SYSTRAN/faster-whisper/releases
- **whisper.cpp GitHub releases** — v1.8.4 confirmed (HIGH confidence): https://github.com/ggml-org/whisper.cpp/releases
- **Janus Gateway GitHub tags** — v1.4.0 confirmed Feb 2026 (HIGH confidence): https://github.com/meetecho/janus-gateway/tags
- **FreeSWITCH GitHub releases** — v1.10.12 confirmed Aug 2024 (HIGH confidence): https://github.com/signalwire/freeswitch/releases
- **Genesis GitHub** — v2026.3.21 confirmed Mar 2026 (HIGH confidence): https://github.com/Otoru/Genesis
- **greenswitch PyPI** — v0.0.19 confirmed Apr 2025 (HIGH confidence): https://pypi.org/project/greenswitch/
- **smpplib PyPI** — v2.2.4 confirmed Jan 2025 (HIGH confidence): pip index versions smpplib
- **Jasmin GitHub releases** — v0.11.0 confirmed Nov 2023 (HIGH confidence): https://github.com/jookies/jasmin/releases
- **silero-vad PyPI** — v6.2.1 confirmed Feb 2026 (MEDIUM confidence, via WebSearch)
- **aiortc** — v1.14.0 confirmed Oct 2025 (MEDIUM confidence, via WebSearch)
- **Kokoro Hugging Face / GitHub** — 82M params, Apache 2.0, kokoro-onnx available (HIGH confidence): https://github.com/hexgrad/kokoro
- **Orpheus TTS GitHub** — 3B Llama-based, Apache 2.0, Mar 2025 release (HIGH confidence): https://github.com/canopyai/Orpheus-TTS
- **piper1-gpl GitHub** — v1.4.1 confirmed Feb 2026, seeking maintainers (HIGH confidence): https://github.com/OHF-Voice/piper1-gpl
- **rhasspy/piper** — archived Oct 6, 2025 (HIGH confidence): https://github.com/rhasspy/piper
- **AssemblyAI voice AI stack guide 2026** — architecture patterns and latency benchmarks (MEDIUM confidence): https://www.assemblyai.com/blog/the-voice-ai-stack-for-building-agents
- **CTranslate2 CUDA 12 requirement** — documented in faster-whisper README (HIGH confidence)
- **Samcom / Samcom Technologies comparison** — FreeSWITCH vs Asterisk 2026 (LOW confidence, single commercial source): https://www.samcomtechnologies.com/blog/asterisk-vs-freeswitch-in-2026-which-voip-platform-should-you-choose

---

*Stack research for: self-hosted agentic telecom infrastructure (Holler)*
*Researched: 2026-03-24*

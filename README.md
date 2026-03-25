# holler

Open-source voice and text infrastructure for AI agents. Permissionless core. Community-built country modules.

> You don't need permission to holler.

## What this is

Holler gives AI agents a mouth and an ear. It's a self-hosted telecom stack that lets autonomous agents make phone calls, send texts, and hold voice conversations — using hardware you own, with no vendor accounts and no human in the loop.

The phone network was built for humans. Holler is a bridge from that infrastructure into whatever comes next.

## System requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | macOS 13+, Ubuntu 22.04+, any Linux with Docker | Same |
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| GPU | None (CPU inference works) | Any GPU with 8+ GB VRAM, or Apple Silicon with 16+ GB unified memory |
| Disk | 10 GB (models + Docker images) | 20 GB |
| Docker | Docker Desktop or Docker Engine + Compose | Same |

Apple Silicon (M1/M2/M3/M4) runs the full stack well on CPU. GPU acceleration via Metal is supported by faster-whisper and Kokoro.

## Prerequisites

- **Python 3.11+**
- **Docker** — Docker Desktop (macOS/Windows) or Docker Engine + Compose (Linux). FreeSWITCH and Redis run as containers.
- **A SIP trunk account** — the single external dependency. Any commodity SIP provider ([VoIP.ms](https://voip.ms), [Bitcall](https://bitcall.io), [Telnyx](https://telnyx.com), etc). ~$15 prepaid gets you started.
- **An OpenAI-compatible LLM endpoint** — default: [Ollama](https://ollama.com) on localhost (free, local). Also works with OpenAI, Anthropic (via adapter), vLLM, or any OpenAI-compatible API.

No vendor accounts required for the core stack. No SignalWire, no Twilio, no cloud APIs. Everything builds from public sources.

## Quick start

```bash
# Clone and install
git clone https://github.com/holler-ai/holler && cd holler
uv venv && source .venv/bin/activate    # or: python3 -m venv .venv && source .venv/bin/activate
uv pip install -e .                      # or: pip install -e .

# Pull a local LLM
ollama pull llama3.2

# Initialize (downloads voice models, starts FreeSWITCH + Redis)
holler init

# Configure your SIP trunk
holler trunk --host sip.voip.ms --user YOUR_USER --pass YOUR_PASS

# Make your first call
holler call +14155551234 --agent "Say hello and ask how their day is going."
```

Five minutes from clone to first call. No dashboard. No account creation. No OAuth flow.

**First build note:** `holler init` builds FreeSWITCH from source on first run (~15-25 min). Subsequent runs use the cached Docker image and start in seconds.

## How it works

| Layer | What | How |
|---|---|---|
| Agent interface | LLM emits tool calls (`call`, `sms`, `transfer`) | Python SDK / CLI |
| Voice pipeline | Local STT + TTS, real-time streaming | faster-whisper + Kokoro |
| Compliance | Per-country plugins in the call path | Community-contributed modules |
| Routing | FreeSWITCH softswitch | Self-hosted, open source |
| Transport | SIP trunk / GSM modem / WebRTC mesh | Your choice of on-ramp |

## Project structure

```
holler/
  core/
    voice/          # STT, TTS, VAD, pipeline, audio bridge
    freeswitch/     # ESL connection, event handling
    telecom/        # Number pool, sessions, routing, recording
    compliance/     # Gateway, consent DB, DNC, audit log
    agent/          # Tool definitions, executor, LLM adapters
    sms/            # SMPP client, delivery hooks
  countries/
    us/             # TCPA, DNC, time-of-day (implemented)
    _template/      # Scaffold for new country modules
  cli/              # CLI commands (init, trunk, call)
  main.py           # Application entry point
config/
  freeswitch/       # FreeSWITCH XML config
docker/             # Docker Compose + Dockerfile
```

## Country modules

The core is jurisdiction-agnostic. Compliance lives in country modules — community-contributed plugins that enforce local rules.

Currently implemented: `us` (TCPA, DNC, time-of-day restrictions).

No module for your country? [Build one.](CONTRIBUTING.md#country-modules) You know your local telecom rules better than anyone.

## Development

```bash
pip install -e ".[dev]"
pytest
```

See `.env.example` for all configuration options. Config is written to `.holler.env` by `holler init`.

## The bridge

This project might be obsolete in three years. Carriers might build agent-native interfaces. Something new might replace phone numbers entirely. That's fine. Holler is designed to be useful *now* — a bridge from the infrastructure that exists to whatever comes next. If it accelerates that transition, it did its job.

## Contributing

The highest-impact contribution is a country module for your jurisdiction. Start with a markdown file documenting the rules — the code comes later. Understanding your country's telecom regulations is the hard part. Turning that into a compliance gateway is the easy part.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

Apache 2.0. Fork it. Build on it. Make it yours.

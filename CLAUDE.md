# Holler

Open-source voice and text infrastructure for autonomous AI agents. Permissionless core. Community-built country modules.

## What This Is

A self-hosted telecom stack that treats phone calls and text messages as tool invocations — the same way an agent calls an API or reads a database. Bridge protocol from current phone infrastructure into an agentic future.

## Design Principles

1. **Permissionless core.** Runs on your hardware, zero vendor accounts. Voice processing, routing, session management — all local, all open-source.
2. **PSTN as a thin edge.** One SIP trunk is the only external dependency for reaching the phone network.
3. **Compliance as plugins.** Jurisdiction-specific rules enforced by community-contributed country modules in the call path. The core is jurisdiction-agnostic.
4. **Numbers as ephemeral resources.** Pooled, allocated per-interaction, released. Identity travels with the conversation, not the number.
5. **Multi-modal.** SMS, voice, WhatsApp — one agent session across channels.
6. **Agent-to-agent native.** WebRTC mesh between agents. PSTN only for the human edge.
7. **Easy to build, easy to leave.** Standard interfaces (SIP, WebRTC, SMPP). No lock-in.

## Core Stack

- **Softswitch:** FreeSWITCH (open source)
- **STT:** faster-whisper / Whisper.cpp (local)
- **TTS:** Piper / Kokoro / Orpheus (local)
- **Media:** WebRTC + RTP via Janus
- **SMS:** SMPP or GSM modem (gammu/kannel)
- **Agent interface:** Tool-use protocol — LLM emits call/sms/transfer actions
- **Language:** Python core (orchestration, agent interface) + C/Rust for latency-critical voice pipeline

## Architecture

```
Agent Runtime (LLM tool calls)
  → Telecom Abstraction Layer (number pool, session state, jurisdiction router)
    → Voice Pipeline (STT + TTS, fully local)
      → Compliance Gateway (per-country plugin, mandatory in call path)
        → SIP Softswitch (FreeSWITCH)
          → PSTN (SIP trunk) / GSM (modem) / Agent mesh (WebRTC)
```

## Country Module Pattern

```
holler/
  core/                  # Universal — softswitch, voice pipeline, agent interface
  countries/
    us/                  # TCPA, STIR/SHAKEN, state overlays, DNC
    uk/                  # Ofcom rules
    _template/           # Scaffold for new country module
  contrib/               # Community modules, experiments
```

Each country module is a compliance gateway plugin. Adding a new country = implementing a plugin interface, not modifying the core.

## Project Character

- Open source (Apache 2.0)
- Bridge protocol — honest about potentially being obsolete in 3 years
- Global-first — not US-centric, US is just one country module
- Onboarding should feel like: install, point at trunk, make a call. Four commands.
- Documentation voice: warm, direct, no corporate speak, technically honest
- "You don't need permission to holler."

## Concept Brief

Full concept exploration with architecture diagrams, compliance analysis, economics, and risk assessment lives at:
`/Users/paul/paul/brains/docs/seeds/holler-voice.html` (creative/brand)
`/Users/paul/paul/brains/docs/drafts/2026-03-24-agentic-telecom-concept-brief.html` (technical)

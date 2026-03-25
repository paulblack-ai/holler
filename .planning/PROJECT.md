# Holler

## What This Is

Open-source, self-hosted telecom infrastructure that gives AI agents the ability to make phone calls, send texts, and hold voice conversations — using hardware the operator owns, with no vendor accounts beyond a commodity SIP trunk. A bridge protocol from the current phone network into an agentic future.

## Core Value

An AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation — no vendor accounts, no API keys, no human in the loop.

## Current State

**v1.0 MVP shipped.** The core thesis is proven: an LLM can originate a compliant phone call or send an SMS through locally-hosted infrastructure using a single tool invocation.

- 4,994 lines of Python across 44 modules + 22 test files (264 tests passing)
- FreeSWITCH + Redis via Docker Compose, fully local STT (faster-whisper) + TTS (Kokoro-ONNX)
- Compliance-gated outbound path (TCPA, DNC, time-of-day, consent) — structurally impossible to bypass
- SMPP messaging with delivery tracking, inbound routing, compliance gate
- Tool-use protocol (call/sms/hangup/transfer) works with OpenAI, Anthropic, local Ollama
- Four-command onboarding: `pip install holler` -> `holler init` -> `holler trunk add` -> `holler call`

## Requirements

### Validated

- ✓ FreeSWITCH softswitch handles SIP call routing — v1.0
- ✓ SIP trunk integration for PSTN connectivity — v1.0
- ✓ Voice pipeline runs fully local (STT + TTS) with streaming architecture — v1.0
- ✓ Number pool management (checkout/release of DIDs per interaction) — v1.0
- ✓ Session state tracks conversation context across a call lifecycle — v1.0
- ✓ Jurisdiction router dispatches calls through per-country compliance gateways — v1.0
- ✓ US compliance gateway enforces TCPA, time-of-day, DNC — v1.0
- ✓ Country module plugin interface with scaffold template — v1.0
- ✓ Recording and live transcription pipeline — v1.0
- ✓ Consent/opt-out state machine enforced in call path (DTMF + STT) — v1.0
- ✓ Agent can make outbound voice call via tool invocation — v1.0
- ✓ Agent can send/receive SMS via SMPP — v1.0
- ✓ CLI onboarding in four commands — v1.0
- ✓ Tool-use protocol exposes call/sms/hangup/transfer as LLM tool invocations — v1.0
- ✓ LLM-agnostic agent interface (OpenAI, Anthropic, local Ollama) — v1.0

### Active

- [ ] Agent-to-agent direct communication via WebRTC (no PSTN)

### Out of Scope

- Cloud-hosted SaaS offering — this is self-hosted infrastructure, not a platform
- Building a carrier or acquiring telecom licenses — SIP trunk is the carrier interface
- Mobile app or end-user GUI — the "user" is an LLM, interface is tool-use protocol
- Custom LLM training — uses existing models (Whisper, Kokoro, general-purpose LLMs)
- WhatsApp / rich messaging channels — v1 focuses on voice + SMS, multi-modal channels are future work
- International compliance modules beyond US — community-contributed, not core v1 deliverable (template provided)

## Context

- The global telecom stack assumes a human at every endpoint. AI agents hitting the phone network today go through vendor chokepoints (Twilio, Vonage) that add cost, latency, data flow through third parties, and vendor lock-in.
- Emerging "AI voice" startups (Vapi, Bland AI, Retell) solve developer experience but replicate the structural dependency. Holler is infrastructure you own — closer to "Linux for telecom" than "AWS for telecom."
- Voice conversation latency budget is ~800ms for the full STT->LLM->TTS loop. Streaming throughout and local inference eliminate network round-trips.
- The project is explicitly a bridge protocol — designed to be useful now while the phone network evolves. May be obsolete in 3 years. That's fine.
- Hardware profile: RTX 3060+ for STT, CPU i7+ for TTS, RTX 4090/M4 Max for local LLM. 1-4 concurrent calls single GPU, 16-64 with multi-GPU.
- US is the hardest compliance jurisdiction (TCPA, STIR/SHAKEN, state overlays). Solving US compliance first makes other countries easier.
- Agent-to-agent communication will grow faster than agent-to-human. Building that path on WebRTC (free, no regulation) rather than PSTN is architecturally important.
- v1.0 shipped with 264 passing tests, 32/32 requirements satisfied, 0 integration gaps.

## Constraints

- **Language**: Python core (orchestration, agent interface) + C/Rust for latency-critical voice pipeline components
- **Softswitch**: FreeSWITCH (open source, mature, well-documented)
- **STT**: faster-whisper / Whisper.cpp (local inference only)
- **TTS**: Kokoro / Orpheus (local inference only)
- **Media**: WebRTC + RTP via Janus gateway
- **SMS**: SMPP protocol or GSM modem (gammu/kannel)
- **License**: Apache 2.0
- **Latency**: Full voice loop must complete in <800ms for natural conversation
- **No vendor accounts**: Core must function with zero external service accounts; SIP trunk is the single external dependency
- **Onboarding**: Install, point at trunk, make a call — four commands maximum

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FreeSWITCH over Asterisk/Kamailio | More scalable, better codec support, stronger WebRTC integration | ✓ Good — handles all v1 requirements |
| Compliance as mandatory call-path gateway, not optional middleware | Architecturally impossible to place non-compliant call; legal defense posture | ✓ Good — structural guarantee proven |
| Numbers as ephemeral pool, not per-agent allocation | Identity travels with conversation context, not with phone number; reduces DID costs | ✓ Good — Redis SPOP/SADD atomic and fast |
| Python core + C/Rust voice pipeline | Python for rapid agent interface iteration; C/Rust only where latency budget demands it | ✓ Good — pure Python sufficient for v1 |
| Local-first inference (no cloud STT/TTS) | Data sovereignty, latency reduction, no per-minute API costs | ✓ Good — faster-whisper + Kokoro work well |
| Genesis for ESL (asyncio-native) | Fits async codebase, actively maintained, MIT license | ✓ Good — clean integration |
| aiosmpplib for SMS | Async-native SMPP, fits established asyncio pattern | ✓ Good — delivery receipts work cleanly |
| Click for CLI | Multi-command support, mature, minimal deps | ✓ Good — four-command flow works |
| OpenAI format as canonical tool schema | Universal compatibility, Anthropic adapter is ~10 lines | ✓ Good — LLM-agnostic proven |
| Append-only consent DB | Legal requirement for audit trail, no UPDATE/DELETE | ✓ Good — immutable record maintained |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-25 after v1.0 milestone completion*

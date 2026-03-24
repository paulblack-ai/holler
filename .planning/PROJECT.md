# Holler

## What This Is

Open-source, self-hosted telecom infrastructure that gives AI agents the ability to make phone calls, send texts, and hold voice conversations — using hardware the operator owns, with no vendor accounts beyond a commodity SIP trunk. A bridge protocol from the current phone network into an agentic future.

## Core Value

An AI agent can make a phone call from locally-hosted infrastructure with a single tool invocation — no vendor accounts, no API keys, no human in the loop.

## Requirements

### Validated

- ✓ FreeSWITCH softswitch handles SIP call routing — Phase 1
- ✓ SIP trunk integration for PSTN connectivity — Phase 1
- ✓ Voice pipeline runs fully local (STT + TTS) with streaming architecture — Phase 1 (latency pending live verification)
- ✓ Number pool management (checkout/release of DIDs per interaction) — Phase 2
- ✓ Session state tracks conversation context across a call lifecycle — Phase 2
- ✓ Jurisdiction router dispatches calls through per-country compliance gateways — Phase 2
- ✓ US compliance gateway enforces TCPA, STIR/SHAKEN, time-of-day, DNC — Phase 2
- ✓ Country module plugin interface with scaffold template — Phase 2
- ✓ Recording and live transcription pipeline — Phase 2
- ✓ Consent/opt-out state machine enforced in the call path — Phase 2

### Active

- [ ] Agent can make an outbound voice call via tool invocation
- [ ] US compliance gateway enforces TCPA, STIR/SHAKEN, time-of-day, DNC
- [ ] Country module plugin interface with scaffold template
- [ ] Agent can send/receive SMS via SMPP or GSM modem
- [ ] Agent-to-agent direct communication via WebRTC (no PSTN)
- [ ] CLI onboarding: `pip install holler`, `holler init`, `holler call` — four commands to first call
- [ ] Recording and live transcription pipeline
- [ ] Consent/opt-out state machine enforced in the call path

### Out of Scope

- Cloud-hosted SaaS offering — this is self-hosted infrastructure, not a platform
- Building a carrier or acquiring telecom licenses — SIP trunk is the carrier interface
- Mobile app or end-user GUI — the "user" is an LLM, interface is tool-use protocol
- Custom LLM training — uses existing models (Whisper, Piper, Kokoro, general-purpose LLMs)
- WhatsApp / rich messaging channels — v1 focuses on voice + SMS, multi-modal channels are future work
- International compliance modules beyond US — community-contributed, not core v1 deliverable (template provided)

## Context

- The global telecom stack assumes a human at every endpoint. AI agents hitting the phone network today go through vendor chokepoints (Twilio, Vonage) that add cost, latency, data flow through third parties, and vendor lock-in.
- Emerging "AI voice" startups (Vapi, Bland AI, Retell) solve developer experience but replicate the structural dependency. Holler is infrastructure you own — closer to "Linux for telecom" than "AWS for telecom."
- Voice conversation latency budget is ~800ms for the full STT→LLM→TTS loop. Streaming throughout and local inference eliminate network round-trips.
- The project is explicitly a bridge protocol — designed to be useful now while the phone network evolves. May be obsolete in 3 years. That's fine.
- Hardware profile: RTX 3060+ for STT, CPU i7+ for TTS, RTX 4090/M4 Max for local LLM. 1-4 concurrent calls single GPU, 16-64 with multi-GPU.
- US is the hardest compliance jurisdiction (TCPA, STIR/SHAKEN, state overlays). Solving US compliance first makes other countries easier.
- Agent-to-agent communication will grow faster than agent-to-human. Building that path on WebRTC (free, no regulation) rather than PSTN is architecturally important.

## Constraints

- **Language**: Python core (orchestration, agent interface) + C/Rust for latency-critical voice pipeline components
- **Softswitch**: FreeSWITCH (open source, mature, well-documented)
- **STT**: faster-whisper / Whisper.cpp (local inference only)
- **TTS**: Piper / Kokoro / Orpheus (local inference only)
- **Media**: WebRTC + RTP via Janus gateway
- **SMS**: SMPP protocol or GSM modem (gammu/kannel)
- **License**: Apache 2.0
- **Latency**: Full voice loop must complete in <800ms for natural conversation
- **No vendor accounts**: Core must function with zero external service accounts; SIP trunk is the single external dependency
- **Onboarding**: Install, point at trunk, make a call — four commands maximum

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| FreeSWITCH over Asterisk/Kamailio | More scalable, better codec support, stronger WebRTC integration | — Pending |
| Compliance as mandatory call-path gateway, not optional middleware | Architecturally impossible to place non-compliant call; legal defense posture | — Pending |
| Numbers as ephemeral pool, not per-agent allocation | Identity travels with conversation context, not with phone number; reduces DID costs | — Pending |
| Python core + C/Rust voice pipeline | Python for rapid agent interface iteration; C/Rust only where latency budget demands it | — Pending |
| Local-first inference (no cloud STT/TTS) | Data sovereignty, latency reduction, no per-minute API costs | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-24 after Phase 2 completion*

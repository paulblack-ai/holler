# Milestones

## v1.0 MVP (Shipped: 2026-03-25)

**Phases completed:** 5 phases, 16 plans, 27 tasks

**Key accomplishments:**

- One-liner:
- faster-whisper STT, Kokoro-ONNX TTS, soxr audio resampler, and VAD turn-detection state machine as standalone async modules
- Genesis ESL async client with originate/hangup/audio_stream call control and EventRouter state machine tracking call lifecycle via CHANNEL_ANSWER/CHANNEL_HANGUP events
- WebSocket audio bridge for mod_audio_stream, streaming OpenAI-compatible LLM client, and async pipeline coordinator wiring STT->LLM->TTS with barge-in cancellation
- One-liner:
- ComplianceModule ABC with check_outbound() contract, TelecomSession wrapping VoiceSession via composition, and NumberPool with atomic Redis SPOP/SADD DID management
- Append-only ConsentDB, fast DNCList, and dual-write AuditLog — three aiosqlite-backed compliance data stores with 22 passing tests
- ComplianceGateway wraps esl.originate() as mandatory pre-originate gate; JurisdictionRouter maps E.164 prefixes with longest-match; _template/ scaffolds new jurisdiction modules with fail-closed defaults
- One-liner:
- Call recording via FreeSWITCH uuid_record with post-call faster-whisper transcription, DTMF and STT opt-out capture wired to consent DB, and full compliance-gated outbound call path integrated into main.py
- SMPP messaging layer with async ESME client, delivery-receipt tracking, inbound SMS routing, and mandatory compliance gate — mirrors voice call pattern for SMS.
- One-liner:
- One-liner:
- Commit:
- One-liner:
- Inbound SMPP SMS now reaches _handle_inbound_sms in main.py; spoken opt-out keywords in STT transcripts trigger check_optout_keywords -> ConsentDB.record_optout(source='stt') -> ESL hangup

---

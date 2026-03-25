---
phase: 05-sms-inbound-stt-optout-wiring
plan: 01
subsystem: telecom
tags: [smpp, stt, optout, consent, voice-pipeline, sms-session]

# Dependency graph
requires:
  - phase: 02-telecom-abstraction-compliance
    provides: ConsentDB with record_optout(), ComplianceGateway, check_optout_keywords
  - phase: 03-sms-agent-interface-cli
    provides: SMSClient.initialize(inbound_handler), HollerHook.received(), SMSSession
  - phase: 01-freeswitch-voice-pipeline
    provides: VoicePipeline._respond() STT->LLM->TTS flow

provides:
  - Inbound SMS handler registered in main.py: sms_client.initialize(inbound_handler=_handle_inbound_sms)
  - STT opt-out keyword detection in VoicePipeline._respond() after transcription, before LLM
  - consent_db schema updated to accept source='stt'
  - main.py _handle_stt_optout: records consent DB + hangup via ESL on keyword match
  - main.py _handle_inbound_sms: creates/updates SMSSession, logs inbound messages

affects:
  - any future phase touching voice pipeline or SMS handling

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Inline deferred import (inside _respond()) to break circular import chain: pipeline -> telecom.optout -> telecom.__init__ -> telecom.session -> voice.pipeline"
    - "Callback wiring via closure: _handle_stt_optout captures telecom_sessions/consent_db/esl from outer main() scope"
    - "SMS session keyed by sender E.164: sms_sessions dict in main() closure, allows multi-message threads"

key-files:
  created:
    - tests/test_phase5_wiring.py
  modified:
    - holler/core/compliance/consent_db.py
    - holler/core/voice/pipeline.py
    - holler/main.py
    - tests/test_tool_pipeline.py

key-decisions:
  - "Inline import of check_optout_keywords inside _respond() to avoid circular import (telecom.__init__ imports telecom.session which imports voice.pipeline); plan allowed inline as alternative"
  - "telecom_sessions dict declaration moved before pipeline/SMS init to allow _handle_stt_optout closure to reference it at definition time"
  - "_opt_out_keywords and _on_optout set as instance attributes via __init__ params; VoicePipeline remains backward compatible (both default to None/[])"

patterns-established:
  - "Opt-out check in _respond() pattern: if self._opt_out_keywords and transcript: check -> callback -> return before LLM"
  - "Inbound handler as closure in main(): state dict defined in outer scope, captured by async def"

requirements-completed: [SMS-02, COMP-04]

# Metrics
duration: 9min
completed: 2026-03-25
---

# Phase 5 Plan 01: SMS Inbound and STT Opt-out Wiring Summary

**Inbound SMPP SMS now reaches _handle_inbound_sms in main.py; spoken opt-out keywords in STT transcripts trigger check_optout_keywords -> ConsentDB.record_optout(source='stt') -> ESL hangup**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-25T01:19:37Z
- **Completed:** 2026-03-25T01:28:19Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Inbound SMS arriving via SMPP is now dispatched to `_handle_inbound_sms` in `main.py`, which creates/updates an `SMSSession` and logs the message (closes SMS-02)
- STT opt-out keyword detection added to `VoicePipeline._respond()` after transcription completes; matched keyword invokes `on_optout` callback and returns before LLM (closes COMP-04)
- `consent_db.py` CHECK constraint updated to accept `'stt'` as a valid source value
- `main.py` wires both paths: `_handle_inbound_sms` via `sms_client.initialize(inbound_handler=...)`, `_handle_stt_optout` via `VoicePipeline(on_optout=..., opt_out_keywords=...)`
- 13 new tests in `test_phase5_wiring.py` covering schema, structural, functional, and behavioral paths; all 264 suite tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire inbound SMS handler and STT opt-out with consent_db schema fix** - `f623138` (feat)

## Files Created/Modified

- `holler/core/compliance/consent_db.py` - Added 'stt' to CHECK constraint source IN list
- `holler/core/voice/pipeline.py` - Added `on_optout`/`opt_out_keywords` params to `__init__`; added opt-out check block in `_respond()` after STT, before LLM
- `holler/main.py` - Added `SMSSession` import; moved `telecom_sessions`/`opt_out_keywords` before pipeline init; added `_handle_stt_optout` and `_handle_inbound_sms` closures; wired both to their respective initializers
- `tests/test_phase5_wiring.py` - 13 new tests: consent_db stt source, structural greps, functional SMS handler, pipeline opt-out behavioral tests
- `tests/test_tool_pipeline.py` - Added `_opt_out_keywords=[]` and `_on_optout=None` to `VoicePipeline.__new__` helpers that bypass `__init__`

## Decisions Made

- Inline import of `check_optout_keywords` inside `_respond()` rather than top-level import — avoids circular import chain (`holler.core.telecom.__init__` imports `telecom.session` which imports `voice.pipeline`)
- `telecom_sessions` dict moved before pipeline/SMS init so `_handle_stt_optout` closure captures it at definition time
- `VoicePipeline.__init__` remains backward compatible — new params default to `None`/`[]`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Circular import: top-level `check_optout_keywords` import**
- **Found during:** Task 1 (GREEN phase — tests failed with ImportError)
- **Issue:** Adding `from holler.core.telecom.optout import check_optout_keywords` at top of `pipeline.py` triggered `holler/core/telecom/__init__.py` (package `__init__` always runs first), which imports `telecom.session`, which imports `VoiceSession` from `voice.pipeline` — circular during module initialization
- **Fix:** Moved import inline inside `_respond()` where opt-out check is performed; Python's module cache prevents re-import overhead after first call
- **Files modified:** `holler/core/voice/pipeline.py`
- **Verification:** All 13 new tests pass; `python3 -c "from holler.main import main"` succeeds
- **Committed in:** f623138

**2. [Rule 1 - Bug] `test_tool_pipeline.py` `__new__`-based pipeline helpers missing new attributes**
- **Found during:** Task 1 (full suite run after GREEN phase)
- **Issue:** `_make_pipeline_with_mocks` and `test_pipeline_no_tool_executor_passes_none_tools` create `VoicePipeline` via `__new__` and manually set attributes — missing `_opt_out_keywords` and `_on_optout`, causing `AttributeError` in `_respond()`
- **Fix:** Added `pipeline._opt_out_keywords = []` and `pipeline._on_optout = None` to both `__new__` helper sites
- **Files modified:** `tests/test_tool_pipeline.py`
- **Verification:** All 264 tests pass
- **Committed in:** f623138

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes required for correctness; no scope creep. Circular import fix is an architectural limitation of the existing `telecom/__init__.py` re-export approach.

## Issues Encountered

None beyond the circular import (handled as Rule 1 deviation above).

## Known Stubs

None — both wiring paths are fully connected. `_handle_inbound_sms` logs messages but does not yet invoke an LLM for reply; this is intentional for v1.0 (SMS agent reply is not in scope per PROJECT.md requirements).

## Next Phase Readiness

- SMS-02 and COMP-04 are both closed — all v1.0 milestone requirements are now satisfied
- The v1.0 milestone audit gaps are fully resolved
- Ready for milestone completion / verification pass

---
*Phase: 05-sms-inbound-stt-optout-wiring*
*Completed: 2026-03-25*

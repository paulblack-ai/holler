# Phase 5: SMS Inbound + STT Opt-Out Wiring - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning
**Source:** v1.0 Milestone Audit gap closure

<domain>
## Phase Boundary

Wire the two unwired paths identified by the v1.0 milestone audit: (1) register an inbound SMS handler in main.py so messages are not silently discarded, and (2) call check_optout_keywords() in the audio processing path so spoken opt-out keywords trigger consent DB update and call termination.

</domain>

<decisions>
## Implementation Decisions

### Inbound SMS handler wiring
- **D-01:** Pass an `inbound_handler` callback to `SMSClient.initialize()` in main.py. The handler should create an SMSSession and log the inbound message. For v1, the handler logs the message and stores it in the telecom session — full agent-driven SMS response is already available via the tool-use protocol.
- **D-02:** The inbound handler callback signature should match what HollerHook expects: `async def handler(sender: str, text: str) -> None`.

### STT keyword opt-out wiring
- **D-03:** Call `check_optout_keywords()` on each STT transcript result in the voice pipeline or main.py audio processing path. When a keyword match is found: (a) write opt-out to ConsentDB, (b) hang up the call via ESL.
- **D-04:** The opt_out_keywords list already parsed in main.py must be passed to wherever the check runs. The check should happen AFTER STT produces a transcript and BEFORE the transcript is sent to the LLM.

### Claude's Discretion
- Exact location of the opt-out check (pipeline._respond() vs main.py callback vs separate middleware)
- Whether to log a structured event when opt-out is detected
- SMSSession storage mechanism (in-memory dict like telecom_sessions, or just log)
- Test strategy for both wiring paths

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit findings
- `.planning/v1.0-MILESTONE-AUDIT.md` — Gap details for SMS-02, COMP-04

### Files to fix
- `holler/main.py` — Pass inbound_handler to sms_client.initialize(); wire opt_out_keywords into audio path
- `holler/core/sms/client.py` — SMSClient.initialize() already accepts inbound_handler parameter
- `holler/core/sms/hook.py` — HollerHook.received() already calls inbound_handler when set
- `holler/core/telecom/optout.py` — check_optout_keywords() already implemented and exported
- `holler/core/voice/pipeline.py` — May need opt-out check in _respond() path
- `holler/core/compliance/consent_db.py` — ConsentDB.record_optout() already implemented

### Phase 2 context (opt-out design)
- `.planning/phases/02-telecom-abstraction-compliance/02-CONTEXT.md` — D-15, D-16 (opt-out design decisions)

### Phase 3 context (SMS design)
- `.planning/phases/03-sms-agent-interface-cli/03-CONTEXT.md` — D-05 through D-08 (SMS decisions)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (already built, just need wiring)
- `check_optout_keywords(transcript, keywords)` in `holler/core/telecom/optout.py` — returns matched keyword or None
- `ConsentDB.record_optout(phone, source, call_uuid)` in `consent_db.py` — writes append-only opt-out record
- `HollerHook.received()` in `hook.py` — dispatches inbound SMS to handler when set
- `SMSClient.initialize(inbound_handler=)` — accepts optional callback
- `opt_out_keywords` list already parsed in main.py from config

### Established Patterns
- Async callbacks for event handling (on_answer, on_hangup, on_dtmf patterns in main.py)
- ConsentDB accessed via closure scope in main.py handlers

### Integration Points
- `main.py:sms_client.initialize()` — add inbound_handler parameter
- `main.py` audio processing path or `pipeline.py:_respond()` — add opt-out keyword check

</code_context>

<specifics>
## Specific Ideas

- Both fixes are pure wiring — the components are built and tested, they just need to be connected
- The DTMF opt-out handler in main.py is the reference pattern for the STT opt-out handler

</specifics>

<deferred>
## Deferred Ideas

None — this phase is tightly scoped to audit gap closure

</deferred>

---

*Phase: 05-sms-inbound-stt-optout-wiring*
*Context gathered: 2026-03-25*

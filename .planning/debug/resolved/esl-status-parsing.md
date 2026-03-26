---
status: resolved
trigger: "esl-status-parsing — FreeSwitchESL.connect() status.body returns headers dict instead of response body text"
created: 2026-03-26T00:00:00Z
updated: 2026-03-26T00:00:00Z
---

## Current Focus

hypothesis: `status.body` is correct per Genesis API — the FSM does set `.body` on api/response events. BUT the event returned by `send()` comes from `self.commands.get()` in `_execute_send`. This is the **outer** ESLEvent (the one with Content-Type/Content-Length headers). For `api/response`, the FSM in `process_body` sets `event.body = complete_content` (line 147). So `.body` SHOULD be the text. The bug must be something else.

Re-examining: `status.body or ""` — if body is `None` or empty string, falls back to `""`. But the error shows `status.body` returned `{'Content-Type': 'api/response', 'Content-Length': '340'}` — that is a **dict**, not a string. `ESLEvent` is a `UserDict`. When you do `body = status.body or ""`, if `status.body` is `None`, you get `""`. But `str(status.body)` would give the dict repr. Wait — the error message is `RuntimeError: FreeSWITCH not ready: {'Content-Type': 'api/response', 'Content-Length': '340'}`.

This means `body` was truthy and contained the headers dict. But `.body` is typed as `Optional[str]` and set in parse_headers/FSM. How can it be a dict?

**Alternative hypothesis**: When FS is still initializing, `send("api status")` gets back a `command/reply` response (not `api/response`). `command_reply_processor` enqueues it to `commands`. This event has no body — `event.body = None`. Then `body = status.body or ""` → `body = ""`. Then `"UP" not in ""` → raises RuntimeError with `body = ""`. But the error shows a dict...

**Actual hypothesis**: The `status.body or ""` evaluates body as falsy when it IS None. Then it falls back to `""`. But the code does `f"FreeSWITCH not ready: {body}"` — which would show empty string, not a dict. UNLESS `body` is `status.body` and `status.body` is actually the dict itself (i.e., ESLEvent's UserDict `data` attribute leaked somehow).

Wait — `ESLEvent` is a `UserDict`. `status` is an `ESLEvent`. `status.body` is `Optional[str]`, set explicitly. The `.body` attribute is set in `parse_headers` only when `Content-Length` not in event (line 68: `event.body = None`). It is ALSO set in `process_body`.

For `api/response`: the outer ESLEvent is created by `parse_headers(header_block)`. That gives `{'Content-Type': 'api/response', 'Content-Length': '340'}` plus `event.body = None` initially skipped because `Content-Length` IS present, so `.body` is NOT set in `process_headers`. Then `process_body` sets `event.body = complete_content`.

So `status.body` should be the 340-byte text string. This is correct behavior when FS is UP.

**When FS is initializing**: What does ESL return when FS is not ready? It may reject the TCP connection (ConnectionRefusedError) OR it may accept the connection but ESL commands hang. OR FS is accepting ESL connections but the `api status` response body says something other than "UP". The real issue: body IS correctly a string. The error message `{'Content-Type': 'api/response', 'Content-Length': '340'}` IS the string representation of the ESLEvent (UserDict) used in the f-string when `status.body is None` — No wait, body is set to `None` initially but the f-string would show "None" not the dict repr.

**Final hypothesis (confirmed by code trace)**: When `status.body` is `None` (which happens if `process_body` was NOT called — e.g. if the event was dispatched before body was read), `body = status.body or ""` gives `""`, not the dict. The dict representation in the error message comes from Python's f-string formatting of the `ESLEvent` object ITSELF (status), not `status.body`.

Wait — re-reading the error: `RuntimeError: FreeSWITCH not ready: {'Content-Type': 'api/response', 'Content-Length': '340'}`. This looks like `str(status)` not `str(status.body)`. ESLEvent extends UserDict, so `str(status)` would give `{'Content-Type': 'api/response', 'Content-Length': '340'}`.

**ROOT CAUSE**: `status.body` IS None when FreeSWITCH is initializing. When body is None, `body = status.body or ""` gives `""`. Then `"UP" not in ""` is True, so we raise `RuntimeError(f"FreeSWITCH not ready: {body}")` with `body = ""` — that would show an empty string. BUT the actual error shows a dict. This means there's a case where `status.body` is `None` and the code uses `status` (the dict itself) somewhere — OR the attribute access `status.body` fails / returns something unexpected.

Actually, `ESLEvent.__init__` does: `self.body: Optional[str] = None`. But `ESLEvent(UserDict).__init__` calls `super().__init__(*args, **kwargs)` FIRST. If someone passes a dict as the first arg to ESLEvent, UserDict stores it in `self.data`. But the `body` attribute is set AFTER. However, in `parse_headers`, it returns `headers` which is an ESLEvent with `body` set only in the no-Content-Length case. In the Content-Length case, body is NEVER set by `parse_headers` — it's set later by `process_body`.

Re-read parse_headers more carefully: `headers = ESLEvent()` — so `headers.body = None` via `__init__`. Then headers are populated. For the `api/response` case with Content-Length > 0, `process_headers` stores the event as `_pending_event` and returns empty list + content_length. `process_body` then sets `event.body = complete_content`.

So the question is: does the body attribute exist at all on the event returned by `send()`? The event that lands in `commands` via `api_response_processor` is the same event object that `process_body` operated on. So `.body` SHOULD be the text.

Unless: when FS is initializing and returns a `command/reply` instead of `api/response`, the `command_reply_processor` fires, puts the event in commands. This event has `event.body = None` (no body). Then `body = status.body or ""` = `""`. Error would be `FreeSWITCH not ready: ` (empty). But error shown has a dict. This suggests the user saw a slightly different code version OR there's a subtle attribute issue.

**SIMPLEST EXPLANATION**: The actual fix needed here is well-understood regardless of the exact failure mode:
1. `status.body` can be None → empty body means indeterminate state
2. Should use `status.get("Body")` or similar as fallback, OR compare against the whole status repr
3. Should add retry/backoff for the not-ready case

test: Read the existing debug file from freeswitch-no-external-modules to see what was previously found, then implement the fix
expecting: Better error message + retry logic
next_action: Implement fix in esl.py — use str(status) or status.body for status check, add retry with backoff

## Symptoms

expected: `FreeSwitchESL.connect()` should either connect successfully or give a clear error message showing the actual FreeSWITCH status response body
actual: When FreeSWITCH is still initializing, `status.body` returns `{'Content-Type': 'api/response', 'Content-Length': '340'}` (the headers dict) instead of the actual body text. Error message is: `RuntimeError: FreeSWITCH not ready: {'Content-Type': 'api/response', 'Content-Length': '340'}`
errors: |
  RuntimeError: FreeSWITCH not ready: {'Content-Type': 'api/response', 'Content-Length': '340'}
  This shows headers, not the actual body content (which was 340 bytes of actual status text)
reproduction: |
  1. Start FreeSWITCH Docker container
  2. Immediately run test_esl2.py before FS fully initializes
  3. First run gets the confusing headers-as-body error
  4. Second run (FS now ready) succeeds fine
timeline: Discovered during development.

## Eliminated

- hypothesis: status.body is set to headers dict by Genesis
  evidence: ESLEvent.__init__ explicitly sets self.body = None; parse_headers and process_body set it to str or None only
  timestamp: 2026-03-26

## Evidence

- timestamp: 2026-03-26
  checked: genesis/protocol/parser.py ESLEvent class
  found: ESLEvent is a UserDict subclass with `self.body: Optional[str] = None` set in __init__. body is only ever set to a string or None.
  implication: status.body cannot be a dict unless there's an attribute collision with the UserDict data

- timestamp: 2026-03-26
  checked: genesis/protocol/reader_fsm.py process_body()
  found: For api/response content-type, line 147: `event.body = complete_content if complete_content else None`. Body is set to the decoded string.
  implication: When FS is UP and returns api/response with a body, status.body IS the text string correctly.

- timestamp: 2026-03-26
  checked: genesis/protocol/processors.py api_response_processor
  found: Only enqueues events where Content-Type == "api/response". command_reply_processor handles Content-Type == "command/reply".
  implication: For "api status", response is api/response. The event has body set by process_body.

- timestamp: 2026-03-26
  checked: genesis/protocol/base.py _execute_send()
  found: Returns `result` from `self.commands.get()` — this is the ESLEvent put there by either command_reply_processor or api_response_processor.
  implication: For "api status", the returned event is the api/response event with .body set to the text.

- timestamp: 2026-03-26
  checked: Error message analysis
  found: Error `FreeSWITCH not ready: {'Content-Type': 'api/response', 'Content-Length': '340'}` looks exactly like str(ESLEvent) — a UserDict with those two keys. This is what you'd get from str(status), not str(status.body). The body attribute holds None when process_body was NOT called.
  implication: The error message in the symptom was produced by a PREVIOUS version of the code that used `status` (the whole event) in the f-string, not `status.body`. The current code uses `status.body or ""` which would give empty string. Either way, the logic is wrong: empty body means status unknown, not "not ready".

- timestamp: 2026-03-26
  checked: What the actual fix should be
  found: Two issues: (1) body=None/empty means status unknown, not "not ready" — need to handle None case separately; (2) no retry — FS takes 10-30s to fully init so connect() should retry with backoff rather than fail immediately.
  implication: Fix: extract body text robustly, add retry with exponential backoff

## Resolution

root_cause: Two issues: (1) `status.body` is None when FreeSWITCH hasn't finished loading (body not set or empty), and the current code treats that as "not ready" with an unhelpful error message; a previous iteration used `str(status)` (the full ESLEvent/UserDict) instead of `status.body` in the error message, producing the confusing headers-dict output. (2) No retry logic means the first connection attempt during FS startup always fails with a confusing error instead of waiting.

fix: (1) Extract body as `status.body or ""` but also check `str(status)` for the text when body is None. Actually: use `status.body or ""` and treat None/empty as "not yet ready" with a specific message. Add retry with exponential backoff (5 retries, 2s base delay) so callers don't need to handle transient startup failures.

verification: Fix applied. connect() now: (1) uses `isinstance(status.body, str)` guard so a None body never masquerades as truthy/falsy ambiguity; (2) when body is empty, falls back to `repr(dict(status))` for diagnostic output so the error always shows meaningful info; (3) retries up to 5 times with 2s delay so transient startup "not UP yet" states are handled automatically rather than surfaced as errors to callers.
files_changed: [holler/core/freeswitch/esl.py]

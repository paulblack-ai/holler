---
phase: 03-sms-agent-interface-cli
plan: "02"
subsystem: agent
tags: [tool-use, llm, openai, anthropic, executor, adapters, tdd]
dependency_graph:
  requires:
    - holler/core/compliance/gateway.py (ComplianceGateway, ComplianceBlockError)
    - holler/core/freeswitch/esl.py (FreeSwitchESL.hangup, send_raw)
    - holler/core/telecom/session.py (TelecomSession)
    - holler/core/telecom/pool.py (NumberPool)
  provides:
    - holler/core/agent/tools.py (HOLLER_TOOLS, ToolCallSentinel, get_tools)
    - holler/core/agent/executor.py (ToolExecutor)
    - holler/core/agent/adapters.py (openai_to_anthropic, anthropic_response_to_tool_calls)
    - holler/core/agent/__init__.py (package exports)
  affects:
    - Plan 03 (LLM pipeline coordinator — wires ToolExecutor into streaming loop)
tech_stack:
  added: []
  patterns:
    - OpenAI function calling JSON Schema with strict mode and nullable type pattern
    - TYPE_CHECKING guard for all inter-module Holler imports
    - ComplianceBlockError -> structured JSON (D-02 pattern)
    - TelecomSession construction with all required fields for SMS path
    - Adapter pattern for multi-provider LLM tool format translation
key_files:
  created:
    - holler/core/agent/__init__.py
    - holler/core/agent/tools.py
    - holler/core/agent/executor.py
    - holler/core/agent/adapters.py
    - tests/test_agent.py
  modified: []
decisions:
  - "prompt parameter on call tool uses nullable type pattern [string, null] — required but nullable per OpenAI strict mode Pitfall 4"
  - "anthropic_response_to_tool_calls returns arguments as dict (not JSON string) — matches Anthropic API which parses input dict natively"
  - "ToolExecutor catches ComplianceBlockError specifically before generic Exception — ensures D-02 structured response never masked by broad catch"
  - "Transfer compliance check uses module.check_outbound() directly (not gateway.originate_checked) — transfer reuses existing session, not a new origination"
metrics:
  duration: "3 minutes"
  completed_date: "2026-03-25"
  tasks_completed: 1
  files_created: 5
  tests_added: 33
---

# Phase 3 Plan 02: Agent Tool-Use Protocol Layer Summary

**One-liner:** Four OpenAI strict-mode tool definitions (call, sms, hangup, transfer) with ToolExecutor dispatching to Holler subsystems and Anthropic adapter for multi-LLM support.

## What Was Built

The `holler/core/agent/` package — the tool-use protocol layer that bridges LLM function calling to actual Holler telecom actions.

### Files Created

- **holler/core/agent/tools.py** — `HOLLER_TOOLS` list of 4 tool definitions in OpenAI function calling JSON Schema format. All tools use `strict: True`, `additionalProperties: False`. The `call` tool's `prompt` parameter uses the nullable type pattern `["string", "null"]` required by strict mode. `ToolCallSentinel` dataclass and `get_tools()` helper also defined.

- **holler/core/agent/executor.py** — `ToolExecutor` class dispatching `execute(tool_name, arguments, session)` to:
  - `call` → `gateway.originate_checked(esl, pool, session)`
  - `sms` → constructs full `TelecomSession` then `gateway.sms_checked(sms, pool, session_for_sms, message, log_id)`
  - `hangup` → `esl.hangup(call_uuid)`
  - `transfer` → compliance check then `esl.send_raw("api uuid_transfer ...")`
  - `ComplianceBlockError` is caught and returned as `{"status": "blocked", "reason": ...}` (D-02)

- **holler/core/agent/adapters.py** — Thin adapter functions for provider-specific tool formats:
  - `openai_to_anthropic()` — converts `parameters` → `input_schema`, drops `type`/`strict`
  - `openai_tools_to_anthropic()` — converts a full list
  - `anthropic_response_to_tool_calls()` — extracts `tool_use` content blocks into `[{id, name, arguments}]`

- **holler/core/agent/__init__.py** — Package exports all public symbols.

- **tests/test_agent.py** — 33 tests covering tool schema validation, executor dispatch for each tool, TelecomSession construction in _execute_sms(), compliance block handling, adapter conversions.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| `prompt` is `["string", "null"]` (required + nullable) | OpenAI strict mode Pitfall 4: optional parameters must be in `required` with `null` as valid type — not absent from `required` |
| `anthropic_response_to_tool_calls` returns `arguments` as dict | Anthropic `input` field is already a parsed dict; no JSON deserialization needed unlike OpenAI which passes JSON string |
| `ComplianceBlockError` caught before `Exception` | Guarantees D-02 structured response; broad except cannot mask compliance block as generic error |
| Transfer uses `module.check_outbound()` directly | Transfer reuses the existing active session context — not a new origination — so `originate_checked()` is not the right call path |

## TDD Execution

- **RED commit:** `102a010` — tests/test_agent.py with 33 failing tests (import error, module not yet created)
- **GREEN commit:** `5b120ce` — holler/core/agent/ package, all 33 tests pass

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: holler/core/agent/tools.py
- FOUND: holler/core/agent/executor.py
- FOUND: holler/core/agent/adapters.py
- FOUND: holler/core/agent/__init__.py
- FOUND: tests/test_agent.py
- FOUND: commit 102a010 (RED phase tests)
- FOUND: commit 5b120ce (GREEN phase implementation)

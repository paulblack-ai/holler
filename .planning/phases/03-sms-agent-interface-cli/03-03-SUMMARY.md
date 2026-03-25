---
phase: 03-sms-agent-interface-cli
plan: "03"
subsystem: voice-pipeline
tags: [tool-calling, llm, pipeline, streaming, agent]
dependency_graph:
  requires: ["03-02"]
  provides: ["tool-call-streaming", "pipeline-tool-interception"]
  affects: ["holler/core/voice/llm.py", "holler/core/voice/pipeline.py"]
tech_stack:
  added: []
  patterns:
    - "tool_calls_accumulator: index-keyed dict for streaming chunk reassembly"
    - "ToolCallSentinel sentinel pattern: last yielded item from stream_response() when tool invoked"
    - "extra_history list: accumulates tool results per round without mutating session.history until turn completes"
    - "max_tool_rounds=5 guard: prevents infinite tool-call loops"
    - "TTS flush via None sentinel before tool execution: prevents pipeline deadlock (Pitfall 2)"
    - "TYPE_CHECKING guard for ToolExecutor import: avoids hard import dependency at module load"
key_files:
  created:
    - tests/test_tool_pipeline.py
  modified:
    - holler/core/voice/llm.py
    - holler/core/voice/pipeline.py
decisions:
  - "tool_calls_accumulator dict keyed by chunk index — reassembles fragmented tool_calls from streaming delta chunks"
  - "extra_history scoped to turn — tool results not added to session.history until turn completes (clean rollback semantics)"
  - "feed_tokens() closes queue with None sentinel on tool call — TTS drains cleanly before executor runs (no deadlock)"
  - "messages_for_round='' for follow-up LLM rounds — LLM continues from tool results in history, no re-prompt needed"
metrics:
  duration: "5 minutes"
  completed: "2026-03-25"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 03 Plan 03: LLM Tool-Call Streaming and Pipeline Interception Summary

**One-liner:** Tool-calling LLM streaming via index-keyed chunk accumulation with pipeline-level ToolCallSentinel interception, TTS flush, and multi-round tool-result re-prompting.

## What Was Built

Extended the LLM client and voice pipeline to bridge LLM tool invocations into the Holler action subsystems (D-14, AGENT-01).

**`holler/core/voice/llm.py`**
- Added `tools: Optional[List[dict]] = None` parameter to `stream_response()`
- When tools provided: passes `tools` and `tool_choice="auto"` to OpenAI-compatible API
- Accumulates streaming tool_calls delta chunks via `tool_calls_accumulator` dict keyed by chunk index
- Yields `ToolCallSentinel(tool_calls)` as the final item when LLM invokes a tool
- Added `build_tool_result_entry(tool_call_id, result)` — creates `role=tool` history entry
- Fully backward compatible: `tools=None` yields only str tokens, no ToolCallSentinel

**`holler/core/voice/pipeline.py`**
- Added `tool_executor: Optional["ToolExecutor"] = None` to `VoicePipeline.__init__()`
- Imported `ToolCallSentinel` and `get_tools()` from `holler.core.agent.tools`
- Restructured `_respond()` with a tool-call retry loop (up to `max_tool_rounds=5`)
- `feed_tokens()` detects `isinstance(token, ToolCallSentinel)`, stores sentinel, flushes TTS queue with None
- After TTS drains: calls `tool_executor.execute()` for each tool call in the sentinel
- Builds `extra_history` with `role=assistant` tool_calls entry + `role=tool` result entries
- Next LLM round uses `messages_for_round=""` — LLM continues from accumulated tool history
- Final text response tokens added to `session.history` at turn end
- Fully backward compatible: `tool_executor=None` behaves exactly as before

**`tests/test_tool_pipeline.py`** (12 tests)
- LLM: text-only backward compat, sentinel yield, argument accumulation, no-tool-calls fallback
- LLM: `build_tool_result_entry()` format and nested serialization
- Pipeline: text-only without executor, text-only with executor (no tool invocation), tool call interception, tool result fed back to LLM, max_tool_rounds guard, tools=None passed when no executor

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All tool paths are wired: ToolExecutor.execute() is called with real arguments, results flow back to LLM. No placeholder returns in the modified pipeline path.

## Self-Check: PASSED

Files exist:
- holler/core/voice/llm.py: FOUND
- holler/core/voice/pipeline.py: FOUND
- tests/test_tool_pipeline.py: FOUND

Commits exist:
- 15c6fe6: feat(03-03): extend LLMClient.stream_response() for tool-call streaming
- 1267a47: feat(03-03): extend VoicePipeline._respond() for tool-call interception

All 12 tests pass: `python3 -m pytest tests/test_tool_pipeline.py` → 12 passed

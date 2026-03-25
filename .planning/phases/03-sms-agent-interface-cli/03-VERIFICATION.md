---
phase: 03-sms-agent-interface-cli
verified: 2026-03-25T00:28:32Z
status: passed
score: 16/16 must-haves verified
re_verification: false
---

# Phase 3: SMS, Agent Interface, CLI Verification Report

**Phase Goal:** An LLM can use Holler as a tool — initiating calls, sending and receiving SMS, and completing the full workflow in four CLI commands from a clean install
**Verified:** 2026-03-25T00:28:32Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                      | Status     | Evidence                                                                            |
|----|--------------------------------------------------------------------------------------------|------------|-------------------------------------------------------------------------------------|
| 1  | SMSClient can send an outbound SMS via aiosmpplib ESME                                     | VERIFIED   | `holler/core/sms/client.py`: `send()` enqueues SubmitSm, sets `_delivery_store[log_id]="queued"` |
| 2  | Inbound SMS from SMSC routes to a handler callback                                         | VERIFIED   | `HollerHook.received()`: non-receipt DeliverSm calls `await self._inbound_handler(sender, text)` |
| 3  | Delivery receipts update a status store queryable by message ID                            | VERIFIED   | `HollerHook._extract_stat()` + `_RECEIPT_STAT_MAP` updates `_store[log_id]`; `SMSClient.get_status()` reads it |
| 4  | SMS send goes through ComplianceGateway.sms_checked() before SMPP transmission            | VERIFIED   | `gateway.py`: `sms_checked()` calls `await sms_client.send(...)` only after `result.passed`; no other send path |
| 5  | SMS to a DNC number is blocked by compliance, not silently sent                            | VERIFIED   | `sms_checked()`: `not result.passed` → `pool.release(did)` → `raise ComplianceBlockError(result.reason)` |
| 6  | Four tool definitions (call, sms, hangup, transfer) exist in OpenAI strict JSON Schema     | VERIFIED   | `HOLLER_TOOLS`: 4 entries, all `strict=True`, `additionalProperties=False`; `call.prompt` uses `["string","null"]` nullable pattern |
| 7  | ToolExecutor dispatches by name to correct handler and returns structured JSON result      | VERIFIED   | `executor.py`: dispatches call/sms/hangup/transfer; unknown returns `{"status":"error","reason":"unknown_tool:..."}`  |
| 8  | Compliance blocks produce `{status: blocked, reason: ...}` not exceptions (D-02)          | VERIFIED   | `execute()`: `except ComplianceBlockError as e: return {"status":"blocked","reason":str(e)}`; caught before generic Exception |
| 9  | Anthropic adapter converts OpenAI tool format to Anthropic input_schema format            | VERIFIED   | `openai_to_anthropic()`: maps `parameters`→`input_schema`, drops `type`/`strict`; verified in spot-check |
| 10 | LLMClient.stream_response() handles tools param and yields ToolCallSentinel on tool call  | VERIFIED   | `llm.py`: `tools: Optional[List[dict]] = None` param; `tool_calls_accumulator` reassembly; `yield ToolCallSentinel(...)` |
| 11 | VoicePipeline._respond() intercepts ToolCallSentinel, executes tool, feeds result back    | VERIFIED   | `pipeline.py`: `isinstance(token, ToolCallSentinel)` check; `await self.tool_executor.execute(...)`; `extra_history` accumulation |
| 12 | Tool execution does not block audio pipeline (TTS filler plays while tool executes)       | VERIFIED   | `feed_tokens()`: on sentinel detection, puts `None` sentinel to queue, returns — TTS drains before executor runs |
| 13 | `holler init` downloads models, generates .holler.env, starts Docker Compose              | VERIFIED   | `commands.py`: `_check_gpu()`, `_download_models()`, `_generate_env_file()`, `_start_services()` all implemented |
| 14 | `holler trunk add` configures SIP trunk credentials in .holler.env                        | VERIFIED   | `_write_trunk_config()`: reads existing file, updates HOLLER_TRUNK_HOST/USER/PASS, appends if absent; `--pass` alias present |
| 15 | `holler call +1XXXXXXXXXX` places a call using the agent loop with tool-use support       | VERIFIED   | `call` command: `asyncio.run(main(call_destination=destination, agent_prompt=agent))`; main.py wires ToolExecutor → VoicePipeline |
| 16 | HollerConfig.from_env() reads .holler.env first, then env vars override                   | VERIFIED   | `config.py`: `load_dotenv(".holler.env", override=False)` at top of `from_env()`; SMSConfig populated from env vars |

**Score:** 16/16 truths verified

---

### Required Artifacts

| Artifact                              | Provides                                                          | Status     | Details                                                     |
|---------------------------------------|-------------------------------------------------------------------|------------|-------------------------------------------------------------|
| `holler/core/sms/__init__.py`         | Package exports: SMSClient, SMSConfig, HollerHook, SMSSession     | VERIFIED   | All four exports confirmed via import                       |
| `holler/core/sms/client.py`           | SMSClient with initialize(), send(), get_status(), stop(); SMSConfig | VERIFIED | Deferred init pattern; TYPE_CHECKING guard for aiosmpplib   |
| `holler/core/sms/hook.py`             | HollerHook: delivery receipt stat parsing, inbound SMS routing    | VERIFIED   | `_RECEIPT_STAT_MAP` with 5 entries; `received()` dispatcher  |
| `holler/core/sms/session.py`          | SMSSession dataclass with sender, destination, messages, created_at | VERIFIED | All fields present; `messages` has `field(default_factory=list)` |
| `holler/core/compliance/gateway.py`   | sms_checked() method and SMSClient TYPE_CHECKING import           | VERIFIED   | `async def sms_checked(self, sms_client, pool, session, message, log_id)` present |
| `holler/core/agent/__init__.py`       | Package exports all public symbols                                | VERIFIED   | All 6 exports confirmed via import                          |
| `holler/core/agent/tools.py`          | HOLLER_TOOLS list, ToolCallSentinel, get_tools()                  | VERIFIED   | 4 tools; strict=True; nullable prompt param; sentinel dataclass |
| `holler/core/agent/executor.py`       | ToolExecutor dispatching to call/sms/hangup/transfer              | VERIFIED   | All 4 tools + unknown; ComplianceBlockError → structured JSON |
| `holler/core/agent/adapters.py`       | openai_to_anthropic(), anthropic_response_to_tool_calls()         | VERIFIED   | input_schema key; no type/strict keys; filters tool_use blocks |
| `holler/core/voice/llm.py`            | Extended stream_response() with tools param and ToolCallSentinel  | VERIFIED   | tools param; tool_calls_accumulator; yield ToolCallSentinel(); build_tool_result_entry() |
| `holler/core/voice/pipeline.py`       | Extended _respond() with tool-call interception, ToolExecutor     | VERIFIED   | tool_executor param; isinstance(token, ToolCallSentinel) check; max_tool_rounds=5 |
| `holler/cli/__init__.py`              | Package marker                                                    | VERIFIED   | File exists                                                 |
| `holler/cli/commands.py`              | Click CLI group with init, trunk, call subcommands                | VERIFIED   | @click.group; 3 commands; --pass alias; asyncio.run(main()); helper functions implemented |
| `holler/config.py`                    | HollerConfig with sms: SMSConfig field and .holler.env loading    | VERIFIED   | `sms: SMSConfig` field; `load_dotenv(".holler.env", override=False)` |
| `holler/main.py`                      | Refactored entry point with SMSClient + ToolExecutor wiring       | VERIFIED   | SMSClient, ToolExecutor, tool_executor= in VoicePipeline; sms_client.stop() in finally |
| `pyproject.toml`                      | CLI entry point and Phase 3 dependencies                          | VERIFIED   | `[project.scripts]`; `holler = "holler.cli.commands:cli"`; all 4 new deps present |
| `tests/test_sms.py`                   | 22 unit tests for SMS client, hook, compliance SMS path           | VERIFIED   | 22 passed, 0 failed                                         |
| `tests/test_agent.py`                 | 33 tests for tool definitions, executor, adapters                 | VERIFIED   | 33 passed, 0 failed                                         |
| `tests/test_tool_pipeline.py`         | 12 tests for LLM tool streaming and pipeline interception         | VERIFIED   | 12 passed, 0 failed                                         |
| `tests/test_cli.py`                   | 22 tests for CLI commands and config loading                      | VERIFIED   | 22 passed, 0 failed                                         |

---

### Key Link Verification

| From                            | To                                 | Via                                          | Status | Details                                                                     |
|---------------------------------|------------------------------------|----------------------------------------------|--------|-----------------------------------------------------------------------------|
| `holler/core/sms/client.py`     | `holler/core/sms/hook.py`          | `hook=HollerHook(...)` in ESME constructor   | WIRED  | `hook = HollerHook(self._delivery_store, inbound_handler)` passed to ESME  |
| `holler/core/compliance/gateway.py` | `holler/core/sms/client.py`    | sms_checked() calls sms_client.send()        | WIRED  | `await sms_client.send(session.destination, message, log_id)` on pass path |
| `holler/core/agent/executor.py` | `holler/core/compliance/gateway.py` | _execute_sms() calls gateway.sms_checked()  | WIRED  | `await self._gateway.sms_checked(self._sms, self._pool, session_for_sms, message, log_id)` |
| `holler/core/agent/executor.py` | `holler/core/freeswitch/esl.py`    | _execute_hangup() calls esl.hangup()         | WIRED  | `await self._esl.hangup(call_uuid)`                                         |
| `holler/core/agent/tools.py`    | `holler/core/agent/adapters.py`    | openai_to_anthropic() transforms HOLLER_TOOLS | WIRED | `openai_to_anthropic(t) for t in tools` consumes HOLLER_TOOLS format       |
| `holler/core/voice/llm.py`      | `holler/core/agent/tools.py`       | stream_response() yields ToolCallSentinel    | WIRED  | `from holler.core.agent.tools import ToolCallSentinel` (direct import, not TYPE_CHECKING) |
| `holler/core/voice/pipeline.py` | `holler/core/agent/executor.py`    | _respond() calls tool_executor.execute()     | WIRED  | `result = await self.tool_executor.execute(tc["name"], args, session)`      |
| `pyproject.toml`                | `holler/cli/commands.py`           | [project.scripts] entry point                | WIRED  | `holler = "holler.cli.commands:cli"` — CLI entry point registered           |
| `holler/cli/commands.py`        | `holler/main.py`                   | call command uses asyncio.run(main(...))     | WIRED  | `asyncio.run(main(call_destination=destination, agent_prompt=agent))`       |
| `holler/config.py`              | `.holler.env`                      | load_dotenv in from_env()                    | WIRED  | `load_dotenv(".holler.env", override=False)` at top of from_env()           |
| `holler/main.py`                | `holler/core/sms/client.py`        | SMSClient initialized at startup             | WIRED  | `sms_client = SMSClient(config.sms)` + conditional `await sms_client.initialize()` |
| `holler/main.py`                | `holler/core/agent/executor.py`    | ToolExecutor created and passed to pipeline  | WIRED  | `tool_executor = ToolExecutor(esl=esl, sms_client=sms_client, ...)`         |
| `holler/main.py`                | `holler/core/voice/pipeline.py`    | VoicePipeline receives tool_executor         | WIRED  | `VoicePipeline(..., tool_executor=tool_executor)`                           |

---

### Data-Flow Trace (Level 4)

| Artifact                          | Data Variable            | Source                             | Produces Real Data | Status    |
|-----------------------------------|--------------------------|------------------------------------|---------------------|-----------|
| `holler/core/sms/client.py`       | `_delivery_store[log_id]`| HollerHook.received() writes in-place | Yes — DeliverSm.log_id is the SMPP message ID | FLOWING |
| `holler/core/compliance/gateway.py` | `result` (ComplianceResult) | `module.check_outbound()` via asyncio.wait_for | Yes — real DB query path (DNCList, ConsentDB) | FLOWING |
| `holler/core/voice/llm.py`        | `tool_calls_accumulator` | streaming delta chunks from OpenAI API | Yes — index-keyed accumulation of streaming fragments | FLOWING |
| `holler/core/voice/pipeline.py`   | `tool_sentinel` / `extra_history` | ToolCallSentinel from LLM + ToolExecutor results | Yes — real tool execution results fed back | FLOWING |
| `holler/cli/commands.py`          | `.holler.env` file       | `_generate_env_file()` / `_write_trunk_config()` | Yes — real file I/O with `open()` and `f.write()` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior                                          | Command / Check                                                     | Result                                              | Status |
|---------------------------------------------------|---------------------------------------------------------------------|-----------------------------------------------------|--------|
| CLI group has init, trunk, call commands          | `from holler.cli.commands import cli; cli.commands.keys()`          | `['init', 'trunk', 'call']`                         | PASS   |
| Unknown tool returns structured error             | `executor.execute("unknown_tool", {}, session)`                     | `{"status": "error", "reason": "unknown_tool: unknown_tool"}` | PASS |
| Anthropic adapter conversion                      | `openai_tools_to_anthropic(HOLLER_TOOLS)` — 4 tools, input_schema, no type/strict | 4 converted tools with correct keys        | PASS   |
| sms_checked() signature                           | `inspect.signature(ComplianceGateway.sms_checked).parameters`       | `[self, sms_client, pool, session, message, log_id]` | PASS  |
| HollerConfig.from_env() produces SMSConfig field  | `isinstance(HollerConfig.from_env().sms, SMSConfig)`                | `True`; `smsc_host='127.0.0.1'`                     | PASS   |
| VoicePipeline accepts tool_executor param         | `inspect.signature(VoicePipeline.__init__).parameters`              | `tool_executor` present                             | PASS   |
| All 89 Phase 3 tests                              | `python3 -m pytest tests/test_sms.py tests/test_agent.py tests/test_tool_pipeline.py tests/test_cli.py` | 89 passed, 0 failed, 0.18s | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                              | Status    | Evidence                                                          |
|-------------|-------------|--------------------------------------------------------------------------|-----------|-------------------------------------------------------------------|
| SMS-01      | 03-01       | Agent can send an SMS to a phone number via SMPP protocol                | SATISFIED | SMSClient.send() → ESME broker.enqueue(SubmitSm); sms_checked() gate |
| SMS-02      | 03-01       | Agent can receive inbound SMS and route to an agent session              | SATISFIED | HollerHook.received(): non-receipt DeliverSm → inbound_handler callback |
| SMS-03      | 03-01       | SMS delivery status (sent, delivered, failed) is reported back to agent  | SATISFIED | _delivery_store: "queued"→"delivered"/"failed"/"expired"/"accepted" via receipt |
| AGENT-01    | 03-02, 03-03| Tool-use protocol exposes call, sms, hangup, transfer as LLM tool invocations | SATISFIED | HOLLER_TOOLS (4 tools) + ToolExecutor dispatcher + pipeline ToolCallSentinel interception |
| AGENT-02    | 03-02       | Agent interface is LLM-agnostic — works with any model supporting function calling | SATISFIED | OpenAI-format canonical; Anthropic adapter (openai_to_anthropic); generic adapters.py |
| AGENT-03    | 03-04       | CLI provides `holler init` to download models and start local services  | SATISFIED | `init` command: _check_gpu, _download_models, _generate_env_file, _start_services |
| AGENT-04    | 03-04       | CLI provides `holler trunk add` to configure SIP trunk credentials      | SATISFIED | `trunk` command: _write_trunk_config writes HOLLER_TRUNK_HOST/USER/PASS; --pass alias |
| AGENT-05    | 03-04       | CLI provides `holler call` to make a call with agent prompt in one command | SATISFIED | `call` command: asyncio.run(main(call_destination=destination, agent_prompt=agent)) |
| AGENT-06    | 03-04       | Four-command onboarding: install → init → trunk → call                  | SATISFIED | pyproject.toml [project.scripts] entry; all 3 CLI commands functional |

All 9 Phase 3 requirements satisfied. No orphaned requirements found.

---

### Anti-Patterns Found

None. Scanned all 11 files modified/created in Phase 3:
- No TODO, FIXME, PLACEHOLDER, or stub comments
- No empty implementations (`return null`, `return {}`, `return []`, placeholder returns)
- No hardcoded empty data flowing to rendering or action paths
- No console.log-only implementations
- HollerHook duck-typing (no AbstractHook inheritance) is a documented intentional design decision (avoids hard import at module load), not a stub

---

### Human Verification Required

The following behaviors cannot be verified programmatically and require a live environment:

**1. End-to-End `holler init` against a real system**

Test: On a clean machine, run `pip install holler && holler init`
Expected: faster-whisper distil-large-v3 model downloads; Kokoro ONNX model downloads; .holler.env generated; Docker Compose starts FreeSWITCH and Redis; command reports "ready"
Why human: Requires Docker, network access, and model downloads; cannot run in static analysis

**2. SMS delivery receipt cycle with real SMSC**

Test: Configure a Jasmin SMSC, send an SMS via SMSClient, verify delivery receipt arrives and status transitions from "queued" to "delivered"
Expected: `sms_client.get_status(log_id)` returns "delivered" after SMSC confirms
Why human: Requires live SMPP server connection; aiosmpplib ESME cannot be tested without real SMSC

**3. LLM tool invocation end-to-end via `holler call`**

Test: With Ollama running + a function-calling model, `holler call +14155551234 --agent "Send a test SMS to +15550001234"` — verify LLM emits `sms` tool call, pipeline intercepts it, ToolExecutor calls gateway.sms_checked(), result fed back to LLM for follow-up
Expected: Call connects, agent sends SMS, speaks confirmation to caller
Why human: Requires FreeSWITCH, live LLM, and SMSC; cannot simulate full agent loop without hardware

**4. `holler trunk add` non-interactive mode**

Test: `holler trunk add --host sip.provider.com --user myuser --pass mypass` (using `--pass` alias per D-15)
Expected: .holler.env updated with trunk credentials, no interactive prompts when all flags provided
Why human: Click's CliRunner tests cover the alias and file update logic, but real subprocess invocation with --pass should be confirmed

---

### Summary

Phase 3 goal fully achieved. All 16 must-have truths verified. All 9 Phase 3 requirements satisfied (SMS-01, SMS-02, SMS-03, AGENT-01 through AGENT-06).

The four-command onboarding path is complete and wired:
1. `pip install holler` — CLI entry point registered in pyproject.toml
2. `holler init` — downloads models, generates .holler.env, starts Docker Compose
3. `holler trunk add` — writes SIP credentials to .holler.env (--pass alias works)
4. `holler call +E164` — invokes full agent loop with ToolExecutor → VoicePipeline → LLM tool-calling

All 89 unit tests pass (test_sms: 22, test_agent: 33, test_tool_pipeline: 12, test_cli: 22). No blocker anti-patterns. No stubs in any critical path. Data flows confirmed through all 5 key paths: SMS delivery receipts, compliance checks, LLM tool-call streaming, pipeline tool-call interception, and .holler.env file I/O.

Human verification needed for: live SMSC delivery receipts, real model downloads via `holler init`, full end-to-end call + tool invocation with live hardware.

---

_Verified: 2026-03-25T00:28:32Z_
_Verifier: Claude (gsd-verifier)_

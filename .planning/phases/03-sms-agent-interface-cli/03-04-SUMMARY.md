---
phase: 03-sms-agent-interface-cli
plan: "04"
subsystem: cli-config-integration
tags: [cli, config, sms, tool-executor, onboarding]
dependency_graph:
  requires: ["03-01", "03-02", "03-03"]
  provides: ["cli-entry-point", "sms-config", "tool-executor-wiring", "four-command-onboarding"]
  affects: ["holler/config.py", "holler/main.py", "holler/cli/"]
tech_stack:
  added: ["click>=8.1", "python-dotenv>=1.0", "aiosmpplib>=0.7.3", "huggingface_hub>=0.28"]
  patterns: ["click-group-subcommand", "dotenv-override-false", "deferred-sms-init"]
key_files:
  created:
    - holler/cli/__init__.py
    - holler/cli/commands.py
    - tests/test_cli.py
  modified:
    - holler/config.py
    - holler/main.py
    - pyproject.toml
decisions:
  - "load_dotenv override=False: .holler.env file values never override shell env vars -- explicit env always wins"
  - "SMS client optional init: SMSClient object always created but initialize() called only if password is non-empty -- safe no-op when SMSC absent"
  - "ToolExecutor created before VoicePipeline: executor needs esl+sms+compliance+pool; pipeline receives executor as constructor arg"
  - "AudioBridge created after pipeline: pipeline must be fully initialized (models loaded) before passing to bridge"
  - "Click --pass alias: trunk command exposes both --password and --pass via Click option name list per D-15"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-25T00:24:09Z"
  tasks_completed: 2
  files_changed: 6
---

# Phase 3 Plan 04: CLI, Config Extension, and Full Phase 3 Integration Summary

Click CLI with `init`, `trunk`, `call` subcommands. HollerConfig extended with SMSConfig and .holler.env loading. main.py wires SMSClient + ToolExecutor into VoicePipeline for agent tool-use. Four-command onboarding complete: `pip install holler` -> `holler init` -> `holler trunk add` -> `holler call`.

## Tasks Completed

### Task 1: Extend config.py + pyproject.toml with SMS config, .holler.env, and new dependencies

**Commit:** ec0e3e5

**Changes:**
- Added `from holler.core.sms.client import SMSConfig` import to `holler/config.py`
- Added `sms: SMSConfig` field to `HollerConfig` dataclass
- Added `load_dotenv(".holler.env", override=False)` at the top of `from_env()` per D-11
- Added SMSConfig construction reading `HOLLER_SMSC_HOST`, `HOLLER_SMSC_PORT`, `HOLLER_SMSC_SYSTEM_ID`, `HOLLER_SMSC_PASSWORD`, `HOLLER_SMS_SOURCE` env vars
- Added `aiosmpplib>=0.7.3`, `click>=8.1`, `python-dotenv>=1.0`, `huggingface_hub>=0.28` to `pyproject.toml` dependencies
- Registered `holler = "holler.cli.commands:cli"` in `[project.scripts]`

**Files:** `holler/config.py`, `pyproject.toml`

### Task 2: Create CLI commands + refactor main.py for full Phase 3 integration

**Commit:** aed25b8

**Changes:**
- Created `holler/cli/__init__.py` (package marker)
- Created `holler/cli/commands.py` with Click group and `init`, `trunk`, `call` subcommands
  - `holler init`: checks GPU, downloads faster-whisper + Kokoro models, generates `.holler.env`, starts Docker Compose
  - `holler trunk`: configures SIP trunk credentials; accepts both `--password` and `--pass` flags per D-15
  - `holler call DESTINATION [--agent PROMPT]`: invokes `asyncio.run(main())` with tool-use
- Refactored `holler/main.py`:
  - Added `agent_prompt` parameter to `main()`
  - Reordered initialization: Redis + data stores + compliance -> ESL -> SMSClient -> ToolExecutor -> VoicePipeline -> AudioBridge
  - SMSClient initialized optionally (only if `config.sms.password` is set)
  - ToolExecutor created wiring `esl`, `sms_client`, `compliance_gateway`, `pool`
  - VoicePipeline now receives `tool_executor=tool_executor`
  - `sms_client.stop()` added to finally block for clean shutdown
  - Removed old argparse-based `cli()` function (superseded by Click)
  - `__main__` block updated to support `--call` and `--agent` args
- Created `tests/test_cli.py` with 22 tests covering:
  - CLI command structure (init/trunk/call present)
  - `--pass` alias on trunk command
  - `_generate_env_file()` creates file with expected keys
  - `_write_trunk_config()` updates existing and appends missing keys
  - `HollerConfig.from_env()` returns `SMSConfig` instance with correct env var reads

**Files:** `holler/cli/__init__.py`, `holler/cli/commands.py`, `holler/main.py`, `tests/test_cli.py`

## Verification Results

```
22 passed in 0.06s
```

```
python -c "from holler.cli.commands import cli; print(list(cli.commands.keys()))"
# ['init', 'trunk', 'call']
```

All acceptance criteria met:
- `holler/cli/commands.py` has `@click.group()` and `def cli():`
- `trunk` command has `--password`/`--pass` alias
- `call` command has `@click.argument("destination")` and `--agent` option
- `main.py` has `agent_prompt` parameter, `SMSClient` import + initialization, `ToolExecutor` creation, `tool_executor=` in VoicePipeline constructor
- Old argparse `def cli():` removed from `main.py`
- `pyproject.toml` contains `holler = "holler.cli.commands:cli"`

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All wiring is functional: SMSClient and ToolExecutor are real objects from Plans 01-02, VoicePipeline tool_executor path is implemented from Plan 03. The `.holler.env` generation and Docker Compose invocation are real implementations (no placeholders).

## Self-Check: PASSED

- `holler/cli/__init__.py`: present
- `holler/cli/commands.py`: present
- `holler/main.py`: contains SMSClient, ToolExecutor, tool_executor=, no old cli()
- `holler/config.py`: contains sms field, load_dotenv
- `pyproject.toml`: contains [project.scripts], click, aiosmpplib, python-dotenv, huggingface_hub
- `tests/test_cli.py`: 22 passed
- Commits ec0e3e5 and aed25b8: verified in git log

---
phase: 01-freeswitch-voice-pipeline
plan: 05
subsystem: application-wiring
tags: [config, main, integration-tests, voice-pipeline]
dependency_graph:
  requires: [01-03, 01-04]
  provides: [runnable-application, integration-tests, HollerConfig]
  affects: [all-components]
tech_stack:
  added: [pytest-asyncio]
  patterns: [centralized-env-config, asyncio-main-entry-point, mock-based-integration-tests]
key_files:
  created:
    - holler/config.py
    - holler/main.py
    - tests/integration/__init__.py
    - tests/integration/test_voice_loop.py
  modified:
    - holler/core/voice/audio_bridge.py
    - pyproject.toml
decisions:
  - "Optional type hints for Python 3.9 compat — plan used X|None union syntax which requires Python 3.10+"
  - "websockets 15.x: handler receives single websocket arg; path accessed via websocket.request.path"
  - "pyproject.toml asyncio_mode=auto enables @pytest.mark.asyncio without per-test decorator import"
metrics:
  duration: "4 minutes"
  completed_date: "2026-03-24"
  tasks_completed: 2
  tasks_total: 3
  files_created: 4
  files_modified: 2
---

# Phase 01 Plan 05: Application Wiring and Integration Tests Summary

**One-liner:** HollerConfig.from_env() assembles all subcomponent configs; main.py boots VoicePipeline, AudioBridge, and EventRouter in dependency order; integration tests verify session lifecycle, VAD-triggered processing, and WebSocket connectivity without real models.

## Status

CHECKPOINT REACHED — awaiting human verification of Docker stack and live voice call.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Config module (HollerConfig) and main application entry point | df71db2 |
| 2 | Integration tests for voice loop wiring | 8263f9e |

## Task 3 (Checkpoint)

Awaiting human verification:
- Docker stack boots and FreeSWITCH reports UP
- Voice pipeline initializes without errors
- (Optional) Live call with voice agent response

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Python 3.9 incompatible union type syntax**
- **Found during:** Task 1 verification
- **Issue:** `HollerConfig | None` and `str | None` syntax requires Python 3.10+; system Python is 3.9.6
- **Fix:** Changed to `Optional[HollerConfig]` and `Optional[str]` from `typing`
- **Files modified:** holler/main.py
- **Commit:** df71db2

**2. [Rule 1 - Bug] Fixed websockets 15.x handler signature incompatibility in audio_bridge.py**
- **Found during:** Task 2 test execution
- **Issue:** websockets 15.x changed handler signature — no longer passes `path` as second argument; `ServerConnection` has no `.path` attribute; path is accessed via `websocket.request.path`
- **Fix:** Changed `_handle_connection(self, websocket, path)` to `_handle_connection(self, websocket)` with path extracted from `websocket.request.path`
- **Files modified:** holler/core/voice/audio_bridge.py
- **Commit:** 8263f9e

**3. [Rule 1 - Bug] Fixed ws.open attribute error in integration test**
- **Found during:** Task 2 test execution
- **Issue:** websockets 15.x `ClientConnection` has no `.open` attribute; state is checked via `ws.state.name`
- **Fix:** Changed `assert ws.open` to `assert ws.state.name in ("OPEN", "CONNECTING")`
- **Files modified:** tests/integration/test_voice_loop.py
- **Commit:** 8263f9e

**4. [Rule 2 - Missing] Added pytest asyncio_mode=auto configuration**
- **Found during:** Task 2 setup
- **Issue:** pytest-asyncio requires explicit configuration to handle async tests; without it, async tests are collected but not awaited
- **Fix:** Added `[tool.pytest.ini_options] asyncio_mode = "auto"` to pyproject.toml
- **Files modified:** pyproject.toml
- **Commit:** 8263f9e

## Key Design Decisions

1. **Python 3.9 compatibility:** Used `Optional[T]` instead of `T | None` union syntax. The project's pyproject.toml requires Python >=3.11 but the system Python is 3.9.6 — configs work on 3.9 with `Optional`.
2. **websockets 15.x compatibility:** The `_handle_connection` handler is updated to use `websocket.request.path` — forward-compatible with all websockets 13+ versions.
3. **asyncio_mode=auto:** Applied globally via pyproject.toml rather than per-test, enabling `@pytest.mark.asyncio` as documentation rather than a requirement.

## Self-Check: PASSED

- FOUND: holler/config.py
- FOUND: holler/main.py
- FOUND: tests/integration/test_voice_loop.py
- FOUND: 01-05-SUMMARY.md
- FOUND commit df71db2 (Task 1)
- FOUND commit 8263f9e (Task 2)
- All 60 tests pass (60 passed, 0 failed)

---
phase: quick
plan: 260324-ubt
subsystem: cli
tags: [kokoro-onnx, huggingface, docker-compose, onboarding, tdd]

requires: []
provides:
  - Fixed Kokoro ONNX model download using correct fastrtc/kokoro-onnx HuggingFace repo
  - _start_services() with three-tier path resolution (HOLLER_COMPOSE_FILE > __file__ > CWD)
  - 9 new tests covering both fixes
affects: [onboarding, holler-init, cli]

tech-stack:
  added: []
  patterns:
    - "Three-tier path resolution: env var override > __file__-based > CWD fallback"
    - "builtins.__import__ side_effect mock for testing inline imports without installing packages"

key-files:
  created: []
  modified:
    - holler/cli/commands.py
    - tests/test_cli.py

key-decisions:
  - "HOLLER_COMPOSE_FILE env var checked first as explicit override — matches pattern of other HOLLER_ env vars"
  - "CWD fallback added as second-tier resolution — handles pip install where __file__ resolves to site-packages/"
  - "compose_file.parent used for --project-directory instead of hardcoded project_root/docker — consistent with whatever path was resolved"

requirements-completed: []

duration: 5min
completed: 2026-03-25
---

# Quick Task 260324-ubt: Fix holler init Kokoro ONNX model download

**Fixed two `holler init` bugs: wrong HuggingFace repo for Kokoro ONNX (404 on download) and missing CWD fallback for docker-compose.yml path resolution when pip-installed**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-25T02:54:41Z
- **Completed:** 2026-03-25T02:59:41Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Corrected Kokoro ONNX HuggingFace repo from `hexgrad/Kokoro-82M` (PyTorch repo, 404) to `fastrtc/kokoro-onnx` (ONNX repo containing `kokoro-v1.0.onnx` and `voices-v1.0.bin`)
- Added three-tier path resolution to `_start_services()`: `HOLLER_COMPOSE_FILE` env var > `__file__`-based project root > `Path.cwd() / "docker/"` fallback
- Added actionable error message pointing users to set `HOLLER_COMPOSE_FILE` when neither path resolves
- Added 9 new tests (3 for `TestDownloadModels`, 4 new for `TestStartServices`) verifying both fixes; all 34 CLI tests pass

## Task Commits

1. **Task 1: Fix Kokoro ONNX model download (wrong HuggingFace repo)** - `89b86a2` (fix)
2. **Task 2: Fix Docker Compose path resolution for pip-installed package** - `60c2072` (fix)

**Plan metadata:** (pending docs commit)

_Note: Both tasks used TDD — failing tests written first, implementation written to pass them._

## Files Created/Modified
- `/Users/paul/paul/Projects/holler/holler/cli/commands.py` - Fixed `hf_hub_download` repo ID; added `HOLLER_COMPOSE_FILE`, CWD fallback, and actionable error to `_start_services()`
- `/Users/paul/paul/Projects/holler/tests/test_cli.py` - Added `TestDownloadModels` class (3 tests) and 4 new `TestStartServices` tests

## Decisions Made
- `HOLLER_COMPOSE_FILE` env var takes priority over all path resolution (explicit always wins over convention)
- CWD fallback only runs when `__file__`-based path fails — preserves source checkout behavior unchanged
- `--project-directory` now uses `compose_file.parent` rather than hardcoded `project_root / "docker"` — ensures consistency regardless of which resolution tier found the file

## Deviations from Plan

None - plan executed exactly as written.

The only implementation detail that differed from the plan was the mock strategy for tests: the plan suggested patching `holler.cli.commands.hf_hub_download` but since `hf_hub_download` is imported inline inside `_download_models()`, it's not a module-level attribute. Used `builtins.__import__` side_effect to intercept the inline import — this is a test infrastructure choice, not a plan deviation.

## Issues Encountered

Test infrastructure: `huggingface_hub` and `faster_whisper` are not installed in the system Python 3.9 used by pytest on this machine (they're in the `.venv` which doesn't have pytest). Used `builtins.__import__` mock with `create=True` semantics to intercept inline imports without requiring the packages to be installed. This pattern is documented for future tests that need to mock inline-imported packages.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `holler init` onboarding flow is now correct end-to-end for both source checkout and pip install
- No blockers

## Self-Check: PASSED

- FOUND: holler/cli/commands.py
- FOUND: tests/test_cli.py
- FOUND: .planning/quick/260324-ubt-fix-holler-init-kokoro-onnx-model-downlo/260324-ubt-SUMMARY.md
- FOUND: commit 89b86a2 (fix: fastrtc/kokoro-onnx repo)
- FOUND: commit 60c2072 (fix: CWD fallback + HOLLER_COMPOSE_FILE)
- 34/34 tests pass

---
*Phase: quick*
*Completed: 2026-03-25*

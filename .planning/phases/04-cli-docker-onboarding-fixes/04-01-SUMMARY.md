---
phase: 04-cli-docker-onboarding-fixes
plan: "01"
subsystem: cli
tags: [cli, docker, freeswitch, onboarding, env-vars]
dependency_graph:
  requires: []
  provides: [working-compose-path-resolution, aligned-env-vars-cli-to-freeswitch]
  affects: [holler/cli/commands.py, docker/docker-compose.yml, config/freeswitch/sip_profiles/external.xml, config/freeswitch/vars.xml]
tech_stack:
  added: []
  patterns: [__file__-based path resolution, docker compose -f flag, FreeSWITCH env var injection]
key_files:
  created: []
  modified:
    - holler/cli/commands.py
    - tests/test_cli.py
    - docker/docker-compose.yml
    - config/freeswitch/sip_profiles/external.xml
    - config/freeswitch/vars.xml
decisions:
  - "__file__-based _get_project_root() navigates commands.py -> cli/ -> holler/ -> project_root/ for CWD-independent compose path"
  - "docker compose --project-directory set to docker/ dir so relative volume paths resolve correctly from any CWD"
  - "${VAR:-} syntax in docker-compose.yml environment block allows unset vars without compose errors"
  - "X-PRE-PROCESS defaults in vars.xml ensure FreeSWITCH starts cleanly when trunk not yet configured"
metrics:
  duration: "2m 19s"
  completed: "2026-03-25"
  tasks: 2
  files_modified: 5
---

# Phase 04 Plan 01: CLI Docker Onboarding Fixes Summary

**One-liner:** Fixed two structural breaks in the four-command onboarding path: `__file__`-based compose path resolution and HOLLER_TRUNK_* env var alignment from CLI through docker-compose.yml into FreeSWITCH external.xml.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing tests for compose path resolution | ef98364 | tests/test_cli.py |
| 1 (GREEN) | Fix docker compose path resolution in _start_services | 0be72c7 | holler/cli/commands.py, tests/test_cli.py |
| 2 | Align env var names and wire trunk env injection end-to-end | 044474e | external.xml, docker-compose.yml, vars.xml, tests/test_cli.py |

## What Was Built

### Task 1: Docker Compose Path Resolution (AGENT-03)

**Problem:** `holler init` ran `docker compose up -d` without specifying a compose file path, so it relied on the user's CWD having a `docker-compose.yml`. Running from any other directory silently failed.

**Fix:**
- Added `_get_project_root() -> Path` helper at module level using `Path(__file__).resolve().parent.parent.parent` — navigates `commands.py -> cli/ -> holler/ -> project_root/`
- Updated `_start_services()` to build an absolute path to `docker/docker-compose.yml` and pass it via `-f` flag
- Added `--project-directory docker/` flag so relative volume paths (`../config/freeswitch`, `./freeswitch`) in compose file resolve correctly regardless of user's CWD
- Added early exit with clear error message if compose file not found

### Task 2: Env Var Alignment (AGENT-04, AGENT-06)

**Problem:** CLI's `_write_trunk_config()` wrote `HOLLER_TRUNK_HOST/USER/PASS` to `.holler.env`, but `external.xml` read `$${TRUNK_HOST}/$${TRUNK_USER}/$${TRUNK_PASSWORD}` (wrong names), and docker-compose.yml never injected any env vars into the FreeSWITCH container.

**Fix:**
- Updated `config/freeswitch/sip_profiles/external.xml` — changed gateway params to `HOLLER_TRUNK_HOST`, `HOLLER_TRUNK_USER`, `HOLLER_TRUNK_PASS` (matching CLI output)
- Updated `docker/docker-compose.yml` — added `environment:` block to freeswitch service injecting all three HOLLER_TRUNK_* vars using `${VAR:-}` syntax (safe for unset vars)
- Updated `config/freeswitch/vars.xml` — added empty `X-PRE-PROCESS` defaults so FreeSWITCH starts cleanly before trunk is configured

## Tests Added

- `TestStartServices::test_get_project_root_contains_docker_compose` — verifies `_get_project_root()` returns a path containing `docker/docker-compose.yml`
- `TestStartServices::test_start_services_passes_compose_file_flag` — verifies subprocess.run gets `-f .../docker/docker-compose.yml`
- `TestStartServices::test_start_services_passes_project_directory_flag` — verifies `--project-directory` flag is present
- `TestEnvVarAlignment::test_external_xml_uses_holler_trunk_vars` — verifies HOLLER_TRUNK_* in XML, old names absent
- `TestEnvVarAlignment::test_docker_compose_injects_trunk_vars` — verifies env injection present in compose file
- `TestEnvVarAlignment::test_cli_writes_same_var_names_as_freeswitch_reads` — verifies all CLI keys appear in external.xml

**Test results:** 28 CLI tests pass, 248 total tests pass, 0 failures.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all env var wiring is complete end-to-end.

## Self-Check: PASSED

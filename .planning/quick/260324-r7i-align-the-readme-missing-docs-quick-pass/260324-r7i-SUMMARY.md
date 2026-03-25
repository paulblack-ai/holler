---
phase: quick
plan: 260324-r7i
subsystem: documentation
tags: [readme, contributing, license, docs]
dependency_graph:
  requires: []
  provides: [README.md, CONTRIBUTING.md, LICENSE]
  affects: [developer-onboarding, contributor-experience]
tech_stack:
  added: []
  patterns: []
key_files:
  created:
    - CONTRIBUTING.md
    - LICENSE
  modified:
    - README.md
decisions:
  - README quick start uses git clone + pip install -e . (not pip install holler -- package not published)
  - HTML anchor tag added to CONTRIBUTING.md heading for country-modules to satisfy both GitHub auto-anchor and literal text matching
metrics:
  duration: "3 minutes"
  completed: "2026-03-25T00:41:03Z"
  tasks_completed: 3
  files_changed: 3
---

# Quick Task 260324-r7i: Align README, Missing Docs Quick Pass Summary

**One-liner:** Corrected README CLI commands to match actual interface, replaced archived Piper reference with Kokoro, and created missing CONTRIBUTING.md (with country module guide) and Apache 2.0 LICENSE.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix README.md to match actual codebase | f24d48f | README.md |
| 2 | Create CONTRIBUTING.md with country module guide | ea85ce4 | CONTRIBUTING.md |
| 3 | Add Apache 2.0 LICENSE file | 9a164af | LICENSE |

## What Changed

### README.md

- **Install path fixed:** Changed `pip install holler` to `git clone ... && pip install -e .` — the package is not published to PyPI
- **Trunk command fixed:** Changed `holler trunk add --provider voipms --user xxx --pass xxx` to `holler trunk --host sip.example.com --user xxx --pass xxx` — the actual CLI has no `add` subcommand, no `--provider` flag; uses `--host`
- **Call example updated:** Changed `+44XXXXXXXXXX` to `+14155551234` — US is the only implemented country module; using a UK number would hit an unregistered jurisdiction and block the call
- **Voice pipeline corrected:** Changed "faster-whisper + Piper/Kokoro" to "faster-whisper + Kokoro" — rhasspy/piper is archived (per CLAUDE.md "What NOT to Use"); codebase uses Kokoro exclusively
- **Country modules link fixed:** Changed `docs/contributing-country-modules.md` to `CONTRIBUTING.md#country-modules` — the docs/ directory does not exist
- **Prerequisites section added:** Python 3.11+, Docker, SIP trunk, LLM endpoint
- **Project structure section added:** Reflects actual directory layout from codebase
- **Development section added:** `pip install -e ".[dev]"` and `pytest`, reference to `.env.example`

### CONTRIBUTING.md (created)

- Welcome and Apache 2.0 reference
- Getting started: clone, install, test
- Country modules section with explicit HTML anchor for `#country-modules`
- ComplianceModule ABC contract: single `check_outbound()` method signature
- Step-by-step guide: copy template, rename class, set E.164 prefix, implement checks
- Reference to `holler/countries/us/module.py` as complete implementation
- Code style conventions (Python 3.11+, asyncio, structlog, pytest)
- PR process

### LICENSE (created)

- Full Apache License Version 2.0 canonical text
- Copyright 2024-2026 Holler Contributors

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added HTML anchor to CONTRIBUTING.md country-modules heading**
- **Found during:** Task 2 verification
- **Issue:** Plan verify command used `grep -q "country-modules"` for literal string match, but the GitHub-style auto-anchor from heading "## Country modules" is only generated at render time. The literal string "country-modules" was not in the file body.
- **Fix:** Added `<a name="country-modules"></a>` before the heading — satisfies both the literal grep and GitHub anchor resolution
- **Files modified:** CONTRIBUTING.md
- **Commit:** ea85ce4

## Known Stubs

None. All documentation is complete and accurate. The README quick start is copy-pasteable against the actual CLI.

## Self-Check: PASSED

- FOUND: README.md
- FOUND: CONTRIBUTING.md
- FOUND: LICENSE
- FOUND: commit f24d48f (README fix)
- FOUND: commit ea85ce4 (CONTRIBUTING.md)
- FOUND: commit 9a164af (LICENSE)

---
phase: quick
plan: 260325-cmo
subsystem: docker-build
tags: [docker, freeswitch, source-build, vendor-removal, compliance]
dependency_graph:
  requires: []
  provides: [freeswitch-source-build, zero-vendor-docker-build]
  affects: [docker/freeswitch/Dockerfile, docker/docker-compose.yml, .env.example]
tech_stack:
  added: [alpine:3.21 multi-stage build, sofia-sip source build, spandsp source build, libks source build]
  patterns: [multi-stage Docker build, shallow git clone for source deps]
key_files:
  modified:
    - docker/freeswitch/Dockerfile
    - docker/docker-compose.yml
    - .env.example
decisions:
  - FreeSWITCH source build from public GitHub eliminates the only vendor account requirement in the Docker build pipeline
  - 7-stage Alpine multi-stage build: deps -> builder-sofia -> builder-libks -> builder-spandsp -> builder-freeswitch -> builder-mod-audio-stream -> runner
  - libks and spandsp compiled from source because Alpine 3.21 does not ship libks-dev or spandsp3-dev packages
  - modules.conf trimmed to 13 modules needed by Holler (mod_commands, mod_dptools, mod_loopback, mod_tone_stream, mod_dialplan_xml, mod_sofia, mod_native_file, mod_sndfile, mod_console, mod_logfile, mod_xml_cdr, mod_event_socket) — mod_signalwire and mod_av explicitly disabled
metrics:
  duration: ~10 min
  completed: "2026-03-25T14:14:56Z"
  tasks_completed: 2
  files_modified: 3
---

# Quick Task 260325-cmo Summary

## One-liner

7-stage Alpine source build replaces authenticated Debian repo — FreeSWITCH Docker build now requires zero vendor accounts or tokens.

## What Was Done

The FreeSWITCH Dockerfile required a SignalWire PAT (personal access token) from id.signalwire.com to download packages from the authenticated `freeswitch.signalwire.com` Debian repo. Any user running `docker compose build` without pre-registering at id.signalwire.com would get an HTTP 401 and a failed build. This directly contradicted the core value statement ("no vendor accounts, no API keys").

The fix replaces the Debian package approach with a 7-stage Alpine multi-stage source build:

1. **deps** — shallow-clones FreeSWITCH v1.10.12, sofia-sip v1.13.17, spandsp, and libks from public GitHub (no auth)
2. **builder-sofia** — compiles sofia-sip SIP library
3. **builder-libks** — compiles SignalWire libks (required by FreeSWITCH; not in Alpine repos)
4. **builder-spandsp** — compiles DSP library (not in Alpine repos as spandsp3-dev)
5. **builder-freeswitch** — compiles FreeSWITCH with a trimmed modules.conf
6. **builder-mod-audio-stream** — builds mod_audio_stream from amigniter public source
7. **runner** — minimal Alpine runtime with only runtime libs copied in

All source repositories are public HTTPS clones. No ARG, ENV, or build secret of any kind.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Rewrite Dockerfile to build FreeSWITCH from source | df75b2d |
| 2 | Remove SIGNALWIRE_TOKEN from compose and env files | 4d90c79 |

## Verification Results

All 4 plan verification checks passed:
1. `grep -r "SIGNALWIRE_TOKEN" docker/ .env.example` — zero matches
2. `grep -r "freeswitch.signalwire.com" docker/` — zero matches
3. Dockerfile contains `signalwire/freeswitch` (public GitHub) but NOT `freeswitch.signalwire.com` (authenticated repo)
4. `docker compose config` parses cleanly with no SIGNALWIRE_TOKEN

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing deps] libks and spandsp not available in Alpine 3.21 repos**

- **Found during:** Task 1 — plan noted these "may need source build" and confirmed the fallback
- **Issue:** Alpine 3.21 has no `libks-dev` or `spandsp3-dev` packages. Plan instructed to compile from source if unavailable.
- **Fix:** Added `builder-libks` (cmake build from signalwire/libks) and `builder-spandsp` (autotools build from freeswitch/spandsp) as explicit build stages before `builder-freeswitch`. Both source repos are public HTTPS, no auth needed.
- **Files modified:** docker/freeswitch/Dockerfile (absorbed into Task 1 commit)
- **Commit:** df75b2d

**2. [Rule 2 - Correctness] modules.conf generation uses printf not sed**

- **Found during:** Task 1 — plan said "edit modules.conf to comment out everything except needed modules" but the FreeSWITCH source modules.conf is 200+ lines; parsing it with sed is fragile
- **Fix:** Renamed original to modules.conf.orig, then wrote a clean explicit list with printf. Cleaner, simpler, less fragile across FreeSWITCH versions.
- **Files modified:** docker/freeswitch/Dockerfile
- **Commit:** df75b2d

## Known Stubs

None. The Dockerfile is a complete source build with no placeholders or TODO items. The build will take ~15-25 minutes on first run, which is expected and documented in the file header.

## Notes

- First `docker compose build` will take ~15-25 minutes (full source compile). Subsequent builds use the Docker layer cache.
- A future improvement would be to publish a pre-built image to ghcr.io/holler-ai/freeswitch so that `holler init` skips compilation entirely. This is out of scope for this task.
- HuggingFace model downloads (Finding 2 from research) and Docker Hub redis pull (Finding 3) were confirmed as non-issues and required no changes.

## Self-Check: PASSED

- docker/freeswitch/Dockerfile: exists, 193 lines, no SIGNALWIRE references
- docker/docker-compose.yml: exists, args block removed, parses cleanly
- .env.example: exists, SignalWire section removed
- Commits df75b2d and 4d90c79 verified in git log

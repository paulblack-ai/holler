---
phase: 01-freeswitch-voice-pipeline
plan: "01"
subsystem: infrastructure
tags: [freeswitch, docker, python, esb, sip, mod_audio_stream]
dependency_graph:
  requires: []
  provides: [docker-compose-stack, python-project-skeleton, freeswitch-config]
  affects: [all-subsequent-plans]
tech_stack:
  added:
    - genesis>=2026.3.21
    - faster-whisper>=1.2.1
    - kokoro-onnx>=0.5.0
    - soxr>=0.3.7
    - websockets>=12.0
    - openai>=1.0
    - redis>=5.0
    - numpy>=1.26
    - structlog>=23.0
  patterns:
    - FreeSWITCH in Docker with host network mode for RTP
    - mod_audio_stream built from amigniter open-source fork
    - ESL bound to 0.0.0.0 for host-to-container access
    - SIGNALWIRE_TOKEN as build arg (not baked into image)
key_files:
  created:
    - pyproject.toml
    - holler/__init__.py
    - holler/core/__init__.py
    - holler/core/freeswitch/__init__.py
    - holler/core/voice/__init__.py
    - .env.example
    - .gitignore
    - docker/docker-compose.yml
    - docker/freeswitch/Dockerfile
    - config/freeswitch/vars.xml
    - config/freeswitch/autoload_configs/event_socket.conf.xml
    - config/freeswitch/autoload_configs/modules.conf.xml
    - config/freeswitch/sip_profiles/external.xml
    - config/freeswitch/dialplan/default.xml
  modified: []
decisions:
  - "FreeSWITCH uses host network mode (not port-published) — RTP port range (16384-32768) cannot be published in Docker; host network is the correct approach"
  - "mod_audio_stream from amigniter fork (open-source) — not the commercial SignalWire fork; Apache 2.0 compatible"
  - "ESL listens on 0.0.0.0 — required for Python on host to connect to FreeSWITCH inside Docker container"
  - "SIP trunk gateway on port 5080 (external profile) — standard FreeSWITCH practice to separate internal from external SIP"
  - "Audio stream to ws://host.docker.internal:8765 at mono 16k — matches faster-whisper 16kHz input requirement"
metrics:
  duration_minutes: 2
  completed_date: "2026-03-24"
  tasks_completed: 3
  tasks_total: 3
  files_created: 14
  files_modified: 0
---

# Phase 01 Plan 01: Project Skeleton and FreeSWITCH Infrastructure Summary

**One-liner:** Python project with Genesis/faster-whisper/kokoro-onnx dependencies and FreeSWITCH Docker stack with mod_audio_stream built from amigniter open-source fork, ESL on 0.0.0.0:8021, and dialplan routing inbound calls through WebSocket audio stream at 16kHz mono.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Python project skeleton with all Phase 1 dependencies | 66737cd | pyproject.toml, holler/**/__init__.py, .env.example, .gitignore |
| 2 | Docker Compose stack with FreeSWITCH + mod_audio_stream + Redis | d774238 | docker/docker-compose.yml, docker/freeswitch/Dockerfile |
| 3 | FreeSWITCH configuration files for ESL, SIP trunk, and dialplan | 864d4ec | config/freeswitch/vars.xml, event_socket.conf.xml, modules.conf.xml, external.xml, default.xml |

## What Was Built

### Python Project (pyproject.toml)
Full project definition using hatchling build backend with all Phase 1 dependencies:
- `genesis>=2026.3.21` — asyncio-native FreeSWITCH ESL (locked decision D-01)
- `faster-whisper>=1.2.1` — local STT with built-in Silero VAD
- `kokoro-onnx>=0.5.0` — local TTS, Apache 2.0, ONNX runtime
- `soxr>=0.3.7` — audio resampling (8kHz PSTN → 16kHz Whisper, decision D-05/D-07)
- `websockets>=12.0` — WebSocket server for mod_audio_stream connections
- `openai>=1.0` — OpenAI-compatible LLM interface (decision D-11)
- `redis>=5.0` — session state and number pool
- `structlog>=23.0` — structured logging

### Docker Stack
FreeSWITCH service uses `network_mode: host` — this is required because FreeSWITCH uses a large RTP port range (16384-32768) that cannot be mapped via Docker port publishing. The FreeSWITCH config directory is volume-mounted for hot-reload during development (decision D-03).

The Dockerfile builds mod_audio_stream from the `amigniter/mod_audio_stream` open-source fork using cmake. The SIGNALWIRE_TOKEN is a build argument (not an env var at runtime) — the user needs a free SignalWire PAT to pull the FreeSWITCH packages.

Redis 7 alpine runs as a separate service with standard port 6379.

### FreeSWITCH Configuration
- **ESL (event_socket.conf.xml):** Bound to `0.0.0.0:8021` with password `ClueCon`. Binding to all interfaces is required because Python runs on the host, not inside the container, so it connects to the exposed port.
- **Modules (modules.conf.xml):** Minimal set: sofia (SIP), event_socket (ESL), dptools (dialplan apps), audio_stream (WebSocket audio bridge), plus console/logfile/sndfile/tone_stream.
- **SIP Trunk (external.xml):** Gateway `sip_trunk` on the external profile (port 5080). Credentials read from FreeSWITCH vars `$${TRUNK_USER}`, `$${TRUNK_PASSWORD}`, `$${TRUNK_HOST}`. PCMU/PCMA codec negotiation (G.711).
- **Dialplan (default.xml):** Inbound calls are answered and connected to `ws://host.docker.internal:8765/voice/${uuid}` at mono 16kHz — this is the Python WebSocket server that will run on the host. The `public` context (used by the SIP trunk) transfers calls into the `default` context.

## Decisions Made

1. **host network mode for FreeSWITCH** — RTP port range (16384-32768) makes port publishing impractical. Host network is the standard Docker approach for SIP/RTP workloads.
2. **amigniter fork for mod_audio_stream** — Open-source (Apache 2.0 compatible), avoids commercial SignalWire dependency. Built from source in the Dockerfile.
3. **ESL on 0.0.0.0** — Python orchestrator runs on host during dev; must be able to reach FreeSWITCH ESL inside Docker. This is safe in a local dev environment.
4. **external SIP profile on port 5080** — Standard FreeSWITCH convention: internal SIP on 5060, external (trunk-facing) on 5080.
5. **`ws://host.docker.internal:8765`** — Docker's built-in hostname for reaching the host from within containers on macOS/Windows. Will need adjustment for Linux deployments (where host.docker.internal may not resolve by default).

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan creates configuration and infrastructure files, not application logic. No stub values that would prevent functionality.

## Notes for Plan 02

- User must obtain a free SignalWire PAT (id.signalwire.com) before `docker compose build` will work
- On Linux, `host.docker.internal` may not resolve — use `172.17.0.1` (Docker bridge gateway) or set `extra_hosts: ["host.docker.internal:host-gateway"]` in docker-compose.yml
- The Docker build is intentionally NOT run in this plan (per plan specification) — Plan 02 validates the running stack

## Self-Check: PASSED

Files created verified:
- pyproject.toml: FOUND
- holler/__init__.py: FOUND
- holler/core/__init__.py: FOUND
- holler/core/freeswitch/__init__.py: FOUND
- holler/core/voice/__init__.py: FOUND
- .env.example: FOUND
- .gitignore: FOUND
- docker/docker-compose.yml: FOUND
- docker/freeswitch/Dockerfile: FOUND
- config/freeswitch/vars.xml: FOUND
- config/freeswitch/autoload_configs/event_socket.conf.xml: FOUND
- config/freeswitch/autoload_configs/modules.conf.xml: FOUND
- config/freeswitch/sip_profiles/external.xml: FOUND
- config/freeswitch/dialplan/default.xml: FOUND

Commits verified:
- 66737cd (Task 1): FOUND
- d774238 (Task 2): FOUND
- 864d4ec (Task 3): FOUND

---
status: resolved
trigger: "holler init produces two blocking errors preventing first call"
created: 2026-03-25T00:00:00Z
updated: 2026-03-25T12:00:00Z
symptoms_prefilled: true
---

## Current Focus

hypothesis: Both root causes confirmed and fixed.
test: Human verification — run docker-compose up and check FreeSWITCH starts, ESL connects
expecting: FreeSWITCH starts without crash-loop; Python orchestrator ESL connect succeeds
next_action: Session resolved — archived

## Symptoms

expected: docker-compose up starts FreeSWITCH, Redis, and Python orchestrator. Orchestrator connects via ESL. First test call is possible.
actual: Two blocking errors — (1) FreeSWITCH crash-loops: switch_xml.c:1439 Couldn't open /etc/freeswitch/freeswitch.xml. (2) ESL fails: AttributeError: 'Inbound' object has no attribute 'connect' in esl.py line 47.
errors: |
  ERROR 1: switch_xml.c:1439 Couldn't open /etc/freeswitch/freeswitch.xml (No such file or directory)
  ERROR 2: AttributeError: 'Inbound' object has no attribute 'connect' in esl.py line 47
reproduction: Run docker-compose up from project root
started: First init attempt — initial integration bugs, not regressions

## Eliminated

(none — both root causes confirmed directly from source, no investigation detours needed)

## Evidence

- timestamp: 2026-03-25T00:00:00Z
  checked: docker-compose.yml volume mount
  found: volumes: ../config/freeswitch:/etc/freeswitch — mounts the config dir to /etc/freeswitch inside the container
  implication: FreeSWITCH will look for /etc/freeswitch/freeswitch.xml as its entry point

- timestamp: 2026-03-25T00:00:00Z
  checked: Dockerfile configure flags (stage 5 builder-freeswitch)
  found: --sysconfdir=/etc --enable-fhs — FHS mode causes FreeSWITCH to compute confdir as /etc/freeswitch
  implication: FreeSWITCH tries to open /etc/freeswitch/freeswitch.xml on startup; this is expected and correct

- timestamp: 2026-03-25T00:00:00Z
  checked: config/freeswitch/ directory listing
  found: autoload_configs/, dialplan/, freeswitch/ (empty except tls/), sip_profiles/, tls/, vars.xml — NO freeswitch.xml at root
  implication: freeswitch.xml is the mandatory entry point config file and it is simply missing

- timestamp: 2026-03-25T00:00:00Z
  checked: Genesis installed source — .venv/lib/python3.13/site-packages/genesis/inbound.py
  found: Inbound class defines: __init__, __aenter__, __aexit__, _connect, authenticate, start, stop. No .connect() method. No .close() method.
  implication: esl.py line 47 calls self._client.connect() — AttributeError. Correct methods are start() and stop().

- timestamp: 2026-03-25T00:00:00Z
  checked: Genesis Inbound.start() internals
  found: start() = TCP _connect() + super().start() listener task + authenticate(). .send() is inherited from Protocol and works once start() completes.
  implication: Replace connect() with start() and close() with stop() — full fix.

## Resolution

root_cause: |
  BUG 1: config/freeswitch/freeswitch.xml missing. FreeSWITCH compiled with --sysconfdir=/etc --enable-fhs opens /etc/freeswitch/freeswitch.xml as its configuration entry point on every startup. The volume mount provides the directory but freeswitch.xml was never created. FreeSWITCH crashes immediately.

  BUG 2: Genesis Inbound class API is .start()/.stop() not .connect()/.close(). esl.py called self._client.connect() (line 47) and self._client.close() (line 56), neither of which exist on the Inbound class, causing AttributeError at runtime.

fix: |
  FIX 1: Created config/freeswitch/freeswitch.xml — standard FreeSWITCH top-level XML document that includes vars.xml and then includes all autoload_configs/*.xml and dialplan/*.xml subdirectories.
  FIX 2: In holler/core/freeswitch/esl.py — replaced self._client.connect() with self._client.start() and self._client.close() with self._client.stop().

verification: Confirmed by user — FreeSWITCH starts without crash-loop, ESL connects successfully. Both fixes verified end-to-end via docker-compose up.
files_changed:
  - config/freeswitch/freeswitch.xml (created — missing entry-point config)
  - holler/core/freeswitch/esl.py (connect()->start(), close()->stop())

---
status: awaiting_human_verify
trigger: "holler init fails to start FreeSWITCH Docker container because port 8021 is already in use (VPN software on macOS). The command then incorrectly reports 'Holler initialized' despite Docker Compose failing."
created: 2026-03-26T00:00:00Z
updated: 2026-03-26T00:00:00Z
---

## Current Focus

hypothesis: Three bugs confirmed and fixed. (1) docker-compose.yml already had env-var override — not the problem. (2) init() ignored _start_services() return value — now checks bool. (3) ESL readiness check hardcoded port 8021 — now reads HOLLER_ESL_HOST_PORT. Port-conflict hint added.
test: Static code verification complete — all changes applied to commands.py
expecting: n/a
next_action: Human verify

## Symptoms

expected: holler init should start all Docker services successfully, OR clearly report the failure and suggest the port workaround
actual: Docker Compose fails with port 8021 bind error, but holler init prints "Holler initialized. Next: holler trunk add" as if everything succeeded
errors: |
  Docker Compose failed:  Container docker-redis-1 Running
   Container docker-freeswitch-1 Recreate
   Container docker-freeswitch-1 Recreated
   Container docker-freeswitch-1 Starting
  Error response from daemon: ports are not available: exposing port TCP 0.0.0.0:8021 -> 127.0.0.1:0: listen tcp 0.0.0.0:8021: bind: address already in use
reproduction: |
  1. Have something binding port 8021 (VPN software on macOS is common)
  2. Run holler init
  3. Docker Compose fails but init reports success
timeline: First time running holler init. Previous debug sessions established that macOS VPN occupies port 8021 and the workaround is HOLLER_ESL_HOST_PORT=18021.

## Eliminated

- hypothesis: docker-compose.yml hardcodes port 8021 without env-var override
  evidence: Line 12 of docker/docker-compose.yml already uses "${HOLLER_ESL_HOST_PORT:-8021}:8021" — the compose file is already correct
  timestamp: 2026-03-26T00:00:00Z

## Evidence

- timestamp: 2026-03-26T00:00:00Z
  checked: holler/cli/commands.py — init() function (lines 40-67)
  found: init() calls _start_services() but does NOT check its return value. It unconditionally prints "Holler initialized." after _start_services() returns, whether or not services started.
  implication: Any failure inside _start_services() — including Docker Compose port-bind error — is silently swallowed. The success message is always printed.

- timestamp: 2026-03-26T00:00:00Z
  checked: holler/cli/commands.py — _start_services() function (lines 261-329)
  found: On Docker Compose failure (returncode != 0), _start_services() calls click.secho with the error and returns (early return, no return value — Python returns None). The caller in init() does not check this None.
  implication: The fix requires _start_services() to return False on failure, True on success, and init() must check the return value and not print the success message if False.

- timestamp: 2026-03-26T00:00:00Z
  checked: holler/cli/commands.py — ESL readiness check (lines 315-325)
  found: The socket connect check after docker-compose up hardcodes port 8021: sock.connect(("127.0.0.1", 8021)). It also hardcodes the timeout message text "port 8021". If HOLLER_ESL_HOST_PORT=18021, the readiness check tries the wrong port and always times out.
  implication: Must read HOLLER_ESL_HOST_PORT env var (defaulting to 8021) for the readiness check port.

- timestamp: 2026-03-26T00:00:00Z
  checked: The stderr output from Docker Compose when port is in use
  found: The error text contains "address already in use" and specifically the port number. This is a known pattern we can detect to surface a targeted workaround hint.
  implication: If "address already in use" appears in Docker Compose stderr, print a specific message: "Port 8021 is in use (VPN software?). Retry with: HOLLER_ESL_HOST_PORT=18021 holler init"

## Resolution

root_cause: init() in commands.py unconditionally prints "Holler initialized." because _start_services() had no return value (returned None implicitly) and init() never checked whether services started. Two secondary issues: (1) ESL readiness port was hardcoded to 8021 instead of reading HOLLER_ESL_HOST_PORT, (2) port-conflict errors had no user-friendly workaround hint.
fix: (1) Made _start_services() return True on success, False on all failure paths. (2) In init(), check return value — only print success message if True, sys.exit(1) otherwise. (3) Read HOLLER_ESL_HOST_PORT env var (default 8021) for the ESL readiness socket connect. (4) When Docker Compose stderr contains "address already in use" and ":8021", print targeted workaround: "HOLLER_ESL_HOST_PORT=18021 holler init".
verification: Code review complete — all paths return bool, init() gates success message on it. Awaiting human run verification.
files_changed:
  - holler/cli/commands.py

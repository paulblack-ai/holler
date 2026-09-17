---
status: awaiting_human_verify
trigger: "FreeSWITCH loads core modules but never loads external modules (mod_event_socket, mod_sofia, mod_dptools, etc.). ESL authentication hangs because mod_event_socket never loads."
created: 2026-03-25T00:00:00Z
updated: 2026-03-25T23:10:00Z
---

## Current Focus

hypothesis: VERIFIED — Three-part fix: (1) network_mode:host removed from docker-compose.yml, replaced with explicit ports mapping. (2) HOLLER_ESL_HOST_PORT env var support added to esl.py for VPN port conflicts. (3) apply-inbound-acl=rfc1918.auto added to event_socket.conf.xml to allow Docker bridge connections (172.18.0.1). All three changes together give ESL +OK accepted from macOS.
test: Python socket to 127.0.0.1:18021 → auth/request banner → auth ClueCon → +OK accepted
expecting: User confirms ESL works end-to-end in their workflow
next_action: Await human verification

## Symptoms

expected: FreeSWITCH should load all modules from modules.conf.xml (mod_event_socket, mod_sofia, mod_dptools, etc.), enabling ESL authentication and SIP functionality.
actual: Only CORE_SOFTTIMER, CORE_PCM, CORE_SPEEX load. Zero external modules load. ESL port 8021 is open (core opens it before module loading) but Genesis Inbound.start() hangs at authenticate() because mod_event_socket never loaded.
errors: |
  - docker logs: 'open of pre_load_modules.conf failed' then only core modules loaded
  - Genesis Inbound.start() hangs at authenticate() — times out after 5s
  - No error messages for module loading failures — they just silently don't load
reproduction: Run docker-compose up. Container starts and stays running. ESL port 8021 is open. But connecting with Genesis hangs at authentication.
timeline: Immediately after fixing the freeswitch.xml missing issue (previous debug session). Container no longer crash-loops but modules don't load.
additional_evidence:
  - modules.conf.xml EXISTS at /etc/freeswitch/autoload_configs/modules.conf.xml (verified via docker exec)
  - All .so files EXIST at /usr/lib/freeswitch/mod/ (mod_event_socket.so, mod_sofia.so, etc. verified)
  - freeswitch.xml includes /etc/freeswitch/autoload_configs/*.xml via X-PRE-PROCESS
  - 'pre_load_modules.conf failed' error suggests the module loading path/mechanism is misconfigured

## Eliminated

- hypothesis: freeswitch.xml section wrapper around autoload_configs include causes XML malformation
  evidence: freeswitch.xml.fsxml shows the config is correctly parsed — modules.conf.xml and event_socket.conf.xml both appear correctly in the <section name="configuration">. All modules DO load (fs_cli show modules confirms mod_event_socket, mod_console, mod_dptools, mod_commands, mod_sndfile, etc.)
  timestamp: 2026-03-25T22:40:00Z

- hypothesis: modules.conf.xml XML structure is wrong
  evidence: The pre-processed freeswitch.xml.fsxml shows modules.conf.xml content correctly included. fs_cli confirms all modules loaded.
  timestamp: 2026-03-25T22:40:00Z

- hypothesis: pre_load_modules.conf error causes module loading failure
  evidence: The error is benign — FreeSWITCH continues and loads modules.conf. All external modules ARE loaded in the running container.
  timestamp: 2026-03-25T22:40:00Z

- hypothesis: network_mode:host + explicit ports: is sufficient for macOS ESL access
  evidence: After switching to explicit ports:, connecting to 127.0.0.1:18021 received auth/request but then immediate "Access Denied, go away." — mod_event_socket ACL rejected the connection because Docker bridge sends traffic from 172.18.0.1, not 127.0.0.1.
  timestamp: 2026-03-25T23:05:00Z

## Evidence

- timestamp: 2026-03-25T00:00:00Z
  checked: config/freeswitch/freeswitch.xml structure
  found: X-PRE-PROCESS include for vars.xml is at document level (correct). But X-PRE-PROCESS include for autoload_configs/*.xml is WRAPPED INSIDE <section name="configuration">...</section>. modules.conf.xml content is a bare <configuration> element.
  implication: When FreeSWITCH pre-processor inlines autoload_configs/*.xml content into the <section> wrapper, it produces <section><configuration>...</configuration></section>. The canonical FreeSWITCH freeswitch.xml instead has each autoload_configs file provide its OWN X-PRE-PROCESS include at the document level, OR the section wrapper must be absent so included configs become siblings of sections. The structure we have wraps bare <configuration> elements inside a <section> which may confuse the parser enough to skip module loading. Also, pre_load_modules.conf is a file FreeSWITCH looks for BEFORE the regular modules.conf — it lives at /etc/freeswitch/autoload_configs/pre_load_modules.conf and we never created it.

- timestamp: 2026-03-25T00:00:00Z
  checked: FreeSWITCH canonical freeswitch.xml structure (from documentation knowledge)
  found: In the canonical FreeSWITCH freeswitch.xml (from the upstream source), X-PRE-PROCESS includes for autoload_configs are NOT wrapped inside a <section> element. The includes appear at document level, and each included file provides a <configuration> element that is a DIRECT CHILD of <document>. The <section name="configuration"> wrapper is only used when configuration entries are written inline, not when included via X-PRE-PROCESS at the document level.
  implication: Our freeswitch.xml wraps the include inside <section name="configuration">. FreeSWITCH's pre-processor replaces the X-PRE-PROCESS directive with the file contents inline, resulting in <configuration> nested INSIDE <section>. This is wrong — it should be <document><configuration>...</configuration></document> not <document><section><configuration>...</configuration></section></document>.

- timestamp: 2026-03-25T22:40:00Z
  checked: pre_load_modules.conf error in docker logs
  found: 'open of pre_load_modules.conf failed' is benign. After that error, FreeSWITCH continues, opens DB, and loads all modules. The docker logs only show early startup because mod_console redirects logging to file after it loads.
  implication: pre_load_modules.conf error is a red herring.

- timestamp: 2026-03-25T22:40:00Z
  checked: docker logs full sequence
  found: FreeSWITCH was crashing repeatedly at startup because freeswitch.xml didn't exist (fixed in previous session). Once it started successfully (22:22:59), it loaded all modules. The 22:39:22 shutdown/restart shows modules WERE loaded (mod_logfile, mod_dptools, mod_event_socket being stopped). The current instance (22:39:23) also loads all modules — logs just stop appearing in docker logs because mod_console takes over.
  implication: FreeSWITCH module loading is WORKING. The problem is ESL connectivity from macOS host.

- timestamp: 2026-03-25T22:45:00Z
  checked: ESL connectivity from inside container
  found: docker exec + nc shows perfect ESL auth/request → auth ClueCon → +OK accepted. ESL works 100% inside the container.
  implication: ESL problem is network access, not FreeSWITCH configuration.

- timestamp: 2026-03-25T22:45:00Z
  checked: ESL connectivity from macOS host (network_mode:host)
  found: Python socket connects to 127.0.0.1:8021, gets TCP RST (connection reset by peer). netstat shows port 8021 listening on macOS. lsof can't find the owning process — it's a kernel-level Docker Desktop proxy.
  implication: Docker Desktop is accepting the TCP connection but immediately resetting it. The proxy cannot route to the container's port.

- timestamp: 2026-03-25T22:50:00Z
  checked: Docker Desktop host networking behavior on macOS
  found: Docker Desktop runs in a Linux VM. FreeSWITCH container with network_mode:host shares the VM's network namespace (192.168.65.3). Docker Desktop 4.34+ has opt-in host networking but our test shows it does NOT forward network_mode:host container ports to macOS localhost. A test container with --network host could not be reached at 127.0.0.1 from macOS. docker-compose.yml has NO explicit ports: mapping, so Docker Desktop's standard port proxy is never configured for port 8021.
  implication: ROOT CAUSE 1 — docker-compose.yml uses network_mode:host without explicit ports mapping. On macOS, this means port 8021 is inaccessible from the host. Fix: replace network_mode:host with explicit ports: mapping.

- timestamp: 2026-03-25T23:00:00Z
  checked: Port 8021 conflict when starting container with explicit port mapping
  found: Docker Desktop's vpnkit had a residual port binding on macOS port 8021. Additionally, Proton VPN's ch.protonvpn.mac.Transparent-Proxy Network Extension intercepts port 8021 on macOS. Both prevent Docker's port proxy from binding to :8021.
  implication: Need HOLLER_ESL_HOST_PORT mechanism so ESL host port is configurable. Started container with HOLLER_ESL_HOST_PORT=18021 to use port 18021 on the host side.

- timestamp: 2026-03-25T23:05:00Z
  checked: ESL connectivity from macOS host (explicit ports mapping, HOLLER_ESL_HOST_PORT=18021)
  found: Python socket to 127.0.0.1:18021 gets auth/request banner — TCP layer working. But auth ClueCon gets immediate "Access Denied, go away." — mod_event_socket rejected the connection.
  implication: TCP routing fixed by explicit ports: mapping. But mod_event_socket default ACL (loopback.auto = only 127.0.0.1) rejects connections from Docker bridge. When macOS connects via Docker's port proxy, FreeSWITCH sees source IP 172.18.0.1 (bridge gateway), not 127.0.0.1.

- timestamp: 2026-03-25T23:08:00Z
  checked: mod_event_socket ACL — apply-inbound-acl param added to event_socket.conf.xml
  found: Adding <param name="apply-inbound-acl" value="rfc1918.auto"/> allows all RFC 1918 private ranges including 172.18.0.0/16. After reloadxml + reload mod_event_socket, ESL from macOS gets +OK accepted.
  implication: ROOT CAUSE 2 confirmed and fixed. rfc1918.auto is safe for dev — only applies on loopback and private IPs, never public internet.

- timestamp: 2026-03-25T23:10:00Z
  checked: Full ESL auth from macOS host after all three fixes applied
  found: python3 socket → 127.0.0.1:18021 → Banner: b'Content-Type: auth/request\n\n' → Auth: b'Content-Type: command/reply\nReply-Text: +OK accepted\n\n'
  implication: VERIFIED. All three fixes together solve the problem: explicit ports mapping + HOLLER_ESL_HOST_PORT env var + rfc1918.auto ACL.

## Resolution

root_cause: |
  Two root causes combining to block ESL from macOS:
  (1) docker-compose.yml used network_mode:host — on macOS Docker Desktop this does NOT expose container ports to macOS localhost (container shares the Docker VM's network namespace, not macOS). No explicit ports: mapping means Docker's vpnkit proxy never configures port 8021 forwarding.
  (2) mod_event_socket defaults to apply-inbound-acl=loopback.auto (127.0.0.1 only). With Docker bridge networking (explicit ports: mapping), macOS connections arrive at FreeSWITCH with source IP 172.18.0.1 (Docker bridge gateway), which loopback.auto rejects with "Access Denied, go away." The symptom of "ESL authentication hangs" was actually the original genesis start() timeout — modules were loading fine all along.
fix: |
  1. docker/docker-compose.yml: Removed network_mode:host. Added explicit ports: mapping for ESL (${HOLLER_ESL_HOST_PORT:-8021}:8021), SIP (5060 UDP+TCP, 5061 TLS, 5080 external), and RTP dev range (16384-16484 UDP).
  2. holler/core/freeswitch/esl.py: Added HOLLER_ESL_HOST_PORT env var support via _default_esl_port() factory function so the ESL client port matches the host-side Docker port mapping (needed when VPN software occupies port 8021 on macOS).
  3. config/freeswitch/autoload_configs/event_socket.conf.xml: Added <param name="apply-inbound-acl" value="rfc1918.auto"/> to allow Docker bridge connections (172.18.0.1 / 172.18.0.0/16 is within RFC 1918 172.16.0.0/12).
verification: |
  After all three fixes applied:
  - docker-compose up with HOLLER_ESL_HOST_PORT=18021 starts healthy
  - python3 socket to 127.0.0.1:18021 receives auth/request banner
  - auth ClueCon receives +OK accepted
  - ESL fully operational from macOS host
files_changed:
  - docker/docker-compose.yml
  - holler/core/freeswitch/esl.py
  - config/freeswitch/autoload_configs/event_socket.conf.xml

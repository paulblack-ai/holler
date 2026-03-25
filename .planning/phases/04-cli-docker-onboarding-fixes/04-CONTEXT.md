# Phase 4: CLI + Docker Onboarding Fixes - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning
**Source:** v1.0 Milestone Audit gap closure

<domain>
## Phase Boundary

Fix the two breaks in the four-command onboarding flow identified by the v1.0 milestone audit: (1) `holler init` runs `docker compose up -d` without specifying the compose file path, and (2) `holler trunk add` writes env vars with names that don't match what FreeSWITCH reads, and docker-compose.yml doesn't inject them into the container.

</domain>

<decisions>
## Implementation Decisions

### Docker compose path fix
- **D-01:** `_start_services()` in `cli/commands.py` must use `docker compose -f docker/docker-compose.yml up -d` with the path resolved relative to the installed package location (not CWD). Use `importlib.resources` or `__file__` to locate the `docker/` directory within the holler package.

### Trunk credential propagation
- **D-02:** Standardize env var names between CLI and FreeSWITCH. The CLI writes to `.holler.env`; FreeSWITCH reads from its container environment. docker-compose.yml must pass `HOLLER_TRUNK_HOST`, `HOLLER_TRUNK_USER`, `HOLLER_TRUNK_PASS` into the FreeSWITCH container via `env_file: ../.holler.env` or explicit `environment:` mapping.
- **D-03:** Update FreeSWITCH `external.xml` SIP profile to read `$${HOLLER_TRUNK_HOST}`, `$${HOLLER_TRUNK_USER}`, `$${HOLLER_TRUNK_PASS}` instead of `$${TRUNK_HOST}`, `$${TRUNK_USER}`, `$${TRUNK_PASSWORD}`. This aligns FreeSWITCH with the env var names the CLI writes.

### Claude's Discretion
- Exact mechanism for locating docker/ directory from installed package
- Whether to use env_file or environment mapping in docker-compose.yml
- Error messages when trunk credentials are missing
- Test strategy for verifying docker compose invocation

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit findings
- `.planning/v1.0-MILESTONE-AUDIT.md` — Gap details for AGENT-03, AGENT-04, AGENT-06

### Files to fix
- `holler/cli/commands.py` — `_start_services()` needs compose file path; `_write_trunk_config()` env var names
- `docker/docker-compose.yml` — Add env var injection for FreeSWITCH container
- `config/freeswitch/sip_profiles/external.xml` — Update variable names to match CLI output

### Phase 3 context (original implementation)
- `.planning/phases/03-sms-agent-interface-cli/03-CONTEXT.md` — D-09 through D-12 (CLI decisions)
- `.planning/phases/03-sms-agent-interface-cli/03-04-PLAN.md` — Original CLI plan

</canonical_refs>

<code_context>
## Existing Code Insights

### Files to Modify
- `holler/cli/commands.py` — `_start_services()` at ~line 45, `_write_trunk_config()` at ~line 70
- `docker/docker-compose.yml` — FreeSWITCH service definition needs env var injection
- `config/freeswitch/sip_profiles/external.xml` — SIP trunk gateway variable names

### Established Patterns
- Click CLI with `@click.group()` and subcommands
- `.holler.env` as config persistence file (load_dotenv in config.py)
- FreeSWITCH reads vars from environment via `$${VAR_NAME}` syntax

### Integration Points
- `.holler.env` — written by CLI, read by Python config AND FreeSWITCH container
- `docker-compose.yml` — must bridge .holler.env into FreeSWITCH container environment

</code_context>

<specifics>
## Specific Ideas

- The fix should be minimal — these are wiring bugs, not new features
- After the fix, the four-command flow must work from any directory (not just project root)

</specifics>

<deferred>
## Deferred Ideas

None — this phase is tightly scoped to audit gap closure

</deferred>

---

*Phase: 04-cli-docker-onboarding-fixes*
*Context gathered: 2026-03-25*

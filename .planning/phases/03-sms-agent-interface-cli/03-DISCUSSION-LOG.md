# Phase 3: SMS + Agent Interface + CLI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-24
**Phase:** 03-sms-agent-interface-cli
**Areas discussed:** Tool protocol shape, SMPP integration approach, CLI framework and onboarding, Agent loop ownership
**Mode:** --auto (all selections made by Claude using recommended defaults)

---

## Tool Protocol Shape

| Option | Description | Selected |
|--------|-------------|----------|
| OpenAI function calling JSON Schema | Standard format, works with OpenAI/Ollama natively, Anthropic via adapter | ✓ |
| Custom JSON-RPC protocol | More flexible but requires every LLM to learn a new format | |
| MCP (Model Context Protocol) | Emerging standard but adds dependency, not yet universal | |

**User's choice:** [auto] OpenAI function calling JSON Schema (recommended default)
**Notes:** Existing LLMClient already uses AsyncOpenAI. Zero adapter code for OpenAI/Ollama. Anthropic tool_use maps cleanly.

### Sub-decisions

**Compliance block handling:**
| Option | Description | Selected |
|--------|-------------|----------|
| Structured error in tool result | LLM sees block reason, can inform human | ✓ |
| Raise exception to caller | Breaks agent loop, LLM never sees reason | |

**User's choice:** [auto] Structured error in tool result (recommended default)

**Tool definition location:**
| Option | Description | Selected |
|--------|-------------|----------|
| Python-defined with auto-generated JSON Schema | Single source of truth, type-safe | ✓ |
| Standalone JSON Schema files | Decoupled but duplicates type info | |

**User's choice:** [auto] Python-defined with auto-generated JSON Schema (recommended default)

**Transfer implementation:**
| Option | Description | Selected |
|--------|-------------|----------|
| Blind transfer via uuid_transfer | Simple, sufficient for v1 | ✓ |
| Attended transfer (consult + bridge) | Better UX but complex, v2 | |

**User's choice:** [auto] Blind transfer (recommended default)

---

## SMPP Integration Approach

| Option | Description | Selected |
|--------|-------------|----------|
| aiosmpplib (async-native) | Fits asyncio pattern, no executor wrapping needed | ✓ |
| smpplib (sync) | More battle-tested but requires run_in_executor | |
| Jasmin (full SMS broker) | Overkill for v1, adds RabbitMQ dependency | |

**User's choice:** [auto] aiosmpplib (recommended default)
**Notes:** Codebase is async throughout. Adding sync library would break pattern.

### Sub-decisions

**Connection model:**
| Option | Description | Selected |
|--------|-------------|----------|
| Persistent with auto-reconnect | Standard for SMPP, initialized at startup | ✓ |
| Connect per-message | High overhead, not how SMPP is designed | |

**User's choice:** [auto] Persistent with auto-reconnect (recommended default)

**SMS compliance path:**
| Option | Description | Selected |
|--------|-------------|----------|
| Through compliance gateway (shared) | TCPA applies to SMS, same structural guarantee | ✓ |
| Separate SMS compliance check | Duplicates logic, harder to audit | |
| No compliance for SMS | Non-compliant, liability risk | |

**User's choice:** [auto] Through compliance gateway (recommended default)

**Delivery receipt handling:**
| Option | Description | Selected |
|--------|-------------|----------|
| SMPP delivery receipt PDU callback | Native SMPP mechanism, status stored for agent query | ✓ |
| Polling SMSC for status | Wasteful, higher latency | |

**User's choice:** [auto] SMPP delivery receipt PDU callback (recommended default)

---

## CLI Framework and Onboarding

| Option | Description | Selected |
|--------|-------------|----------|
| Click | Mature, well-documented, minimal deps, @click.group() for subcommands | ✓ |
| Typer | Modern but adds pydantic dependency | |
| argparse | Already used in main.py but clunky for multi-command CLI | |

**User's choice:** [auto] Click (recommended default)
**Notes:** argparse exists in main.py but only for simple --call flag. Click is better for holler init/trunk/call subcommand pattern.

### Sub-decisions

**holler init behavior:**
| Option | Description | Selected |
|--------|-------------|----------|
| Download models + generate config + check system | Full onboarding experience | ✓ |
| Generate config only | Minimal but user must find/download models separately | |

**User's choice:** [auto] Download models + generate config + check system (recommended default)

**Config persistence:**
| Option | Description | Selected |
|--------|-------------|----------|
| .holler.env file with env override | File for persistence, env for override. Extends from_env() | ✓ |
| Environment variables only | No persistence between sessions | |
| YAML/TOML config file | Different paradigm from existing env-based config | |

**User's choice:** [auto] .holler.env file with env override (recommended default)

**Agent prompt specification:**
| Option | Description | Selected |
|--------|-------------|----------|
| --agent flag with default | Simple, discoverable. No flag = default assistant | ✓ |
| Separate prompt file (--prompt-file) | More flexible but extra step | |
| Interactive prompt entry | Breaks scriptability | |

**User's choice:** [auto] --agent flag with default (recommended default)

---

## Agent Loop Ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Built-in agent loop in Holler | Required for holler call to work. External use as library also supported | ✓ |
| External orchestrator only | Holler as pure library, no CLI agent loop possible | |
| Both with feature flag | Over-engineered for v1 | |

**User's choice:** [auto] Built-in agent loop (recommended default)
**Notes:** holler call must work end-to-end for four-command onboarding. Built-in loop is mandatory.

### Sub-decisions

**Multi-modal sessions:**
| Option | Description | Selected |
|--------|-------------|----------|
| Claude's discretion | Session object supports it conceptually. Details deferred | ✓ |
| Explicit cross-channel API | Scope creep for Phase 3 | |

**User's choice:** [auto] Claude's discretion (recommended default)

**Pipeline integration:**
| Option | Description | Selected |
|--------|-------------|----------|
| Extend VoicePipeline for tool-call interception | Transparent to voice pipeline, coordinator handles routing | ✓ |
| Separate agent coordinator alongside pipeline | Duplicates orchestration logic | |

**User's choice:** [auto] Extend VoicePipeline (recommended default)

**Multi-LLM tool format:**
| Option | Description | Selected |
|--------|-------------|----------|
| Adapter pattern, OpenAI as canonical | One format stored, adapters for providers | ✓ |
| Per-provider tool definitions | Maintenance burden, format drift | |

**User's choice:** [auto] Adapter pattern (recommended default)

---

## Claude's Discretion

- SMPP connection configuration details
- Exact JSON Schema structure for each tool definition
- Model download source URLs and caching strategy
- Docker Compose service startup/health check logic
- Delivery status store implementation
- Error handling and retry strategy for SMPP
- Click command help text and output formatting
- Agent loop iteration limits and timeout handling

## Deferred Ideas

- Attended transfer — v2
- WebRTC agent-to-agent mesh — v2
- Multi-modal session escalation (SMS → voice) — bonus, not requirement
- GSM modem support — deployment option, not core
- Webhook/event callbacks — v2

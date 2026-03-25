# Contributing to Holler

Thanks for your interest. Holler is Apache 2.0 — fork it, build on it, make it yours. See [LICENSE](LICENSE) for the full text.

The most valuable contributions right now are country modules. If you understand the telecom regulations in your jurisdiction, you can contribute something that nobody else can.

## Getting started

```bash
git clone https://github.com/holler-ai/holler && cd holler
pip install -e ".[dev]"
pytest
```

All tests should pass before you start. If they don't, open an issue.

<a name="country-modules"></a>
## Country modules

The core is jurisdiction-agnostic. Compliance lives in country modules — plugins that enforce local rules before any call goes out. Every outbound call passes through a compliance module for the destination's jurisdiction. If no module is registered for a prefix, the call is blocked.

### The contract

Every country module implements a single method:

```python
async def check_outbound(
    self,
    destination: str,
    session: TelecomSession,
) -> ComplianceResult:
    ...
```

- `destination`: E.164 destination number (e.g. `+61299123456`)
- `session`: the `TelecomSession` with DID, jurisdiction, consent state, etc.
- Returns `ComplianceResult(passed=True, ...)` to allow the call
- Returns `ComplianceResult(passed=False, reason="...", ...)` to deny it
- Never raises exceptions — catch everything and return a deny result
- Never blocks for more than 2 seconds (gateway timeout)

The gateway guarantees: if `check_outbound()` raises or times out, the call is blocked. Fail-closed, always.

### Step by step

**1. Start with the rules, not the code.**

Before writing a line of Python, write a markdown file that documents your country's telecom regulations. What consent is required? What hours can you call? Is there a national DNC list? Who enforces it? What are the penalties?

Understanding the rules is the hard part. The code is the easy part.

**2. Copy the template.**

```bash
cp -r holler/countries/_template holler/countries/au
```

Replace `au` with your [ISO 3166-1 alpha-2 country code](https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2).

**3. Rename the class.**

In `holler/countries/au/module.py`, rename `TemplateComplianceModule` to `AustraliaComplianceModule` (or whatever fits).

**4. Set your E.164 prefix.**

The registration prefix should be your country's calling code: `+61` for Australia, `+44` for the UK, `+1` for NANP (US + Canada share this — you'll need sub-prefix logic), etc.

**5. Implement `check_outbound()`.**

Replace the `template_not_implemented` placeholder with real checks. Typical checks:

- **Consent** — does the caller have prior express written consent from this number?
- **DNC** — is the destination on a national or state/provincial Do Not Call list?
- **Time-of-day** — is the current time within allowed calling hours for the recipient's timezone?
- **Caller ID / CLI** — does the caller have a valid CLI for this jurisdiction? Any STIR/SHAKEN equivalent?
- **Jurisdiction-specific** — OFCOM silent call rules (UK), ACMA registration (AU), CRTC rules (CA), etc.

**6. Look at the US implementation for reference.**

`holler/countries/us/module.py` implements TCPA compliance: DNC check, time-of-day (8am–9pm in recipient's timezone), and consent verification. It's a complete implementation you can pattern-match against.

**7. Register your module.**

In your application startup (or in `holler/main.py` for the CLI path):

```python
from holler.core.telecom.router import JurisdictionRouter
from holler.countries.au.module import AustraliaComplianceModule

router.register("+61", AustraliaComplianceModule())
```

**8. Test it.**

Write tests that cover: allowed call (all checks pass), DNC block, time-of-day block, consent block, and whatever jurisdiction-specific rules you've implemented.

**9. Submit a PR.**

Include your rules documentation alongside the code. The module is only useful if future contributors can understand why it does what it does.

## Code style

- Python 3.11+, type hints throughout
- `asyncio` for all I/O — no blocking calls in the hot path
- `structlog` for logging (not `logging` directly)
- `pytest` for tests — `pytest-asyncio` for async test cases
- No external services in tests — mock at the boundary

## Pull requests

1. Fork the repo and create a branch from `main`
2. Write tests for your changes
3. Run `pytest` — all tests must pass
4. Open a PR with a clear description of what you've added and why

For country modules, include a short summary of the jurisdiction's telecom rules in the PR description. Even a few bullet points helps reviewers who don't know your country's regulations.

Questions? Open an issue. We're friendly.

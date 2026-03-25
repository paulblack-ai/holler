# Quick Task: Audit and Fix Vendor Dependencies

**Researched:** 2026-03-25
**Domain:** Docker build pipeline, FreeSWITCH packaging, model downloads
**Confidence:** HIGH

## Summary

The "no vendor accounts" promise has two confirmed violations and one conditional concern.
The most critical is the SignalWire PAT requirement in the FreeSWITCH Dockerfile — it blocks
`holler init` for any user who hasn't pre-registered at id.signalwire.com. HuggingFace
anonymous downloads work but carry rate-limit risk under high load; they are not a hard
blocker for single-user installs. Docker Hub for `redis:7-alpine` is unauthenticated and
not a concern.

**Primary recommendation:** Replace the SignalWire Debian repo approach with a source-build
Dockerfile modelled on `PatrickBaus/freeswitch-docker` (Alpine, no token, v1.10.12 tracked,
actively maintained, ghcr.io hosted). The fix is a Dockerfile rewrite; no Python or config
changes are required.

---

## Findings

### Finding 1: SignalWire PAT in Dockerfile — CONFIRMED BLOCKER

**Location:** `docker/freeswitch/Dockerfile` lines 3–14 and `docker/docker-compose.yml` line 6.

**What it does:** The Dockerfile fetches the FreeSWITCH Debian package signing key and adds
an apt source using HTTP Basic Auth with `--http-user=signalwire --http-password=${SIGNALWIRE_TOKEN}`.
If `SIGNALWIRE_TOKEN` is unset or empty, `wget` returns HTTP 401, the `apt-key add` fails,
and the image build aborts with a non-zero exit code.

**What the user must do today:** Create a free account at `id.signalwire.com`, generate a PAT,
and export `SIGNALWIRE_TOKEN` before running `docker compose up --build`. This is an
undocumented prerequisite.

**Impact:** Directly contradicts the core value statement ("no vendor accounts") and the
README ("No dashboard. No account creation. No OAuth flow."). The `.env.example` even
acknowledges it with the comment `# SignalWire (required to build FreeSWITCH Docker image)`.

**Confidence:** HIGH — confirmed by direct code inspection.

---

### Finding 2: HuggingFace Anonymous Downloads — LOW RISK, NOT A BLOCKER

**Location:** `holler/cli/commands.py` `_download_models()`, lines 136–140.

**What it does:** `hf_hub_download("fastrtc/kokoro-onnx", ...)` and `WhisperModel("distil-large-v3", ...)`
both call the HuggingFace Hub without any authentication token. The `faster_whisper` import also
uses `huggingface_hub` internally.

**Rate-limit reality:** Anonymous users are allowed 3,000 resolver requests per 5-minute window
per IP address (confirmed from HF official docs, September 2025 figures). A single `holler init`
triggers 2–3 resolver calls total — well within the anonymous limit for any individual installation.

**Risk:** If multiple developers on the same office NAT IP run `holler init` simultaneously, or a
CI pipeline hammers it repeatedly, a 429 could occur. The `huggingface_hub` SDK (1.2.0+) auto-retries
on 429 by reading the `RateLimit` header, so the failure mode is a delay, not a hard error.

**The real issue:** `hf_hub_download` will succeed silently without a token for public repos. No
account is required for `fastrtc/kokoro-onnx` or Whisper models. This is not a "vendor account"
problem in the same category as the SignalWire PAT — it's a commodity CDN download.

**Recommendation:** No change required for v1.0 promise. Optionally document that setting
`HF_TOKEN` in the environment speeds up downloads and avoids rate-limit delays in CI scenarios.

**Confidence:** HIGH — confirmed from HuggingFace rate limits documentation.

---

### Finding 3: Docker Hub Rate Limits (redis:7-alpine) — NOT A CONCERN

`docker-compose.yml` pulls `redis:7-alpine` from Docker Hub. Docker Hub applies pull rate limits
to unauthenticated users (100 pulls/6 hours per IP) but not for public images from a logged-in
account. For a developer running `holler init` once, this is not a concern. No account required.

**Confidence:** HIGH.

---

### Finding 4: mod_audio_stream Build — NO EXTERNAL ACCOUNT NEEDED

`docker/freeswitch/Dockerfile` lines 34–41 clone `github.com/amigniter/mod_audio_stream` via
public HTTPS and build from source. This requires no token. This part of the Dockerfile is clean.

---

## Fix: Replace SignalWire Repo with Source Build

### Option A: Build from Source (Recommended)

`PatrickBaus/freeswitch-docker` (ghcr.io/patrickbaus/freeswitch-docker) is:
- Multi-stage Alpine build from public GitHub sources — zero vendor tokens
- Tracks FreeSWITCH v1.10.12 (current stable, same as Holler's target)
- Released v1.10.12-5 on January 29, 2026 — actively maintained with automated release tracking
- Excludes only `mod_av` and `mod_signalwire` — neither is required by Holler's call path
- Published on ghcr.io (no Docker Hub pull rate limit concerns)

**Two implementation paths:**

**Path A1 — Use the pre-built image directly**

In `docker-compose.yml`, replace the `build:` block with:
```yaml
freeswitch:
  image: ghcr.io/patrickbaus/freeswitch-docker:latest
```

Eliminates the build entirely. User never needs to build FreeSWITCH. Fastest fix.

Risk: Trusting a third-party image maintainer. The maintainer is an individual (PatrickBaus),
not a corporate entity. Image is on ghcr.io with automated release tracking.

**Path A2 — Copy the Dockerfile into the repo**

Vendor the PatrickBaus Dockerfile (Apache 2.0 / MIT compatible) into `docker/freeswitch/Dockerfile`,
replacing the current SignalWire-repo approach. Holler controls the image build; no external image
trust required. `mod_audio_stream` still built as a separate layer on top.

The PatrickBaus Dockerfile uses multi-stage Alpine: deps -> builder-sofia -> builder-freeswitch -> runner.
Build time is ~15–25 minutes on a modern machine (full source compile). This is a one-time cost on
first `docker compose build`.

Risk: Long initial build time surprises users expecting a fast `holler init`. Mitigation: publish
a pre-built image to ghcr.io/holler-ai/freeswitch alongside the source Dockerfile.

### Option B: Build from Source (DIY, without vendoring PatrickBaus)

Adapt the signalwire/freeswitch `scripts/packaging/build` scripts or the master Dockerfile
to compile from source on Debian Bookworm. The signalwire/freeswitch repo is public and
cloneable without credentials; only the Debian package _repo_ requires a token, not the source code.

Dependencies to build manually: libks, spandsp, sofia-sip, then FreeSWITCH itself.
Build time: ~20–30 minutes on Debian. More complex to maintain than the PatrickBaus approach.

**Confidence on all options:** HIGH — each confirmed by direct Dockerfile inspection.

---

## Recommended Fix (Ranked)

| Rank | Approach | Build Time | Trust | Complexity |
|------|----------|------------|-------|------------|
| 1 | Path A2: vendor PatrickBaus Dockerfile + publish holler image to ghcr.io | ~20min first build, 0s after | Self-controlled | Medium |
| 2 | Path A1: reference ghcr.io/patrickbaus/freeswitch-docker directly | 0s | Third-party maintainer | Low |
| 3 | Option B: DIY source build from signalwire/freeswitch | ~25min first build | Self-controlled | High |

**Recommended:** Path A2. Gives users `docker compose build` that works with zero tokens, while
keeping the image build under the project's control. Publish the result to ghcr.io/holler-ai/freeswitch
so repeat installs and CI skip the build entirely. The PatrickBaus Dockerfile is well-structured
(multi-stage, non-root runtime user, healthcheck-compatible) and is the right starting point.

---

## .env.example Fix

The `.env.example` currently has:
```
# SignalWire (required to build FreeSWITCH Docker image)
SIGNALWIRE_TOKEN=your_signalwire_pat
```

After the Dockerfile fix, this entry must be removed entirely. It should not appear in any
generated config or documentation.

---

## Files to Change

| File | Change |
|------|--------|
| `docker/freeswitch/Dockerfile` | Replace SignalWire-repo approach with source build |
| `docker/docker-compose.yml` | Remove `SIGNALWIRE_TOKEN` build arg |
| `.env.example` | Remove `SIGNALWIRE_TOKEN` entry |
| `README.md` | Remove any mention of SignalWire PAT from prerequisites |
| `holler/cli/commands.py` | No changes required |

---

## Sources

- `docker/freeswitch/Dockerfile` — direct inspection (HIGH)
- `docker/docker-compose.yml` — direct inspection (HIGH)
- `.env.example` — direct inspection (HIGH)
- [PatrickBaus/freeswitch-docker](https://github.com/PatrickBaus/freeswitch-docker) — Dockerfile and README verified (HIGH)
- [HuggingFace Hub Rate Limits](https://huggingface.co/docs/hub/rate-limits) — official documentation, September 2025 data (HIGH)
- [signalwire/freeswitch docker/release/Dockerfile](https://github.com/signalwire/freeswitch/blob/master/docker/release/Dockerfile) — verified as Jessie/1.6 era, not usable (HIGH)
- [signalwire/freeswitch docker/master/Dockerfile](https://github.com/signalwire/freeswitch/blob/master/docker/master/Dockerfile) — verified requires TOKEN (HIGH)

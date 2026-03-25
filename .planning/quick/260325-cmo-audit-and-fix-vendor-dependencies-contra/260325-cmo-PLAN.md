---
phase: quick
plan: 260325-cmo
type: execute
wave: 1
depends_on: []
files_modified:
  - docker/freeswitch/Dockerfile
  - docker/docker-compose.yml
  - .env.example
autonomous: true
requirements: []
must_haves:
  truths:
    - "docker compose build succeeds with zero environment variables set"
    - "No file in the repo references SIGNALWIRE_TOKEN as a required variable"
    - "FreeSWITCH container starts and responds to fs_cli status after build"
    - "mod_audio_stream is built and loadable in the final image"
  artifacts:
    - path: "docker/freeswitch/Dockerfile"
      provides: "Source-build FreeSWITCH without vendor tokens"
      contains: "signalwire/freeswitch"
    - path: "docker/docker-compose.yml"
      provides: "Compose config without SIGNALWIRE_TOKEN"
    - path: ".env.example"
      provides: "Example env without SignalWire section"
  key_links:
    - from: "docker/docker-compose.yml"
      to: "docker/freeswitch/Dockerfile"
      via: "build context"
      pattern: "build:.*context:.*freeswitch"
---

<objective>
Remove the SignalWire PAT requirement from the FreeSWITCH Docker build so that `holler init` and `docker compose build` work with zero vendor accounts.

Purpose: The core value statement is "no vendor accounts, no API keys, no human in the loop." The current Dockerfile requires a free SignalWire PAT from id.signalwire.com to download FreeSWITCH Debian packages. This contradicts the promise and blocks any user who hasn't pre-registered. The fix is to build FreeSWITCH from source (the source code on GitHub is public and requires no authentication) instead of pulling from the authenticated Debian package repo.

Output: A Dockerfile that compiles FreeSWITCH v1.10.12 from source on Alpine Linux using a multi-stage build, with mod_audio_stream built on top. No tokens, no vendor accounts, no authentication of any kind.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@docker/freeswitch/Dockerfile
@docker/docker-compose.yml
@.env.example
@.planning/quick/260325-cmo-audit-and-fix-vendor-dependencies-contra/260325-cmo-RESEARCH.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Rewrite Dockerfile to build FreeSWITCH from source</name>
  <files>docker/freeswitch/Dockerfile</files>
  <action>
Replace the entire Dockerfile with a multi-stage Alpine-based source build. The approach builds FreeSWITCH v1.10.12 from the public signalwire/freeswitch GitHub repo (no token needed -- only the Debian *package repo* requires auth, not the source code).

IMPORTANT LICENSE NOTE: PatrickBaus/freeswitch-docker is GPL v3. Do NOT copy that Dockerfile. Write a fresh one inspired by the same general approach (Alpine multi-stage source build). FreeSWITCH itself is MPL 1.1 which is compatible with Apache 2.0 distribution.

Stage structure:

**Stage 1: `deps` (FROM alpine:3.21)**
- Install git
- Shallow-clone signalwire/freeswitch at tag v1.10.12 from https://github.com/signalwire/freeswitch.git (depth 1, single-branch)
- Shallow-clone freeswitch/sofia-sip at tag v1.13.17 from https://github.com/freeswitch/sofia-sip.git (depth 1, single-branch)
- Remove .git directories to save space

**Stage 2: `builder-sofia` (FROM alpine:3.21)**
- COPY --from=deps the sofia-sip source
- Install build deps: build-base autoconf automake libtool openssl-dev glib-dev
- Run: ./bootstrap.sh && ./configure --prefix=/usr --enable-static=no && make -j$(nproc) && make install DESTDIR=/build

**Stage 3: `builder-freeswitch` (FROM alpine:3.21)**
- COPY --from=deps the freeswitch source
- COPY --from=builder-sofia /build/ /
- Install build deps: build-base autoconf automake libtool openssl-dev libjpeg-turbo-dev sqlite-dev curl-dev pcre-dev speex-dev speexdsp-dev libedit-dev libsndfile-dev opus-dev lua5.3-dev tiff-dev libks-dev spandsp3-dev ldns-dev
- Run bootstrap.sh, then configure with --enable-fhs and a modules.conf that enables ONLY the modules Holler needs:
  - mod_commands, mod_console, mod_dptools, mod_event_socket, mod_sofia, mod_dialplan_xml, mod_loopback, mod_sndfile, mod_native_file, mod_tone_stream, mod_logfile
  - Disable mod_signalwire and mod_av explicitly (not needed, avoids extra deps)
- Build: make -j$(nproc) && make install DESTDIR=/build
- The modules.conf approach: Before running configure, edit modules.conf in the source tree to comment out everything except the needed modules. This controls which modules get built.

**Stage 4: `builder-mod-audio-stream` (FROM alpine:3.21)**
- COPY --from=builder-freeswitch /build/ /
- Install: build-base cmake git libwebsockets-dev pkgconf
- Clone https://github.com/amigniter/mod_audio_stream.git
- Build with cmake: mkdir build && cd build && cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)
- Copy the .so to /build/usr/lib/freeswitch/mod/

**Stage 5: `runner` (FROM alpine:3.21)**
- Install ONLY runtime deps: libstdc++ openssl libjpeg-turbo sqlite-libs libcurl pcre speex speexdsp libedit libsndfile opus lua5.3-libs tiff libks spandsp3 ldns libwebsockets
- COPY --from=builder-freeswitch /build/ /
- COPY --from=builder-mod-audio-stream the mod_audio_stream.so into /usr/lib/freeswitch/mod/
- Create freeswitch user (uid 499, gid 499)
- Create /etc/freeswitch and /var/log/freeswitch directories
- HEALTHCHECK same as current: fs_cli -x "status" | grep -q "UP"
- CMD ["freeswitch", "-nonat", "-c"]

Key points:
- No ARG for any token or credential
- No wget to any authenticated endpoint
- Everything cloned from public GitHub repos via HTTPS
- Use shallow clones (--depth 1) to minimize download size
- Multi-stage build keeps final image small (only runtime libs)
- First build will take ~15-25 minutes (source compilation). This is expected and acceptable -- it is a one-time cost.

If a specific Alpine package (like spandsp3-dev or libks-dev) is not available in Alpine repos, the build stage should compile that dependency from source too (e.g., clone https://github.com/signalwire/libks.git and build it). Check Alpine 3.21 package availability. Common fallbacks:
- libks: May need source build from https://github.com/signalwire/libks.git
- spandsp3: May need source build from https://github.com/freeswitch/spandsp.git

Add a comment at the top of the Dockerfile:
```
# FreeSWITCH v1.10.12 — built from source, zero vendor accounts required.
# Source: https://github.com/signalwire/freeswitch (public, no auth)
# Build time: ~15-25 min on first run (cached after that)
```
  </action>
  <verify>
    <automated>cd /Users/paul/paul/Projects/holler && grep -c "SIGNALWIRE" docker/freeswitch/Dockerfile | grep -q "^0$" && grep -q "signalwire/freeswitch" docker/freeswitch/Dockerfile && echo "PASS: No SignalWire token refs, source build present"</automated>
  </verify>
  <done>Dockerfile builds FreeSWITCH from public source with zero authentication. No SIGNALWIRE_TOKEN ARG. Multi-stage Alpine build. All modules from current Dockerfile are included. mod_audio_stream built from amigniter source.</done>
</task>

<task type="auto">
  <name>Task 2: Remove SIGNALWIRE_TOKEN from compose and env files</name>
  <files>docker/docker-compose.yml, .env.example</files>
  <action>
**docker/docker-compose.yml:**
Remove the `args:` block under `freeswitch.build` entirely. The build context stays the same but no build args are passed. The result should be:

```yaml
  freeswitch:
    build:
      context: ./freeswitch
    network_mode: "host"
    environment:
      - HOLLER_TRUNK_HOST=${HOLLER_TRUNK_HOST:-}
      - HOLLER_TRUNK_USER=${HOLLER_TRUNK_USER:-}
      - HOLLER_TRUNK_PASS=${HOLLER_TRUNK_PASS:-}
    volumes:
      - ../config/freeswitch:/etc/freeswitch
      - freeswitch-logs:/var/log/freeswitch
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "fs_cli", "-x", "status"]
      interval: 10s
      timeout: 5s
      retries: 3
```

Everything else in docker-compose.yml stays unchanged.

**.env.example:**
Remove these two lines entirely:
```
# SignalWire (required to build FreeSWITCH Docker image)
SIGNALWIRE_TOKEN=your_signalwire_pat
```

Leave the blank line before "# Voice Pipeline" section to maintain readability. The result should flow from LLM_MODEL to WHISPER_MODEL with a blank line separator.
  </action>
  <verify>
    <automated>cd /Users/paul/paul/Projects/holler && ! grep -q "SIGNALWIRE" docker/docker-compose.yml && ! grep -q "SIGNALWIRE" .env.example && echo "PASS: No SignalWire refs in compose or env"</automated>
  </verify>
  <done>SIGNALWIRE_TOKEN removed from docker-compose.yml build args and .env.example. No file in the repo requires a SignalWire account.</done>
</task>

</tasks>

<verification>
1. `grep -r "SIGNALWIRE_TOKEN" docker/ .env.example` returns zero matches
2. `grep -r "signalwire.com" docker/` returns zero matches (no references to the authenticated package repo)
3. Dockerfile contains `signalwire/freeswitch` (the public GitHub repo URL) but NOT `freeswitch.signalwire.com` (the authenticated package repo)
4. `docker compose config` in docker/ directory parses without errors and shows no SIGNALWIRE_TOKEN
</verification>

<success_criteria>
- Zero references to SIGNALWIRE_TOKEN in docker/, .env.example
- Dockerfile builds FreeSWITCH from public GitHub source (no authentication)
- All FreeSWITCH modules from the original Dockerfile are present in the new build
- mod_audio_stream still built from amigniter source
- docker-compose.yml parses cleanly with no build args
- .env.example has no SignalWire section
</success_criteria>

<output>
After completion, create `.planning/quick/260325-cmo-audit-and-fix-vendor-dependencies-contra/260325-cmo-SUMMARY.md`
</output>

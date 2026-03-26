# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## holler-init-blocking — Missing freeswitch.xml entry-point config + Genesis ESL API mismatch
- **Date:** 2026-03-25
- **Error patterns:** freeswitch.xml, switch_xml.c, Couldn't open, No such file or directory, AttributeError, connect, Inbound, esl.py, ESL, crash-loop, docker-compose
- **Root cause:** (1) config/freeswitch/freeswitch.xml was never created — FreeSWITCH compiled with --sysconfdir=/etc --enable-fhs requires it as its top-level config entry point and crash-loops without it. (2) Genesis Inbound API is .start()/.stop(), not .connect()/.close() — esl.py called the non-existent .connect() method causing AttributeError at runtime.
- **Fix:** (1) Created config/freeswitch/freeswitch.xml with standard X-PRE-PROCESS includes for vars.xml, autoload_configs/, and dialplan/. (2) In holler/core/freeswitch/esl.py replaced self._client.connect() with self._client.start() and self._client.close() with self._client.stop().
- **Files changed:** config/freeswitch/freeswitch.xml, holler/core/freeswitch/esl.py
---

## esl-status-parsing — FreeSwitchESL.connect() body extraction and retry backoff
- **Date:** 2026-03-26
- **Error patterns:** RuntimeError, FreeSWITCH not ready, api/response, Content-Type, Content-Length, status.body, None, UP, headers dict, initializing, connect
- **Root cause:** Two issues: (1) status.body (ESLEvent.body) is None during FreeSWITCH startup because process_body has not yet been called; a prior code version used str(status) (the full UserDict) in the error f-string, producing a confusing headers-dict output in the RuntimeError message. (2) No retry logic meant the first connection attempt during FS startup always failed immediately instead of waiting for FS to finish loading modules.
- **Fix:** (1) Guard body extraction with isinstance(status.body, str) so None never causes ambiguous falsy behaviour; fall back to repr(dict(status)) in error diagnostics. (2) Added retry loop in connect() — 5 retries with 2s delay — so transient startup "not UP yet" states are handled automatically. Also uses start()/stop() consistently per the Genesis API.
- **Files changed:** holler/core/freeswitch/esl.py
---


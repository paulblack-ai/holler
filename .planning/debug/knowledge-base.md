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


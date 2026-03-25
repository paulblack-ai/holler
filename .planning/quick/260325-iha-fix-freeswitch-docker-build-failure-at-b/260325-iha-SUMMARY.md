---
one_liner: "Fix FreeSWITCH Docker source build — six fixes for Alpine/ARM64 compatibility"
---

# Quick Task 260325-iha: Fix FreeSWITCH Docker Build

## What Changed

The FreeSWITCH Dockerfile (multi-stage Alpine source build from the vendor dependency audit) failed at multiple points. Six fixes applied iteratively:

1. **spandsp bootstrap.sh** — `autogen.sh` calls `whereis` (missing on Alpine) and has broken `libtoolize` version parsing. Fixed: replaced `./bootstrap.sh` with `autoreconf -fi`.

2. **Alpine 3.21 → 3.20** — GCC 14 on Alpine 3.21 treats `-Wincompatible-pointer-types` as error. sofia-sip v1.13.17 and FreeSWITCH v1.10.12 have many instances. Fixed: downgraded to Alpine 3.20 (GCC 13).

3. **libvpx build failure** — configure detects libvpx and tries to build it even though mod_av is not in modules.conf. Fixed: added `--disable-libvpx` to configure.

4. **/var/run symlink conflict** — Alpine symlinks `/var/run` → `/run`. FreeSWITCH's `make install DESTDIR=/build` creates `/build/var/run/` as a directory. COPY into runner fails. Fixed: `rm -rf /build/var/run` after install.

5. **mod_audio_stream deps** — Missing `speexdsp-dev`, `libevent-dev`, `zlib-dev` in builder stage. Missing `--recurse-submodules` for `libs/libwsc` submodule. All added.

6. **Runtime shared libraries** — Runner stage was missing sofia-sip, spandsp, and libks .so files. Fixed: added COPY from each builder stage into runner.

## Verification

```
$ docker run --rm docker-freeswitch freeswitch -version
FreeSWITCH version: 1.10.12-release~64bit ( 64bit)
```

- Platform: macOS/ARM64 (Apple Silicon)
- Image size: 1.19GB (includes English sounds + MOH)
- All 10 modules + mod_audio_stream present
- Zero vendor accounts required

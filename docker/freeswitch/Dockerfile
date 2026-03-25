# FreeSWITCH v1.10.12 — built from source, zero vendor accounts required.
# Source: https://github.com/signalwire/freeswitch (public, no auth)
# Build time: ~15-25 min on first run (cached after that)

# -------------------------------------------------------------------
# Stage 1: deps — shallow-clone all sources
# -------------------------------------------------------------------
FROM alpine:3.20 AS deps

RUN apk add --no-cache git

# FreeSWITCH v1.10.12
RUN git clone --depth 1 --branch v1.10.12 --single-branch \
    https://github.com/signalwire/freeswitch.git /src/freeswitch && \
    rm -rf /src/freeswitch/.git

# sofia-sip v1.13.17 (FreeSWITCH bundled version is out of date; use upstream)
RUN git clone --depth 1 --branch v1.13.17 --single-branch \
    https://github.com/freeswitch/sofia-sip.git /src/sofia-sip && \
    rm -rf /src/sofia-sip/.git

# spandsp (FreeSWITCH fork — no versioned releases, use HEAD)
RUN git clone --depth 1 --single-branch \
    https://github.com/freeswitch/spandsp.git /src/spandsp && \
    rm -rf /src/spandsp/.git

# libks (SignalWire — public source, no token needed)
RUN git clone --depth 1 --single-branch \
    https://github.com/signalwire/libks.git /src/libks && \
    rm -rf /src/libks/.git


# -------------------------------------------------------------------
# Stage 2: builder-sofia — build sofia-sip
# -------------------------------------------------------------------
FROM alpine:3.20 AS builder-sofia

RUN apk add --no-cache \
    build-base autoconf automake libtool \
    openssl-dev glib-dev

COPY --from=deps /src/sofia-sip /src/sofia-sip
WORKDIR /src/sofia-sip

RUN ./bootstrap.sh && \
    ./configure --prefix=/usr --enable-static=no && \
    make -j$(nproc) && \
    make install DESTDIR=/build


# -------------------------------------------------------------------
# Stage 3: builder-libks — build libks (needed by FreeSWITCH)
# -------------------------------------------------------------------
FROM alpine:3.20 AS builder-libks

RUN apk add --no-cache \
    build-base cmake openssl-dev util-linux-dev

COPY --from=deps /src/libks /src/libks
WORKDIR /src/libks

RUN cmake . -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr && \
    make -j$(nproc) && \
    make install DESTDIR=/build


# -------------------------------------------------------------------
# Stage 4: builder-spandsp — build spandsp (DSP for fax/tone)
# -------------------------------------------------------------------
FROM alpine:3.20 AS builder-spandsp

RUN apk add --no-cache \
    build-base autoconf automake libtool \
    tiff-dev libsndfile-dev

COPY --from=deps /src/spandsp /src/spandsp
WORKDIR /src/spandsp

# spandsp's autogen.sh has broken libtoolize version parsing on Alpine.
# Use autoreconf directly — does the same thing without the buggy checks.
RUN autoreconf -fi && \
    ./configure --prefix=/usr --enable-static=no && \
    make -j$(nproc) && \
    make install DESTDIR=/build


# -------------------------------------------------------------------
# Stage 5: builder-freeswitch — compile FreeSWITCH from source
# -------------------------------------------------------------------
FROM alpine:3.20 AS builder-freeswitch

# Build deps
RUN apk add --no-cache \
    build-base autoconf automake libtool pkgconf \
    openssl-dev libjpeg-turbo-dev sqlite-dev curl-dev \
    pcre-dev speex-dev speexdsp-dev libedit-dev \
    libsndfile-dev opus-dev lua5.3-dev tiff-dev ldns-dev \
    libwebsockets-dev glib-dev util-linux-dev

# Install sofia-sip, libks, spandsp from prior stages
COPY --from=builder-sofia /build/ /
COPY --from=builder-libks /build/ /
COPY --from=builder-spandsp /build/ /

# Update ldconfig so linker can find installed libs
RUN ldconfig /usr/lib || true

COPY --from=deps /src/freeswitch /src/freeswitch
WORKDIR /src/freeswitch

# Bootstrap
RUN ./bootstrap.sh -j

# Trim modules.conf to only what Holler needs.
# This controls which modules get compiled — anything commented out is skipped.
RUN mv modules.conf modules.conf.orig && \
    printf '%s\n' \
        'applications/mod_commands' \
        'applications/mod_dptools' \
        'applications/mod_loopback' \
        'applications/mod_tone_stream' \
        'dialplans/mod_dialplan_xml' \
        'endpoints/mod_loopback' \
        'endpoints/mod_sofia' \
        'formats/mod_native_file' \
        'formats/mod_sndfile' \
        'loggers/mod_console' \
        'loggers/mod_logfile' \
        'xml_int/mod_xml_cdr' \
        'event_handlers/mod_event_socket' \
    > modules.conf

# Configure — disable libvpx (mod_av not in modules.conf but configure
# still tries to build its libs). --enable-fhs for standard paths.
RUN ./configure \
        --prefix=/usr \
        --sysconfdir=/etc/freeswitch \
        --localstatedir=/var \
        --enable-fhs \
        --disable-libvpx

# Build and install
RUN make -j$(nproc) && make install DESTDIR=/build

# Sounds and MOH are optional — create target dir first
RUN mkdir -p /build/usr/share/freeswitch/sounds && \
    (make cd-moh-install DESTDIR=/build || true) && \
    (make cd-sounds-install DESTDIR=/build || true)

# Alpine symlinks /var/run -> /run. Remove /var/run from DESTDIR
# to avoid COPY conflict with the runner stage's symlink.
RUN rm -rf /build/var/run


# -------------------------------------------------------------------
# Stage 6: builder-mod-audio-stream — build mod_audio_stream on top
# -------------------------------------------------------------------
FROM alpine:3.20 AS builder-mod-audio-stream

RUN apk add --no-cache \
    build-base cmake git pkgconf \
    libwebsockets-dev openssl-dev speexdsp-dev libevent-dev zlib-dev

# We need FreeSWITCH headers for mod compilation
COPY --from=builder-freeswitch /build/ /
COPY --from=builder-spandsp /build/ /
COPY --from=builder-sofia /build/ /
COPY --from=builder-libks /build/ /

RUN git clone --depth 1 --recurse-submodules \
    https://github.com/amigniter/mod_audio_stream.git /src/mod_audio_stream

WORKDIR /src/mod_audio_stream
RUN mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) && \
    mkdir -p /build/usr/lib/freeswitch/mod && \
    cp mod_audio_stream.so /build/usr/lib/freeswitch/mod/


# -------------------------------------------------------------------
# Stage 7: runner — minimal runtime image
# -------------------------------------------------------------------
FROM alpine:3.20 AS runner

# Runtime dependencies only
RUN apk add --no-cache \
    libstdc++ openssl libjpeg-turbo sqlite-libs libcurl \
    pcre speex speexdsp libedit libsndfile opus lua5.3-libs \
    tiff ldns libwebsockets glib util-linux \
    ncurses-libs readline

# Install FreeSWITCH binaries and modules
COPY --from=builder-freeswitch /build/ /

# Install sofia-sip, spandsp, libks shared libraries (not in FreeSWITCH DESTDIR)
COPY --from=builder-sofia /build/usr/lib/ /usr/lib/
COPY --from=builder-spandsp /build/usr/lib/ /usr/lib/
COPY --from=builder-libks /build/usr/lib/ /usr/lib/

# Install mod_audio_stream
COPY --from=builder-mod-audio-stream /build/usr/lib/freeswitch/mod/mod_audio_stream.so \
    /usr/lib/freeswitch/mod/mod_audio_stream.so

# Create non-root user for FreeSWITCH (uid/gid 499)
RUN addgroup -g 499 -S freeswitch && \
    adduser -u 499 -S -G freeswitch -H -D freeswitch

# Runtime directories
RUN mkdir -p /etc/freeswitch /var/log/freeswitch /var/run/freeswitch && \
    chown -R freeswitch:freeswitch \
        /etc/freeswitch /var/log/freeswitch /var/run/freeswitch \
        /usr/lib/freeswitch /usr/share/freeswitch

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD fs_cli -x "status" | grep -q "UP" || exit 1

CMD ["freeswitch", "-nonat", "-c"]

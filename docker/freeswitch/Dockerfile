FROM debian:12-slim

ARG SIGNALWIRE_TOKEN

# Install FreeSWITCH from SignalWire repo (requires free PAT from id.signalwire.com)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates curl && \
    wget --http-user=signalwire --http-password=${SIGNALWIRE_TOKEN} \
    -O /usr/share/keyrings/signalwire-freeswitch-repo.gpg \
    https://freeswitch.signalwire.com/repo/deb/debian-release/bookworm/public.gpg && \
    echo "machine freeswitch.signalwire.com login signalwire password ${SIGNALWIRE_TOKEN}" > /etc/apt/auth.conf && \
    echo "deb [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] \
    https://freeswitch.signalwire.com/repo/deb/debian-release/bookworm/ bookworm main" \
    > /etc/apt/sources.list.d/freeswitch.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    freeswitch \
    freeswitch-mod-commands \
    freeswitch-mod-console \
    freeswitch-mod-dptools \
    freeswitch-mod-event-socket \
    freeswitch-mod-sofia \
    freeswitch-mod-dialplan-xml \
    freeswitch-mod-loopback \
    freeswitch-mod-sndfile \
    freeswitch-mod-native-file \
    freeswitch-mod-tone-stream \
    freeswitch-mod-logfile \
    && rm -rf /var/lib/apt/lists/*

# Build mod_audio_stream from source (open-source fork: amigniter)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential pkg-config \
    libfreeswitch-dev libwebsockets-dev && \
    git clone https://github.com/amigniter/mod_audio_stream.git /tmp/mod_audio_stream && \
    cd /tmp/mod_audio_stream && mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc) && \
    cp mod_audio_stream.so /usr/lib/freeswitch/mod/ && \
    rm -rf /tmp/mod_audio_stream && \
    apt-get purge -y git cmake build-essential && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD fs_cli -x "status" | grep -q "UP" || exit 1

CMD ["freeswitch", "-nonat", "-c"]

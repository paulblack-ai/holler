#!/bin/zsh
# Holler health check — run from project root

echo "=== Holler Status ==="
echo ""

# Docker services
echo "-- Docker --"
docker ps --filter "name=docker-freeswitch" --filter "name=docker-redis" --format "  {{.Names}}: {{.Status}}" 2>/dev/null || echo "  Docker not running"
echo ""

# ESL port
echo "-- FreeSWITCH ESL --"
(echo > /dev/tcp/127.0.0.1/18021) 2>/dev/null && echo "  Port 18021: OPEN" || \
(echo > /dev/tcp/127.0.0.1/8021) 2>/dev/null && echo "  Port 8021: OPEN" || echo "  Port 8021/18021: CLOSED"
echo ""

# Redis
echo "-- Redis --"
redis-cli ping 2>/dev/null | grep -q PONG && echo "  Redis: PONG" || echo "  Redis: not responding"
echo ""

# Ollama
echo "-- Ollama --"
curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "llama" && echo "  Ollama: running (llama3.2 available)" || echo "  Ollama: not running or no models"
echo ""

# Trunk config
echo "-- SIP Trunk --"
if [ -f .holler.env ]; then
    host=$(grep HOLLER_TRUNK_HOST .holler.env | cut -d= -f2)
    user=$(grep HOLLER_TRUNK_USER .holler.env | cut -d= -f2)
    if [ -n "$host" ] && [ -n "$user" ]; then
        echo "  Configured: ${user}@${host}"
    else
        echo "  Not configured (run: holler trunk)"
    fi
else
    echo "  No .holler.env found (run: holler init)"
fi
echo ""

# Venv
echo "-- Python --"
if [ -n "$VIRTUAL_ENV" ]; then
    echo "  Venv: active ($VIRTUAL_ENV)"
else
    echo "  Venv: NOT active (run: source .venv/bin/activate)"
fi
which holler >/dev/null 2>&1 && echo "  CLI: installed" || echo "  CLI: not found"
echo ""

# Models
echo "-- Voice Models --"
python3 -c "from huggingface_hub import try_to_load_from_cache; print('  Whisper: cached' if try_to_load_from_cache('Systran/faster-whisper-distil-large-v3', 'model.bin') else '  Whisper: not downloaded')" 2>/dev/null || echo "  Whisper: unknown"
ls ~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots/*/kokoro-v1.0.onnx >/dev/null 2>&1 && echo "  Kokoro: cached" || echo "  Kokoro: not downloaded"
echo ""
echo "=== Done ==="

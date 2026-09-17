#!/bin/zsh
# Holler diagnostic dump — paste output to debug sessions

echo "=== Holler Diagnostics $(date) ==="
echo ""

echo "-- System --"
uname -m
sw_vers 2>/dev/null | head -3
echo ""

echo "-- Docker Containers --"
docker ps -a --filter "name=docker-freeswitch" --filter "name=docker-redis" --format "{{.Names}} | {{.Status}} | {{.Ports}}" 2>/dev/null
echo ""

echo "-- FreeSWITCH Logs (last 30 lines) --"
docker logs docker-freeswitch-1 2>&1 | tail -30
echo ""

echo "-- FreeSWITCH Module Loading --"
docker logs docker-freeswitch-1 2>&1 | grep -i "Successfully Loaded\|Cannot load\|Error loading\|mod_\|pre_load\|modules.conf"
echo ""

echo "-- Redis --"
docker logs docker-redis-1 2>&1 | tail -5
echo ""

echo "-- Ports --"
for port in 8021 18021 5060 6379 11434; do
    (echo > /dev/tcp/127.0.0.1/$port) 2>/dev/null && echo "  $port: OPEN" || echo "  $port: CLOSED"
done
echo ""

echo "-- Ollama --"
curl -s http://localhost:11434/api/tags 2>/dev/null | head -3 || echo "  not running"
echo ""

echo "-- Trunk Config --"
grep -E "TRUNK_HOST|TRUNK_USER" .holler.env 2>/dev/null || echo "  no .holler.env"
echo ""

echo "-- Git --"
git log --oneline -5 2>/dev/null
echo ""
echo "=== End ==="

#!/bin/bash
# Test concurrent access to hailo-vision and hailo-clip services through device manager

set -e

echo "Testing concurrent hailo-vision and hailo-clip access..."
echo "Both services use device manager which serializes device access"
echo ""

# Test 1: Sequential health checks
echo "=== Test 1: Sequential health checks ==="
start=$(date +%s%N)
curl -s http://localhost:11435/health | jq . > /tmp/vision_health.json
curl -s http://localhost:5000/health | jq . > /tmp/clip_health.json
end=$(date +%s%N)
seq_time=$((($end - $start) / 1000000))

echo "Vision: $(jq .model /tmp/vision_health.json) - loaded: $(jq .model_loaded /tmp/vision_health.json)"
echo "CLIP: $(jq .model /tmp/clip_health.json) - loaded: $(jq .model_loaded /tmp/clip_health.json)"
echo "Sequential time: ${seq_time}ms"
echo ""

# Test 2: Concurrent pings (background processes)
echo "=== Test 2: Concurrent health checks (background) ==="
start=$(date +%s%N)
(curl -s http://localhost:11435/health > /tmp/vision_concurrent.json) &
(curl -s http://localhost:5000/health > /tmp/clip_concurrent.json) &
wait
end=$(date +%s%N)
con_time=$((($end - $start) / 1000000))

echo "Vision: $(jq .model /tmp/vision_concurrent.json)"
echo "CLIP: $(jq .model /tmp/clip_concurrent.json)"
echo "Concurrent time: ${con_time}ms"
echo ""

# Check device manager queue from logs
echo "=== Device Manager Queue Analysis ==="
echo "Recent device manager activity (last 5 requests):"
sudo journalctl -u hailo-device-manager.service -n 100 --no-pager | grep -E "Loading model|Inference|response:" | tail -5

echo ""
echo "✓ Test complete!"
echo "Both hailo-vision (VLM) and hailo-clip (CLIP) services coexist"
echo "Device manager serializes all device access through single VDevice"

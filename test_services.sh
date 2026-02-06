#!/bin/bash

# Script to test Hailo services: clip, vision, whisper, ocr
# Repeats the sequence 3 times
# Reports times between steps

set -e

# File paths
DOG_IMG="$HOME/raspberry_pi_hailo_ai_services/dog.png"
AUDIO_FILE="$HOME/raspberry_pi_hailo_ai_services/audio2.wav"
CARD_IMG="$HOME/raspberry_pi_hailo_ai_services/card.png"

# Function to get base64 of image
get_base64() {
    base64 -w0 < "$1"
}

# Function to time and call
call_and_time() {
    local start=$1
    local label=$2
    shift 2
    "$@" > /dev/null 2>&1  # Suppress output, only time
    local end=$(date +%s.%N)
    local elapsed=$(echo "$end - $start" | bc)
    echo "Time for $label: ${elapsed}s"
    echo "$end"
}

for iteration in {1..3}; do
    echo "=== Iteration $iteration ==="

    # Prepare base64
    DOG_B64=$(get_base64 "$DOG_IMG")
    CARD_B64=$(get_base64 "$CARD_IMG")

    start=$(date +%s.%N)

    # 1. hailo-clip
    end1=$(call_and_time "$start" "hailo-clip" curl -X POST http://localhost:5000/v1/classify \
        -H "Content-Type: application/json" \
        -d "{\"image\": \"data:image/png;base64,${DOG_B64}\", \"prompts\": [\"a dog\", \"a cat\", \"a bird\"], \"top_k\": 1}")

    # 2. hailo-vision
    end2=$(call_and_time "$end1" "hailo-vision" curl -X POST http://localhost:11435/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d "{\"model\": \"qwen2-vl-2b-instruct\", \"messages\": [{\"role\": \"user\", \"content\": [{\"type\": \"image\", \"image_url\": {\"url\": \"data:image/png;base64,${DOG_B64}\"}}, {\"type\": \"text\", \"text\": \"Describe this image.\"}]}]}")

    # 3. hailo-whisper
    end3=$(call_and_time "$end2" "hailo-whisper" curl -X POST http://localhost:11437/v1/audio/transcriptions \
        -F "file=@${AUDIO_FILE}" \
        -F "model=Whisper-Base")

    # 4. hailo-ocr
    end4=$(call_and_time "$end3" "hailo-ocr" curl -X POST http://localhost:11436/v1/ocr/extract \
        -H "Content-Type: application/json" \
        -d "{\"image\": \"data:image/png;base64,${CARD_B64}\", \"languages\": [\"en\"]}")

    echo ""
done
#!/usr/bin/env python3

import requests
import base64
import time
import os

# File paths
DOG_IMG = os.path.expanduser("~/raspberry_pi_hailo_ai_services/dog.png")
AUDIO_FILE = os.path.expanduser("~/raspberry_pi_hailo_ai_services/audio2.wav")
CARD_IMG = os.path.expanduser("~/raspberry_pi_hailo_ai_services/card.png")

def get_base64(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def call_clip(image_b64):
    url = "http://localhost:5000/v1/classify"
    data = {
        "image": f"data:image/png;base64,{image_b64}",
        "prompts": ["a dog", "a cat", "a bird"],
        "top_k": 1
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()

def call_vision(image_b64):
    url = "http://localhost:11435/v1/chat/completions"
    data = {
        "model": "qwen2-vl-2b-instruct",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_b64
                    },
                    {
                        "type": "text",
                        "text": "Describe this image."
                    }
                ]
            }
        ]
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()

def call_whisper(audio_file):
    url = "http://localhost:11437/v1/audio/transcriptions"
    with open(audio_file, "rb") as f:
        files = {"file": f}
        data = {"model": "Whisper-Base"}
        response = requests.post(url, files=files, data=data)
    response.raise_for_status()
    return response.json()

def call_ocr(image_b64):
    url = "http://localhost:11436/v1/ocr/extract"
    data = {
        "image": f"data:image/png;base64,{image_b64}",
        "languages": ["en"]
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    return response.json()

for iteration in range(1, 4):
    print(f"=== Iteration {iteration} ===")

    # Prepare base64
    dog_b64 = get_base64(DOG_IMG)

    start = time.time()

    # hailo-vision
    result = call_vision(dog_b64)
    end = time.time()
    print(f"Time for hailo-vision: {end - start:.3f}s")
    print(f"Response: {result['choices'][0]['message']['content']}")
    print()
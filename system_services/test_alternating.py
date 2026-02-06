#!/usr/bin/env python3

import requests
import base64
import time
import json
from datetime import datetime

# Service URLs
CLIP_URL = "http://localhost:5000/v1/classify"
VISION_URL = "http://localhost:11435/v1/chat/completions"

# Read and encode image
with open("dog.png", "rb") as f:
    image_data = f.read()
image_b64 = base64.b64encode(image_data).decode()
image_uri = f"data:image/png;base64,{image_b64}"

# Prompts for CLIP
clip_prompts = [
    "a photo of a dog",
    "a photo of a cat",
    "a photo of a person",
    "a photo of a car"
]

# Prompt for Vision
vision_prompt = "Describe this image in one sentence."

def call_clip():
    start_time = time.time()
    start_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        response = requests.post(CLIP_URL, json={
            "image": image_uri,
            "prompts": clip_prompts,
            "top_k": 1
        }, timeout=30)
        end_time = time.time()
        duration = (end_time - start_time) * 1000  # ms
        if response.status_code == 200:
            result = response.json()
            top_class = result["classifications"][0]
            print(f"[{start_dt}] CLIP: {top_class['text']} (score: {top_class['score']:.3f}) - {duration:.1f}ms")
        else:
            print(f"[{start_dt}] CLIP: Error {response.status_code} - {duration:.1f}ms")
    except Exception as e:
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        print(f"[{start_dt}] CLIP: Exception {str(e)} - {duration:.1f}ms")

def call_vision():
    start_time = time.time()
    start_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    try:
        response = requests.post(VISION_URL, json={
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_uri}},
                        {"type": "text", "text": vision_prompt}
                    ]
                }
            ],
            "temperature": 0.7,
            "max_tokens": 50,
            "stream": False
        }, timeout=30)
        end_time = time.time()
        duration = (end_time - start_time) * 1000  # ms
        if response.status_code == 200:
            result = response.json()
            description = result["choices"][0]["message"]["content"].strip()
            print(f"[{start_dt}] VISION: {description} - {duration:.1f}ms")
        else:
            print(f"[{start_dt}] VISION: Error {response.status_code} - {duration:.1f}ms")
    except Exception as e:
        end_time = time.time()
        duration = (end_time - start_time) * 1000
        print(f"[{start_dt}] VISION: Exception {str(e)} - {duration:.1f}ms")

if __name__ == "__main__":
    print("Starting alternating test: 10 CLIP + 10 VISION calls")
    for i in range(10):
        call_clip()
        call_vision()
    print("Test completed.")
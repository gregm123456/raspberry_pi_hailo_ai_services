#!/usr/bin/env python3
"""
Unified test script for Hailo Vision service.
Supports image classification by URL, local file, or text-only chat completion.
"""

import argparse
import base64
import json
import os
import requests

def main():
    parser = argparse.ArgumentParser(
        description="Unified test script for Hailo Vision service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 test_vision.py url "http://example.com/image.jpg"
  python3 test_vision.py file "/path/to/image.png"
  python3 test_vision.py chat "Hello, how are you?"
        """
    )
    parser.add_argument(
        "mode",
        choices=["url", "file", "chat"],
        help="Mode: 'url' for image classification by URL, 'file' for local image file, 'chat' for text-only completion"
    )
    parser.add_argument(
        "input",
        help="URL, file path, or text prompt depending on mode"
    )
    args = parser.parse_args()

    BASE_URL = "http://localhost:11435/v1/chat/completions"

    if args.mode == "url":
        # Image classification by URL
        payload = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please describe this image."},
                        {"type": "image_url", "image_url": {"url": args.input}}
                    ]
                }
            ],
            "max_tokens": 100
        }
    elif args.mode == "file":
        # Image classification by local file
        if not os.path.exists(args.input):
            print(f"Error: File not found: {args.input}")
            return
        with open(args.input, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(args.input)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        payload = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Please describe this image."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}}
                    ]
                }
            ],
            "max_tokens": 100
        }
    elif args.mode == "chat":
        # Text-only chat completion (note: service requires images, this may fail)
        print("Note: This service is designed for vision tasks and requires images. Text-only may not work.")
        payload = {
            "model": "qwen2-vl-2b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": args.input
                }
            ],
            "max_tokens": 100
        }

    print(f"Submitting request in mode '{args.mode}' with input: {args.input}")
    try:
        response = requests.post(BASE_URL, json=payload, timeout=90)
        if response.status_code == 200:
            result = response.json()
            print("\n--- Response ---")
            print(json.dumps(result, indent=2))
        else:
            print(f"Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"Request Error: {e}")

if __name__ == "__main__":
    main()
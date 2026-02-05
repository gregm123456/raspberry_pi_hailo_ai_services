#!/usr/bin/env python3
"""
Test concurrent access to hailo-vision and hailo-clip services.
Both services use the device manager, which should serialize requests.
"""
import asyncio
import aiohttp
import time
from PIL import Image
import io
import base64

VISION_URL = "http://localhost:11435"
CLIP_URL = "http://localhost:5000"

# Create a simple test image (100x100 red square)
def create_test_image():
    img = Image.new('RGB', (100, 100), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf.getvalue()


async def call_vision(session, image_data, prompt):
    """Call hailo-vision VLM service"""
    start = time.time()
    data = aiohttp.FormData()
    data.add_field('images', image_data, filename='test.png', content_type='image/png')
    data.add_field('prompt', prompt)
    
    async with session.post(f"{VISION_URL}/api/vision", data=data) as resp:
        result = await resp.json()
        elapsed = time.time() - start
        return {"service": "vision", "elapsed": elapsed, "response": result.get("response", "")[:50]}


async def call_clip(session, image_data, labels):
    """Call hailo-clip zero-shot classification service"""
    start = time.time()
    data = aiohttp.FormData()
    data.add_field('image', image_data, filename='test.png', content_type='image/png')
    data.add_field('labels', ','.join(labels))
    
    async with session.post(f"{CLIP_URL}/classify", data=data) as resp:
        result = await resp.json()
        elapsed = time.time() - start
        return {"service": "clip", "elapsed": elapsed, "predictions": result.get("predictions", [])}


async def main():
    print("Testing concurrent hailo-vision and hailo-clip access...")
    print("Both services use the device manager, which serializes device access.")
    print()
    
    # Create test image
    image_data = create_test_image()
    
    async with aiohttp.ClientSession() as session:
        # Test 1: Sequential calls (baseline)
        print("=== Test 1: Sequential calls ===")
        start = time.time()
        vision_result = await call_vision(session, image_data, "What color is this?")
        clip_result = await call_clip(session, image_data, ["red", "blue", "green"])
        sequential_time = time.time() - start
        
        print(f"Vision: {vision_result['response']} ({vision_result['elapsed']:.2f}s)")
        print(f"CLIP: {clip_result['predictions'][:2]} ({clip_result['elapsed']:.2f}s)")
        print(f"Total sequential time: {sequential_time:.2f}s")
        print()
        
        # Test 2: Concurrent calls (should be serialized by device manager)
        print("=== Test 2: Concurrent calls (device manager serializes) ===")
        start = time.time()
        results = await asyncio.gather(
            call_vision(session, image_data, "Describe this image."),
            call_clip(session, image_data, ["red", "blue", "green", "yellow"]),
            call_vision(session, image_data, "What is the dominant color?"),
            call_clip(session, image_data, ["square", "circle", "triangle"]),
        )
        concurrent_time = time.time() - start
        
        for i, result in enumerate(results):
            service = result['service']
            elapsed = result['elapsed']
            if service == 'vision':
                print(f"{i+1}. Vision ({elapsed:.2f}s): {result['response']}")
            else:
                print(f"{i+1}. CLIP ({elapsed:.2f}s): {result['predictions'][:2]}")
        
        print(f"\nTotal concurrent time: {concurrent_time:.2f}s")
        print(f"Speedup vs sequential: {sequential_time/concurrent_time:.2f}x")
        print("\n✓ Test complete! Both services can coexist through device manager.")


if __name__ == "__main__":
    asyncio.run(main())

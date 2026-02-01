import base64
import requests
import json
import os
from pathlib import Path

def classify_image(image_path, prompts):
    url = "http://localhost:5000/v1/classify"
    
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    
    payload = {
        "image": encoded_string,
        "prompts": prompts,
        "top_k": 3
    }
    
    response = requests.post(url, json=payload)
    return response.json()

images_dir = Path("temp_test_images")
images = ["test.png", "tgr.png", "tmp6imzi42v.png", "unnamed.png"]
prompts = [
    "a colorful illustration of people jogging in a park with a kite",
    "a woman cosplaying as Jessie from Team Rocket",
    "a pose estimation skeleton graph",
    "a man riding a bicycle while using a laptop balanced on the handlebars"
]

results = {}
for img in images:
    img_path = images_dir / img
    if img_path.exists():
        print(f"Classifying {img}...")
        results[img] = classify_image(str(img_path), prompts)
    else:
        print(f"File {img_path} not found.")

print("\n--- Results ---")
print(json.dumps(results, indent=2))

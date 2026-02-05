#!/usr/bin/env python3
"""
Simple test script for hailo-depth service.

Runs depth estimation on dog.png and saves the result to the same directory.

Usage:
    python3 test_depth_inference.py [--api-url http://localhost:11436]
"""

import argparse
import base64
import io
import json
import sys
from pathlib import Path

try:
    import requests
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install requests numpy pillow")
    sys.exit(1)


def estimate_depth_via_api(image_path: str, api_url: str = "http://localhost:11436") -> dict:
    """
    Estimate depth via REST API.
    
    Args:
        image_path: Path to input image
        api_url: Base URL of hailo-depth service
    
    Returns:
        Dictionary with depth results
    """
    # Load image
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"📷 Loaded image: {image_path} ({len(image_data)} bytes)")
    
    # Check service health
    try:
        health = requests.get(f"{api_url}/health", timeout=5)
        health.raise_for_status()
        print(f"✓ Service health: {health.json()['status']}")
    except requests.RequestException as e:
        print(f"✗ Service health check failed: {e}")
        print(f"  Make sure hailo-depth service is running:")
        print(f"  sudo systemctl start hailo-depth.service")
        sys.exit(1)
    
    # Perform depth estimation
    print(f"\n🔍 Running depth estimation...")
    
    try:
        response = requests.post(
            f"{api_url}/v1/depth/estimate",
            files={'image': image_data},
            data={
                'output_format': 'both',  # Get both numpy and image outputs
                'normalize': 'true',
                'colormap': 'viridis'
            },
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        # Print results
        print(f"✓ Inference completed in {result['inference_time_ms']:.1f}ms")
        print(f"  Model: {result['model']} ({result['model_type']})")
        print(f"  Input shape: {result['input_shape']}")
        print(f"  Depth shape: {result['depth_shape']}")
        
        if 'stats' in result:
            stats = result['stats']
            print(f"  Stats: min={stats['min']:.3f}, max={stats['max']:.3f}, mean={stats['mean']:.3f}")
        
        return result
        
    except requests.RequestException as e:
        print(f"✗ Inference failed: {e}")
        sys.exit(1)


def save_depth_outputs(result: dict, output_dir: str = ".") -> None:
    """
    Decode and save depth outputs.
    
    Args:
        result: Response dictionary from depth estimation
        output_dir: Directory to save outputs
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save colorized depth image (PNG)
    if 'depth_image' in result and result['depth_image']:
        print(f"\n💾 Saving depth visualization...")
        depth_png_bytes = base64.b64decode(result['depth_image'])
        depth_image_path = output_path / 'depth_visualization.png'
        
        with open(depth_image_path, 'wb') as f:
            f.write(depth_png_bytes)
        
        print(f"  ✓ {depth_image_path} ({len(depth_png_bytes)} bytes)")
    
    # Save numpy array (NPZ)
    if 'depth_map' in result and result['depth_map']:
        print(f"\n💾 Saving depth array...")
        depth_npz_bytes = base64.b64decode(result['depth_map'])
        depth_array_path = output_path / 'depth_array.npz'
        
        with open(depth_array_path, 'wb') as f:
            f.write(depth_npz_bytes)
        
        print(f"  ✓ {depth_array_path} ({len(depth_npz_bytes)} bytes)")
        
        # Load and display array info
        try:
            depth_npz = io.BytesIO(depth_npz_bytes)
            depth_data = np.load(depth_npz)
            depth_array = depth_data['depth']
            depth_npz.close()
            
            print(f"    Shape: {depth_array.shape}")
            print(f"    DType: {depth_array.dtype}")
            print(f"    Range: [{depth_array.min():.3f}, {depth_array.max():.3f}]")
        except Exception as e:
            print(f"    Warning: Could not load array: {e}")
    
    print(f"\n✓ All outputs saved to {output_path}\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test hailo-depth service on dog.png"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:11436",
        help="Base URL of hailo-depth service (default: http://localhost:11436)"
    )
    parser.add_argument(
        "--image",
        default="dog.png",
        help="Input image file (default: dog.png)"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for depth results (default: current directory)"
    )
    
    args = parser.parse_args()
    
    # Verify image exists
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"✗ Image not found: {image_path}")
        sys.exit(1)
    
    print(f"=" * 60)
    print(f"  Hailo Depth Estimation Test")
    print(f"=" * 60)
    
    # Run depth estimation
    result = estimate_depth_via_api(str(image_path), args.api_url)
    
    # Save outputs
    save_depth_outputs(result, args.output_dir)


if __name__ == '__main__':
    main()

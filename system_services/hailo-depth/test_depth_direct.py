#!/usr/bin/env python3
"""
Direct depth estimation test script (no service required).

Imports DepthEstimator directly and runs inference on dog.png.
Output is saved to the same directory as the input image.

Usage:
    python3 test_depth_direct.py [--image dog.png]

Note: This script requires hailo-apps to be on PYTHONPATH and HailoRT to be installed.
For the service-based version, see test_depth_inference.py
"""

import argparse
import asyncio
import base64
import io
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Install with: pip install numpy pillow")
    sys.exit(1)


def load_depth_and_save(result: dict, output_dir: Path, base_name: str = "depth") -> None:
    """
    Decode and save depth outputs.
    
    Args:
        result: Response dictionary from depth estimation
        output_dir: Directory to save outputs
        base_name: Base name for output files
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save colorized depth image (PNG)
    if 'depth_image' in result and result['depth_image']:
        print(f"\n💾 Saving visualization...")
        if isinstance(result['depth_image'], str):
            try:
                depth_png_bytes = base64.b64decode(result['depth_image'])
            except Exception:
                # If it's already bytes or another format
                depth_png_bytes = result['depth_image']
        else:
            depth_png_bytes = result['depth_image']
        
        output_file = output_dir / f"{base_name}_visualization.png"
        with open(output_file, 'wb') as f:
            f.write(depth_png_bytes)
        
        print(f"  ✓ {output_file} ({len(depth_png_bytes)} bytes)")
    
    # Save numpy array (NPZ)
    if 'depth_map' in result and result['depth_map'] is not None:
        print(f"\n💾 Saving array (NPZ)...")
        
        # If it's base64, decode it
        if isinstance(result['depth_map'], str):
            try:
                depth_npz_bytes = base64.b64decode(result['depth_map'])
            except Exception:
                depth_npz_bytes = result['depth_map']
        else:
            depth_npz_bytes = result['depth_map']
        
        output_file = output_dir / f"{base_name}_array.npz"
        with open(output_file, 'wb') as f:
            f.write(depth_npz_bytes)
        
        print(f"  ✓ {output_file} ({len(depth_npz_bytes)} bytes)")
        
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
            print(f"    Warning: Could not parse array: {e}")


async def run_direct_inference(image_path: Path) -> dict:
    """
    Run depth estimation directly using DepthEstimator.
    
    Args:
        image_path: Path to input image
    
    Returns:
        Result dictionary with depth maps
    """
    # Try to import DepthEstimator
    try:
        import sys
        service_dir = Path(__file__).parent
        sys.path.insert(0, str(service_dir))
        sys.path.insert(0, str(service_dir / 'vendor' / 'hailo-apps' / 'hailo_apps' / 'python'))
        
        from hailo_depth_server import DepthServiceConfig, DepthEstimator
    except ImportError as e:
        print(f"✗ Could not import DepthEstimator: {e}")
        print(f"\nMake sure:")
        print(f"  1. HailoRT is installed: sudo apt install dkms hailo-h10-all")
        print(f"  2. hailo-apps is vendored in this directory")
        print(f"  3. Required Python packages are installed")
        sys.exit(1)
    
    # Load and read image
    if not image_path.exists():
        print(f"✗ Image not found: {image_path}")
        sys.exit(1)
    
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"📷 Loaded image: {image_path} ({len(image_data)} bytes)")
    print(f"\n🔍 Running depth estimation (direct)...")
    
    try:
        # Initialize estimator
        config = DepthServiceConfig()
        estimator = DepthEstimator(config)
        
        print(f"  Initializing model: {config.model_name}...")
        await estimator.initialize()
        
        if not estimator.is_loaded:
            print(f"✗ Model failed to load: {estimator.last_error}")
            sys.exit(1)
        
        # Run inference
        result = await estimator.estimate_depth(
            image_data=image_data,
            normalize=True,
            colormap='viridis',
            output_format='both'
        )
        
        print(f"✓ Inference completed in {result['inference_time_ms']:.1f}ms")
        print(f"  Model: {result['model']} ({result['model_type']})")
        print(f"  Input shape: {result['input_shape']}")
        print(f"  Depth shape: {result['depth_shape']}")
        
        if 'stats' in result:
            stats = result['stats']
            print(f"  Stats: min={stats['min']:.3f}, max={stats['max']:.3f}, mean={stats['mean']:.3f}")
        
        # Cleanup
        await estimator.shutdown()
        
        return result
        
    except Exception as e:
        print(f"✗ Inference failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Direct depth estimation test on dog.png (no service required)"
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
    
    image_path = Path(args.image)
    output_dir = Path(args.output_dir)
    
    print(f"=" * 60)
    print(f"  Hailo Depth Estimation Test (Direct)")
    print(f"=" * 60)
    
    # Run async function
    try:
        result = asyncio.run(run_direct_inference(image_path))
        load_depth_and_save(result, output_dir, base_name="depth")
        print(f"✓ All outputs saved to {output_dir.absolute()}\n")
    except KeyboardInterrupt:
        print("\n✗ Interrupted by user")
        sys.exit(1)


if __name__ == '__main__':
    main()

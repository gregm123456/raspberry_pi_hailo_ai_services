#!/usr/bin/env python3
"""
Test script to verify if Hailo-10H can keep multiple networks loaded simultaneously.

This explores whether we can:
1. Load multiple HEF models into the device memory
2. Keep them loaded concurrently (without unloading/reloading)
3. Switch between them for inference without re-initialization
4. Measure memory and performance impact

Usage:
    python3 test_multi_network_load.py
"""

import sys
import time
import psutil
import os
from pathlib import Path

try:
    import hailo_platform
    from hailo_platform.genai import VLM
    from hailo_apps.python.core.common.defines import SHARED_VDEVICE_GROUP_ID
except ImportError as e:
    print(f"ERROR: Missing dependency: {e}")
    print("Install with: sudo apt install python3-h10-hailort")
    print("And ensure hailo-vision is installed: sudo ./system_services/hailo-vision/install.sh")
    sys.exit(1)


def get_process_memory_mb():
    """Get current process memory usage in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def discover_available_models():
    """Discover available HEF model files from hailo-apps resources."""
    resources_base = Path("/var/lib/hailo-vision/resources/models/hailo10h")
    
    if not resources_base.exists():
        print(f"ERROR: Resources directory not found at {resources_base}")
        return []
    
    models = list(resources_base.glob("*.hef"))
    if not models:
        print(f"ERROR: No HEF files found in {resources_base}")
        print("Install models first using: sudo ./system_services/hailo-vision/install.sh")
        return []
    
    return sorted(models)


def test_single_device_scan():
    """Test: Can we scan for devices?"""
    print("\n=== Test 1: Device Scan ===")
    try:
        devices = hailo_platform.Device.scan()
        print(f"✓ Found {len(devices)} device(s)")
        for device_id in devices:
            print(f"  - Device: {device_id}")
        return devices
    except Exception as e:
        print(f"✗ Device scan failed: {e}")
        return []


def test_device_open():
    """Test: Can we open a device?"""
    print("\n=== Test 2: Device Open/Close ===")
    try:
        device = hailo_platform.Device()
        device_id = device.device_id
        print(f"✓ Opened device: {device_id}")
        
        # Check for any pre-loaded networks
        loaded = device.loaded_network_groups
        print(f"✓ Pre-loaded network groups: {len(loaded)}")
        
        device.release()
        print("✓ Device released cleanly")
        return True
    except Exception as e:
        print(f"✗ Device open/close failed: {e}")
        return False


def test_single_network_load(model_path):
    """Test: Can we load a single network?"""
    print(f"\n=== Test 3: Single Network Load ===")
    print(f"Model: {model_path.name}")
    
    try:
        device = hailo_platform.Device()
        print(f"Device opened: {device.device_id}")
        
        mem_before = get_process_memory_mb()
        print(f"Memory before load: {mem_before:.1f} MB")
        
        start_time = time.time()
        params = hailo_platform.VDevice.create_params()
        params.group_id = SHARED_VDEVICE_GROUP_ID
        vdevice = hailo_platform.VDevice(params)
        vlm = VLM(vdevice, str(model_path))
        load_time = time.time() - start_time
        
        mem_after = get_process_memory_mb()
        print(f"✓ Network loaded in {load_time:.2f}s")
        print(f"Memory after load: {mem_after:.1f} MB (Δ {mem_after - mem_before:.1f} MB)")
        
        loaded = device.loaded_network_groups
        print(f"✓ Loaded network groups: {len(loaded)}")
        for i, net in enumerate(loaded):
            print(f"  [{i}] {net}")
        
        vdevice.release()
        device.release()
        return True
    except Exception as e:
        print(f"✗ Single network load failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dual_network_load(model1_path, model2_path):
    """Test: Can we load TWO networks simultaneously?"""
    print(f"\n=== Test 4: Dual Network Load (Sequential) ===")
    print(f"Model 1: {model1_path.name}")
    print(f"Model 2: {model2_path.name}")
    
    try:
        device = hailo_platform.Device()
        device_id = device.device_id
        print(f"Device opened: {device_id}")
        
        # Create VDevice (inference context)
        params = hailo_platform.VDevice.create_params()
        params.group_id = SHARED_VDEVICE_GROUP_ID
        vdevice = hailo_platform.VDevice(params)
        
        mem_before = get_process_memory_mb()
        print(f"Memory before loads: {mem_before:.1f} MB")
        
        # Load first network
        print(f"\nLoading network 1...")
        start_time = time.time()
        vlm1 = VLM(vdevice, str(model1_path))
        load_time1 = time.time() - start_time
        print(f"✓ Network 1 loaded in {load_time1:.2f}s")
        
        loaded_after_1 = device.loaded_network_groups
        print(f"  Loaded networks: {len(loaded_after_1)}")
        
        mem_after_1 = get_process_memory_mb()
        print(f"  Memory: {mem_after_1:.1f} MB (Δ {mem_after_1 - mem_before:.1f} MB)")
        
        # Load second network
        print(f"\nLoading network 2...")
        start_time = time.time()
        try:
            vlm2 = VLM(vdevice, str(model2_path))
            load_time2 = time.time() - start_time
            print(f"✓ Network 2 loaded in {load_time2:.2f}s")
            
            loaded_after_2 = device.loaded_network_groups
            print(f"  Loaded networks: {len(loaded_after_2)}")
            
            mem_after_2 = get_process_memory_mb()
            print(f"  Memory: {mem_after_2:.1f} MB (Δ {mem_after_2 - mem_before:.1f} MB)")
            
            # SUCCESS: Both networks loaded simultaneously!
            print(f"\n✓✓✓ SUCCESS: Both networks loaded simultaneously!")
            print(f"    Device has {len(loaded_after_2)} network groups resident in memory")
            
            vdevice.release()
            device.release()
            return True
            
        except Exception as e:
            print(f"⚠ Network 2 load failed: {e}")
            print(f"  This suggests the device may only support one loaded network at a time")
            vdevice.release()
            device.release()
            return False
            
    except Exception as e:
        print(f"✗ Dual network load failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_network_switching(model1_path, model2_path):
    """Test: Can we efficiently switch between pre-loaded networks?"""
    print(f"\n=== Test 5: Network Switching ===")
    print(f"Model 1: {model1_path.name}")
    print(f"Model 2: {model2_path.name}")
    
    try:
        device = hailo_platform.Device()
        params = hailo_platform.VDevice.create_params()
        params.group_id = SHARED_VDEVICE_GROUP_ID
        vdevice = hailo_platform.VDevice(params)
        
        # Load both networks
        print("Loading networks...")
        vlm1 = VLM(vdevice, str(model1_path))
        vlm2 = VLM(vdevice, str(model2_path))
        
        loaded = device.loaded_network_groups
        print(f"✓ {len(loaded)} networks loaded")
        
        # Attempt to switch between them
        print("\nAttempting to use network 1...")
        try:
            print(f"  Network 1 object: {vlm1}")
            print(f"  Can infer directly: {hasattr(vlm1, 'infer')}")
        except Exception as e:
            print(f"  Note: {e}")
        
        print("\nAttempting to use network 2...")
        try:
            print(f"  Network 2 object: {vlm2}")
            print(f"  Can infer directly: {hasattr(vlm2, 'infer')}")
        except Exception as e:
            print(f"  Note: {e}")
        
        vdevice.release()
        device.release()
        print("✓ Cleanup successful")
        return True
        
    except Exception as e:
        print(f"✗ Network switching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 70)
    print("Hailo-10H Multi-Network Concurrent Load Test")
    print("=" * 70)
    
    # Test 1: Device Scan
    devices = test_single_device_scan()
    if not devices:
        print("\nERROR: No devices found. Verify Hailo driver is installed.")
        sys.exit(1)
    
    # Test 2: Device Open/Close
    if not test_device_open():
        print("\nERROR: Cannot open device.")
        sys.exit(1)
    
    # Discover available models
    print("\n=== Discovering Available Models ===")
    models = discover_available_models()
    if not models:
        print("ERROR: No models found. Run install.sh first.")
        sys.exit(1)
    
    print(f"Found {len(models)} model(s):")
    for i, model in enumerate(models):
        print(f"  [{i}] {model.name}")
    
    # Test 3: Single Network Load (baseline)
    if models:
        if not test_single_network_load(models[0]):
            print("WARNING: Single network load failed. Skipping multi-network tests.")
            sys.exit(1)
    
    # Test 4: Dual Network Load (the critical test)
    if len(models) >= 2:
        success = test_dual_network_load(models[0], models[1])
        
        if success:
            # Test 5: Network Switching
            test_network_switching(models[0], models[1])
    else:
        print(f"\nWARNING: Only {len(models)} model(s) available. Need at least 2 for dual-load test.")
        print("Install additional models to complete the test.")
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print("""
Interpretation:
  ✓ Test 4 "Dual Network Load" succeeds:
    → Device CAN keep multiple networks loaded simultaneously
    → Potential for state manager daemon with hot-swappable inference
    → Services can be lightweight clients without device management
  
  ✗ Test 4 "Dual Network Load" fails:
    → Device supports only one active network at a time
    → Must use service switching approach
    → Consider optimizing switch latency instead
""")
    print("=" * 70)


if __name__ == "__main__":
    main()

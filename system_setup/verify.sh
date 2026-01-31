#!/usr/bin/env bash
#
# Hailo-10H Verification Script
# Performs health checks on Hailo driver and device after installation
#

set -uo pipefail

# Color output (falls back to plain if not supported)
HAS_COLOR=true
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

if [[ ! -t 1 ]]; then
    HAS_COLOR=false
fi

# ============================================================================
# Output Functions
# ============================================================================

pass() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${GREEN}✓${NC} $*"
    else
        echo "[PASS] $*"
    fi
}

fail() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${RED}✗${NC} $*"
    else
        echo "[FAIL] $*"
    fi
}

warn() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${YELLOW}⚠${NC} $*"
    else
        echo "[WARN] $*"
    fi
}

info() {
    if [[ $HAS_COLOR == true ]]; then
        echo -e "${BLUE}ℹ${NC} $*"
    else
        echo "• $*"
    fi
}

# ============================================================================
# Verification Functions
# ============================================================================

check_device_node() {
    echo ""
    info "▶ Device Detection"
    
    if [[ -e /dev/hailo0 ]]; then
        pass "Device node /dev/hailo0 exists"
        
        # Check permissions
        if [[ -r /dev/hailo0 && -w /dev/hailo0 ]]; then
            pass "Device readable and writable"
        else
            warn "Device exists but may have permission issues"
            echo "    Current user: $(whoami)"
            echo "    Device permissions: $(ls -la /dev/hailo0 | awk '{print $1, $3, $4}')"
        fi
        return 0
    else
        fail "Device node /dev/hailo0 not found"
        echo "    Troubleshooting: Run 'dmesg | tail -20' to check for kernel errors"
        return 1
    fi
}

check_kernel_module() {
    echo ""
    info "▶ Kernel Module"
    
    if lsmod | grep -q "^hailo"; then
        pass "Hailo kernel module loaded"
        local version=$(lsmod | grep "^hailo" | awk '{print $3}')
        
        # Get more details from dmesg
        if dmesg | grep -q "hailo: Init module"; then
            local driver_version=$(dmesg | grep "hailo: Init module" | grep -oP 'driver version \K[0-9.]+' | tail -1)
            if [[ -n "$driver_version" ]]; then
                pass "Driver version: $driver_version"
            fi
        fi
        return 0
    else
        fail "Hailo kernel module not loaded"
        echo "    Module should be: hailo or hailo_h10h"
        return 1
    fi
}

check_firmware() {
    echo ""
    info "▶ Firmware"
    
    if command -v hailortcli &> /dev/null; then
        if hailortcli fw-control identify &> /dev/null; then
            pass "Firmware detected and responsive"
            
            # Extract version
            local fw_version=$(hailortcli fw-control identify 2>/dev/null | grep "Firmware Version" | grep -oP 'Version: \K[0-9.]+' || echo "unknown")
            if [[ "$fw_version" != "unknown" ]]; then
                pass "Firmware version: $fw_version"
            fi
            
            # Extract device architecture
            local arch=$(hailortcli fw-control identify 2>/dev/null | grep "Device Architecture" | grep -oP 'Architecture: \K\S+' || echo "unknown")
            if [[ "$arch" != "unknown" ]]; then
                pass "Device architecture: $arch"
            fi
            
            return 0
        else
            fail "hailortcli available but device not responding"
            return 1
        fi
    else
        fail "hailortcli command not found (libhailort not installed?)"
        return 1
    fi
}

check_dmesg_logs() {
    echo ""
    info "▶ Kernel Logs"
    
    if dmesg | grep -q "Firmware was loaded successfully"; then
        pass "Firmware loaded successfully (kernel log verified)"
        return 0
    elif dmesg | grep -q "hailo"; then
        warn "Hailo kernel logs found but firmware status unclear"
        echo "    Run 'dmesg | grep hailo | tail -10' to inspect"
        return 1
    else
        fail "No Hailo kernel logs found"
        return 1
    fi
}

check_device_tree() {
    echo ""
    info "▶ Hardware Detection"
    
    if grep -q "Raspberry Pi 5" /proc/device-tree/model 2>/dev/null; then
        pass "Raspberry Pi 5 detected"
    else
        warn "Could not verify Raspberry Pi 5 from device tree"
        echo "    This may be normal in some emulation environments"
    fi
}

# ============================================================================
# Diagnostic Output
# ============================================================================

show_hailortcli_output() {
    echo ""
    info "▶ Full Device Information (hailortcli)"
    
    if command -v hailortcli &> /dev/null; then
        echo ""
        hailortcli fw-control identify 2>/dev/null || {
            warn "hailortcli failed; this may indicate a driver issue"
        }
        echo ""
    fi
}

show_kernel_details() {
    echo ""
    info "▶ Kernel Module Details"
    echo ""
    
    echo "Loaded modules related to Hailo:"
    lsmod | grep hailo || echo "  (none found)"
    echo ""
}

# ============================================================================
# Summary
# ============================================================================

main() {
    local total=0
    local failed=0
    
    echo ""
    info "╔══════════════════════════════════════════════════════════╗"
    info "║   Hailo-10H System Verification                         ║"
    info "╚══════════════════════════════════════════════════════════╝"
    echo ""
    
    # Run checks
    check_device_node || ((failed++))
    ((total++))
    
    check_kernel_module || ((failed++))
    ((total++))
    
    check_firmware || ((failed++))
    ((total++))
    
    check_dmesg_logs || ((failed++))
    ((total++))
    
    check_device_tree
    ((total++))
    
    # Show diagnostic info
    show_hailortcli_output
    show_kernel_details
    
    # Summary
    echo ""
    info "═══════════════════════════════════════════════════════════"
    if [[ $failed -eq 0 ]]; then
        pass "All checks passed! System is ready."
        pass "Hailo-10H is configured and ready to use."
        echo ""
        info "Next steps:"
        info "  • Install an AI service (e.g., hailo-ollama)"
        info "  • Run: cd ../system_services/hailo-ollama && bash install.sh"
        echo ""
        return 0
    else
        fail "$failed of $total checks failed"
        echo ""
        info "Troubleshooting:"
        info "  • See TROUBLESHOOTING.md in this directory"
        info "  • Check kernel logs: dmesg | grep -i hailo"
        info "  • Verify device: ls -la /dev/hailo0"
        info "  • Verify packages: dpkg -l | grep hailo"
        echo ""
        return 1
    fi
}

main "$@"

# Service Port Reconciliation Plan

**Date:** February 5, 2026  
**Status:** Draft for Review  
**Author:** Greg  

## Overview

This plan resolves port conflicts among Hailo AI system services to enable simultaneous deployment without configuration changes. Currently, 2 ports have conflicts affecting 5 services.

### Current Conflicts
- **Port 5002:** hailo-face (frozen) vs hailo-piper (working)
- **Port 11436:** hailo-ocr, hailo-depth, hailo-pose (all working, no priority)

### Constraints
1. **hailo-ollama** retains Ollama's standard port 11434 (priority service)
2. **hailo-face** and **hailo-scrfd** are frozen/standby; keep their default ports (5002, 5001)
3. Prefer conventional HTTP ports where possible
4. Minimize changes; stay within established 5000s and 11400s ranges

## Proposed Port Assignments

| Service | Current Port | New Port | Status | Rationale |
|---------|--------------|----------|--------|-----------|
| hailo-ollama | 11434 | 11434 | ✓ No change | Priority (Ollama standard) |
| hailo-whisper | 11437 | 11437 | ✓ No change | Unique, no conflict |
| hailo-clip | 5000 | 5000 | ✓ No change | Unique, no conflict |
| hailo-vision | 11435 | 11435 | ✓ No change | Unique, no conflict |
| hailo-florence | 11438 | 11438 | ✓ No change | Unique, no conflict |
| hailo-scrfd | 5001 | 5001 | ✓ No change | Frozen service (priority) |
| hailo-face | 5002 | 5002 | ✓ No change | Frozen service (priority) |
| **hailo-piper** | **5002** | **5003** | ⚠️ Change | Conflict with frozen hailo-face |
| **hailo-ocr** | **11436** | **11436** | ✓ Prioritized | Alphabetically first of 3-way conflict |
| **hailo-depth** | **11436** | **11439** | ⚠️ Change | 3-way port conflict |
| **hailo-pose** | **11436** | **11440** | ⚠️ Change | 3-way port conflict |

### Final Port Map (Post-Reconciliation)
- **5000:** hailo-clip
- **5001:** hailo-scrfd (frozen)
- **5002:** hailo-face (frozen)
- **5003:** hailo-piper
- **11434:** hailo-ollama
- **11435:** hailo-vision
- **11436:** hailo-ocr
- **11437:** hailo-whisper
- **11438:** hailo-florence
- **11439:** hailo-depth
- **11440:** hailo-pose

## Implementation Steps

### 1. Update hailo-piper Configuration
- **File:** `system_services/hailo-piper/hailo-piper.yaml`
- **Change:** `port: 5002` → `port: 5003`
- **File:** `system_services/hailo-piper/API_SPEC.md`
- **Change:** Base URL `http://localhost:5002` → `http://localhost:5003`
- **Rationale:** Adjacent to frozen services; stays in 5000s range

### 2. Update hailo-depth Configuration
- **File:** `system_services/hailo-depth/hailo-depth.yaml`
- **Change:** `port: 11436` → `port: 11439`
- **File:** `system_services/hailo-depth/API_SPEC.md`
- **Change:** Base URL `http://localhost:11436` → `http://localhost:11439`
- **Rationale:** Next available in 11400s sequence; avoids existing services

### 3. Update hailo-pose Configuration
- **File:** `system_services/hailo-pose/hailo-pose.yaml`
- **Change:** `port: 11436` → `port: 11440`
- **File:** `system_services/hailo-pose/API_SPEC.md`
- **Change:** Base URL `http://localhost:11436` → `http://localhost:11440`
- **Rationale:** Next available in 11400s sequence; logical progression

### 4. Verify hailo-ocr Configuration
- **File:** `system_services/hailo-ocr/hailo-ocr.yaml`
- **Confirm:** `port: 11436` (no change needed)
- **File:** `system_services/hailo-ocr/API_SPEC.md`
- **Confirm:** Base URL `http://localhost:11436` ✓
- **Rationale:** Alphabetically first; foundational OCR service

### 5. Update Systemd Service Units
Check service installer scripts for hardcoded port references:
- `system_services/hailo-piper/install.sh` (or equivalent)
- `system_services/hailo-depth/install.sh`
- `system_services/hailo-pose/install.sh`

### 6. Update Client/Integration References
Search workspace for hardcoded port references:
- **5002 references:** Update to 5003 for hailo-piper
- **11436 references:** Update to 11439 for hailo-depth, 11440 for hailo-pose
- **Files to check:** Test harnesses, examples, shell scripts in `system_services/` and `build_plans/`

### 7. Update Documentation
- Update any README files mentioning default ports
- Update integration guides or deployment docs

## Verification Steps

### Port Uniqueness Check
```bash
# After changes, verify no duplicates
grep -r "port.*5003\|port.*11439\|port.*11440" system_services/*/
# Should show only the updated services
```

### Service Health Checks
```bash
# Test new ports
curl http://localhost:5003/health    # hailo-piper (was 5002)
curl http://localhost:11439/health   # hailo-depth (was 11436)
curl http://localhost:11440/health   # hailo-pose (was 11436)
curl http://localhost:11436/health   # hailo-ocr (unchanged)

# Verify frozen services unaffected
curl http://localhost:5001/health    # hailo-scrfd (unchanged)
curl http://localhost:5002/health    # hailo-face (unchanged)
```

### Systemd Status
```bash
systemctl status hailo-piper hailo-depth hailo-pose hailo-ocr
# All should show active (running)
```

## Decision Rationale

### Port Selection Criteria
- **Conventional ranges:** Stick to 5000s (HTTP APIs) and 11400s (Hailo services)
- **Sequential assignment:** Use next available ports to minimize gaps
- **Minimal disruption:** Change only what's necessary
- **Future-proofing:** Leave room for additional services

### Conflict Resolution Logic
1. **5002 conflict:** hailo-face (frozen) wins; hailo-piper moves to 5003
2. **11436 conflict:** No priority among working services; hailo-ocr keeps port (alphabetical); others get sequential ports

### Why These Specific Ports?
- **5003:** Adjacent to 5001/5002; maintains API service grouping
- **11439/11440:** Skip 11437/11438 (existing); follow sequence from 11436

## Risks & Mitigations

### Risk: Breaking Existing Deployments
- **Mitigation:** Document changes clearly; provide migration guide

### Risk: Port Conflicts with Other Systems
- **Mitigation:** All ports are non-standard; verify against local services

### Risk: Service Installer Scripts
- **Mitigation:** Review and update installers before deployment

## Next Steps

1. **Review & Approval:** Get feedback on this plan
2. **Implementation:** Apply configuration changes
3. **Testing:** Verify all services start and respond on new ports
4. **Documentation:** Update all references and docs
5. **Deployment:** Roll out changes to production systems

## Appendix: Current API Specs Summary

| Service | Port | Base URL | Status |
|---------|------|----------|--------|
| hailo-ollama | 11434 | http://localhost:11434 | Priority |
| hailo-piper | 5002 → 5003 | http://localhost:5003 | Change |
| hailo-whisper | 11437 | http://localhost:11437 | No change |
| hailo-ocr | 11436 | http://localhost:11436 | No change |
| hailo-clip | 5000 | http://localhost:5000 | No change |
| hailo-depth | 11436 → 11439 | http://localhost:11439 | Change |
| hailo-face | 5002 | http://localhost:5002 | Frozen |
| hailo-florence | 11438 | http://localhost:11438 | No change |
| hailo-pose | 11436 → 11440 | http://localhost:11440 | Change |
| hailo-scrfd | 5001 | http://localhost:5001 | Frozen |
| hailo-vision | 11435 | http://localhost:11435 | No change |

---

**Last Updated:** February 5, 2026  
**Version:** 1.0 Draft
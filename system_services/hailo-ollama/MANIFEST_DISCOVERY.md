# Hailo-Ollama Manifest Discovery Solution

## Problem Statement

The `hailo-ollama` systemd service failed to discover model manifests, resulting in:
- Empty model lists: `GET /hailo/v1/list` returned `{"models":[]}`
- Failed model pulls: `POST /api/pull` returned 500 Internal Server Error with "Null pointer" exceptions

When running `hailo-ollama` manually (not as a systemd service), model discovery worked correctly and manifests were found.

## Root Cause Analysis

### Manifest Storage Architecture

The Hailo GenAI Model Zoo Debian package (`hailo_gen_ai_model_zoo_5.1.1_arm64.deb`) installs model manifests to:
```
/usr/share/hailo-ollama/models/manifests/
├── deepseek_r1_distill_qwen/
│   └── 1.5b/
│       └── manifest.json
├── llama3.2/
│   └── 3b/
│       └── manifest.json
├── qwen2/
│   └── 1.5b/
│       └── manifest.json
├── qwen2.5-coder/
│   └── 1.5b/
│       └── manifest.json
└── qwen2.5-instruct/
    └── 1.5b/
        └── manifest.json
```

### XDG Base Directory Specification

`hailo-ollama` follows the XDG Base Directory specification for locating configuration and data:
- `XDG_CONFIG_HOME`: Configuration files (default: `~/.config`)
- `XDG_CONFIG_DIRS`: System-wide config directories (default: `/etc/xdg`)
- `XDG_DATA_HOME`: User-specific data (default: `~/.local/share`)
- `XDG_DATA_DIRS`: System-wide data directories (default: `/usr/local/share:/usr/share`)

### Discovery Mechanism Investigation

Through `strace` analysis, we found that `hailo-ollama` searches for manifests **only** in:
```
$XDG_DATA_HOME/hailo-ollama/models/manifests/
```

**Not** in:
```
$XDG_DATA_DIRS/hailo-ollama/models/manifests/
```

This is a critical distinction—the application only checks `XDG_DATA_HOME` (writable user data), not `XDG_DATA_DIRS` (read-only system data).

### Systemd Service Environment

Our systemd service configuration set:
```ini
Environment=XDG_DATA_HOME=/var/lib
Environment=XDG_DATA_DIRS=/var/lib:/usr/share:/usr/local/share
```

This directed `hailo-ollama` to search:
```
/var/lib/hailo-ollama/models/manifests/
```

Since the service writes downloaded model blobs to `/var/lib/hailo-ollama/models/blobs/`, we needed manifests in the same tree.

## Attempted Solutions

### Attempt 1: Symlinks

Initial approach: Symlink package manifests into the service data directory.

```bash
ln -s /usr/share/hailo-ollama/models/manifests/qwen2 \
      /var/lib/hailo-ollama/models/manifests/qwen2
```

**Result:** Failed. Directory listing showed symlinks but `hailo-ollama` didn't discover models.

**Why it failed:** The `hailo-ollama` binary uses `readdir()` with `struct dirent` type checking. Symlinks return `d_type == DT_LNK`, not `DT_DIR`. The application's directory scanner skips non-directory entries, so symlinked directories aren't traversed.

### Attempt 2: Fixing XDG_DATA_DIRS Path

Modified systemd service to include `/usr/share` in `XDG_DATA_DIRS`:
```ini
Environment=XDG_DATA_DIRS=/var/lib:/usr/share:/usr/local/share
```

**Result:** Still failed.

**Why it failed:** As discovered through strace, `hailo-ollama` **only searches `XDG_DATA_HOME`**, not `XDG_DATA_DIRS`. Adding paths to `XDG_DATA_DIRS` has no effect on manifest discovery.

### Solution: Systemd Bind Mount

Use systemd's `BindReadOnlyPaths` directive to mount package manifests into the service data directory:

```ini
BindReadOnlyPaths=/usr/share/hailo-ollama/models/manifests:/var/lib/hailo-ollama/models/manifests
```

**Result:** Success ✓

Models discovered:
```json
{
  "models": [
    "deepseek_r1_distill_qwen:1.5b",
    "llama3.2:3b",
    "qwen2.5-coder:1.5b",
    "qwen2.5-instruct:1.5b",
    "qwen2:1.5b"
  ]
}
```

Model pull succeeded:
```json
{"status":"success"}
```

## Why Bind Mounts Work

### Directory Entry Types

When using `readdir()`, the kernel returns different `d_type` values:
- **Symlink:** `d_type == DT_LNK` (type 10)
- **Directory:** `d_type == DT_DIR` (type 4)

### Bind Mount Behavior

A bind mount creates a **mount point** that overlays the target directory. From the application's perspective:
- The mounted directory appears as a **real directory** (`DT_DIR`)
- All subdirectories and files are accessible as if they were physically present
- Read-only mount (`BindReadOnlyPaths`) prevents the service from modifying package-installed manifests

### Systemd Integration

`BindReadOnlyPaths` provides mount namespacing **per-service**:
- Mount is visible only to the `hailo-ollama.service` process tree
- No system-wide `/etc/fstab` modifications required
- Automatic cleanup on service stop
- Idempotent: safe to restart service without manual umount

## Implementation

### Service Unit Configuration

File: `/etc/systemd/system/hailo-ollama.service`

```ini
[Unit]
Description=Hailo Ollama (Ollama-compatible API on Hailo-10H)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=hailo-ollama
Group=hailo-ollama
WorkingDirectory=/var/lib/hailo-ollama
StateDirectory=hailo-ollama

# Bind package manifests into the writable data directory
BindReadOnlyPaths=/usr/share/hailo-ollama/models/manifests:/var/lib/hailo-ollama/models/manifests

# XDG wiring: force config + data locations
Environment=XDG_CONFIG_HOME=/etc/xdg
Environment=XDG_CONFIG_DIRS=/etc/xdg
Environment=XDG_DATA_HOME=/var/lib
Environment=XDG_DATA_DIRS=/var/lib:/usr/share:/usr/local/share

ExecStart=/usr/bin/env hailo-ollama
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Installer Script Changes

File: `install.sh`

```bash
create_state_directories() {
    log "Creating model directory structure"
    mkdir -p /var/lib/hailo-ollama/models/manifests
    mkdir -p /var/lib/hailo-ollama/models/blobs
    # Ensure manifest directory is clean; systemd will bind-mount package manifests
    rm -rf /var/lib/hailo-ollama/models/manifests/*
    
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" /var/lib/hailo-ollama
    chmod -R u+rwX,g+rX,o-rwx /var/lib/hailo-ollama
}
```

The installer now:
1. Creates an empty `/var/lib/hailo-ollama/models/manifests/` directory
2. Cleans any existing content (old symlinks)
3. Systemd bind-mounts package manifests on service start

## Verification

### Check Model Discovery
```bash
curl -s http://localhost:11434/hailo/v1/list | jq
```

Expected output:
```json
{
  "models": [
    "deepseek_r1_distill_qwen:1.5b",
    "llama3.2:3b",
    "qwen2.5-coder:1.5b",
    "qwen2.5-instruct:1.5b",
    "qwen2:1.5b"
  ]
}
```

### Test Model Pull
```bash
curl -s http://localhost:11434/api/pull \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen2:1.5b", "stream": false}'
```

Expected output (after download completes):
```json
{"status":"success"}
```

### Verify Bind Mount
```bash
sudo systemctl status hailo-ollama.service
mount | grep hailo-ollama
```

Should show:
```
/dev/sdXX on /var/lib/hailo-ollama/models/manifests type ext4 (ro,...)
```

### Check Downloaded Models
```bash
sudo ls -lh /var/lib/hailo-ollama/models/blobs/
```

After successful pull, blob files appear with SHA256 names.

## Comparison: Manual vs Service

### Manual Execution

When running `hailo-ollama` manually:
```bash
hailo-ollama
```

Default environment:
- `XDG_DATA_HOME=~/.local/share` (not set, defaults to home)
- `XDG_DATA_DIRS=/usr/local/share:/usr/share` (system default)

But manifests are found because the package also installs to `/usr/share`, and manual execution may follow different code paths or have fallback discovery logic.

### Systemd Service Execution

Constrained environment:
- Runs as `hailo-ollama` user with limited privileges
- `XDG_DATA_HOME=/var/lib` (writable service state)
- Must have manifests in `$XDG_DATA_HOME/hailo-ollama/models/manifests/`
- Bind mount provides read-only access to package manifests

## Alternative Solutions Considered

### Option 1: Copy Manifests on Install
Copy `/usr/share/hailo-ollama/models/manifests/` → `/var/lib/hailo-ollama/models/manifests/`

**Pros:**
- Simple, no mount dependencies
- Works with any filesystem

**Cons:**
- Duplicates data (5 manifests × ~1KB each)
- Stale data after package upgrades
- Requires re-copy logic in installer
- Must handle version conflicts

**Verdict:** Not selected—violates DRY principle and creates synchronization burden.

### Option 2: Patch hailo-ollama Binary
Modify the application to search `XDG_DATA_DIRS` in addition to `XDG_DATA_HOME`.

**Pros:**
- Most "correct" solution per XDG spec
- No mount/symlink workarounds

**Cons:**
- Requires source code access
- Rebuild for each package version
- Diverges from upstream
- Maintenance burden

**Verdict:** Not viable—closed-source Debian package.

### Option 3: Bind Mount (Selected)
Use systemd `BindReadOnlyPaths` to overlay package manifests.

**Pros:**
- Clean separation: read-only system data, writable user data
- Automatic updates when package upgrades
- Per-service namespace (no system-wide changes)
- Idempotent and declarative
- No application modifications

**Cons:**
- Requires systemd 231+ (met on Raspberry Pi OS)
- Slightly more complex than symlinks
- Mount point visible in service process only

**Verdict:** Selected—best balance of maintainability and correctness.

## Lessons Learned

1. **XDG_DATA_HOME ≠ XDG_DATA_DIRS**: Applications may only search user data, not system data directories

2. **Symlinks are not directories**: `readdir()` type checking differentiates between `DT_LNK` and `DT_DIR`

3. **Bind mounts are transparent**: Mount namespaces allow per-service filesystem views without system-wide configuration

4. **strace is essential**: Without tracing `openat()` calls, the actual search path wasn't obvious

5. **Test assumptions**: "It works manually" doesn't mean it works in a restricted service environment

## Future Considerations

### Package Updates

When `hailo_gen_ai_model_zoo` is upgraded:
- New manifests appear automatically (bind mount follows underlying directory)
- Service restart: `sudo systemctl restart hailo-ollama.service`
- No manual steps required

### Adding Custom Models

If users want custom manifests:
1. **Option A:** Place in `/usr/share/hailo-ollama/models/manifests/` (requires elevated privileges)
2. **Option B:** Modify service to use multiple bind mounts for custom manifest directory
3. **Option C:** Extend installer to copy custom manifests into bind target

### Multi-User Scenarios

Current solution is single-service. For multi-user:
- Each user needs their own `XDG_DATA_HOME`
- Separate bind mounts per service instance
- Or: shared read-only manifests + per-user blob storage

## References

- XDG Base Directory Specification: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
- systemd.exec(5): `BindReadOnlyPaths` directive
- Linux `readdir(3)` and `struct dirent`
- Hailo GenAI Model Zoo: https://hailo.ai/developer-zone/
- Raspberry Pi AI HAT+ Documentation: https://www.raspberrypi.com/documentation/computers/ai.html

---

**Document Version:** 1.0  
**Last Updated:** January 31, 2026  
**Issue Resolution:** hailo-ollama systemd service manifest discovery

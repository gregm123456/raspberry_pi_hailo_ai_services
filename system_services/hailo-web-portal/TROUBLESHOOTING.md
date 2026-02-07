# Troubleshooting Hailo Web Portal

## Service fails to start

**Diagnostic:**
```bash
sudo systemctl status hailo-web-portal.service
sudo journalctl -u hailo-web-portal.service -n 50
```

**Likely causes:**
- Python venv missing or corrupted
- Dependencies not installed
- Port 7860 already in use

**Fix:**
1. Reinstall: `sudo ./install.sh`
2. Check for port conflicts: `sudo lsof -i :7860`

## Device status shows error

**Diagnostic:**
```bash
curl http://127.0.0.1:5099/v1/device/status
sudo systemctl status hailo-device-status.service
```

**Likely causes:**
- `hailo-device-status` not running
- Wrong URL in `HAILO_DEVICE_STATUS_URL`

**Fix:**
1. Start service: `sudo systemctl restart hailo-device-status.service`
2. Verify URL environment in the unit file

## Service control returns sudo errors

**Diagnostic:**
```bash
sudo cat /etc/sudoers.d/hailo-web-portal-systemctl
```

**Likely causes:**
- Sudoers file missing or permissions incorrect

**Fix:**
1. Re-run installer: `sudo ./install.sh`
2. Ensure permissions: `sudo chmod 0440 /etc/sudoers.d/hailo-web-portal-systemctl`

## Ollama start blocked

**Reason:**
- Other Hailo services are running and Ollama requires exclusive access

**Fix:**
1. Stop other services from the Service Control tab
2. Start `hailo-ollama` again

## UI loads but requests fail

**Diagnostic:**
```bash
curl http://localhost:11435/health
curl http://localhost:11436/health
```

**Likely causes:**
- Target service is stopped
- Service port changed from defaults

**Fix:**
1. Start the service
2. Update the service port in its config and restart

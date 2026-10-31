# Troubleshooting

- **Service fails immediately:** check `systemctl status hailo-audio` and
  `journalctl -u hailo-audio -n 100`. The YamNet HEF and class map must exist
  under `/var/lib/hailo-audio/resources/`.
- **Device manager socket denied/missing:** verify `hailo-device-manager` is
  active and that `hailo-audio` belongs to `hailo-device-mgr`.
- **`/ready` returns 503:** inspect the service journal for HEF load errors
  and confirm the installed HailoRT/firmware and HEF compiler versions are
  compatible.
- **HTTP 400 on upload:** use an uncompressed PCM WAV under 25 MiB and 60
  seconds. Compressed WAV/MP3 is not accepted.
- **No event predictions:** check that the uploaded clip contains audible
  content; silence still produces ranked classes and is not an API failure.

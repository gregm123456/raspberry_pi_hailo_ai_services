# Hailo Super-Resolution Troubleshooting

## Service health

```bash
systemctl status hailo-super-resolution
curl -fsS http://127.0.0.1:11442/health
curl -fsS http://127.0.0.1:11442/health/ready
journalctl -u hailo-super-resolution -n 100 --no-pager
```

`/health/ready` checks the Device Manager socket but does not load the SPANF
model. The first inference loads the HEF.

## Device Manager unavailable

Check `hailo-device-manager.service` and `/run/hailo/device.sock`. The service
account must be a member of `hailo-device-mgr`; the installer configures this.

## HEF permission denied

The Device Manager process opens the HEF, so it needs read/traverse access even
though the API process can read it. Re-run the installer to restore the shared
permissions, then verify:

```bash
namei -l /var/lib/hailo-super-resolution/models/spanf_x4.hef
sudo -u hailo-device-mgr test -r /var/lib/hailo-super-resolution/models/spanf_x4.hef
```

The state/model directories should be `root:hailo-device-mgr` mode `0750`, and
the HEF should be `root:hailo-device-mgr` mode `0640`.

## Resource exhaustion

Device Manager uses its LRU policy when another network cannot fit. A SPANF
load may evict an older cached network; services reload their models on their
next inference. Check the Device Manager status endpoint and logs if this
happens:

```bash
curl -fsS http://127.0.0.1:5099/v1/device/status
journalctl -u hailo-device-manager -n 100 --no-pager
```

## Request rejected

The input must be a valid base64 image data URI and no more than 4,000,000
pixels. Resize or crop larger images before uploading. The service preserves
aspect ratio; it does not stretch non-square images to the model's square
input.

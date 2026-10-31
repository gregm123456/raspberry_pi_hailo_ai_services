# Hailo Audio Classification (YamNet)

A small REST service for classifying short PCM WAV clips with the Hailo-10H
YamNet HEF. It uses the device manager, accepts mono or multichannel WAV, and
returns the highest-scoring AudioSet events.

## Install

From the repository root, initialize the Model Zoo submodule if needed, then
run `sudo ./system_services/hailo-audio/install.sh`. The installer fetches the
public Hailo-10H YamNet HEF compiled for HailoRT 5.5.0; no Developer Zone
login is required. The model's Apache-2.0 class map is copied from the pinned
Model Zoo submodule.

The service requires the `hailo-device-manager` service and uses port 11441.
It is managed with `systemctl status|restart hailo-audio` and logs to journald.
The installer creates an isolated virtual environment; the Audio service is a
device-manager client and does not install or open its own HailoRT runtime.

For any other project that directly imports `hailo_platform`, create a
project-specific virtual environment and install the HailoRT wheel matching
the system runtime. Do not install HailoRT into system Python or use
`--system-site-packages`; see the repository's
[AI HAT+ 2 setup guide](../../reference_documentation/system_setup.md).

## API

See [API_SPEC.md](./API_SPEC.md). Supported uploads are uncompressed PCM WAV,
up to 60 seconds and 25 MiB. Audio is downmixed and resampled to 16 kHz before
YamNet's 96-frame log-mel inputs are generated.

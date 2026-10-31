# Architecture

`hailo-audio` owns WAV validation and YamNet feature preparation, but it does
not open the Hailo device directly. It sends fixed-shape log-mel tensors to
`hailo-device-manager`, which serializes HailoRT operations and returns the
521 model scores. The host converts logits to sigmoid scores and averages
scores across 0.96-second windows before selecting the top classes.

Input contract: PCM WAV -> mono float waveform -> 16 kHz -> 400-sample Hann
STFT windows at 160-sample hops -> 64 HTK mel bands (125-7500 Hz) -> log
magnitude -> `(96, 64, 1)` patches. Files shorter than one patch are zero
padded; longer files are evaluated with a 48-frame hop.

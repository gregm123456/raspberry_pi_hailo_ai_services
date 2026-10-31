# Hailo Super-Resolution Architecture

The service is an asynchronous HTTP wrapper around the v5.5.0 Hailo-10H
`spanf_x4` HEF. It uses `HailoDeviceClient` to send tensors to
`hailo-device-manager`; it does not open a HailoRT device itself.

1. Decode and validate the uploaded image, rejecting inputs above 4,000,000
   pixels.
2. Convert to RGB and split into 512x512 tiles with a 64-pixel overlap. Smaller
   edge tiles are padded by reflection (or edge replication for a one-pixel
   dimension).
3. Run each tile through the generic tensor handler using UINT8 input and
   output formats. The UINT8 response keeps the base64-framed manager message
   below its 64 MiB limit; the client allows 24 MiB for the 2048x2048x3 output.
4. Blend overlapping output areas and crop to the exact 4x dimensions of the
   original image. The accumulator uses bounded integer weights to limit
   transient RAM use.
5. Encode the final image as JPEG and return it with dimensions, tile count,
   and elapsed time.

The API serializes inference requests so concurrent uploads cannot multiply
the image-buffer memory footprint. The HEF remains cached by Device Manager
after first use and is subject to its normal least-recently-used capacity
policy.

The API binds to loopback by default because it has no authentication and
handles user-provided images. The portal accesses it on the same host.

# Whisper Upload Compatibility Plan

## Objective

Ensure the Hailo Whisper service remains strictly compatible with the OpenAI Whisper API, while clarifying and improving client usability for audio uploads—especially for scenarios where a local file path is not available. Address the handling of optional fields (`prompt`, `temperature`) to avoid misleading clients.

---

## Background

- The current API only accepts `multipart/form-data` uploads with a `file` field, matching the OpenAI Whisper API.
- Raw audio payloads (e.g., `Content-Type: audio/wav` with the audio as the body) are not supported and return an error.
- Some clients (e.g., browser, mobile, streaming pipelines) may not have a local file path, but can still use multipart uploads with in-memory blobs or streams.
- The API spec lists `prompt` and `temperature` as optional fields, but the backend handler does not currently process or pass them to the model runner.

---

## Plan

### 1. Confirm Handler and Model Runner Support
- Review `APIHandler.transcriptions` in `hailo_whisper_server.py` to confirm which fields are parsed and passed to the model runner.
- Check if the underlying model runner (Whisper implementation) supports `prompt` and `temperature`.
- If supported, wire these fields through the handler; if not, update documentation to mark them as unsupported.

### 2. Strict Content-Type Enforcement
- Add a check in the handler to ensure only `multipart/form-data` requests are accepted.
- For non-multipart requests, return a clear `415 Unsupported Media Type` error with a message referencing OpenAI Whisper compatibility.
- Update error handling to provide actionable feedback for clients.

### 3. Documentation Improvements
- Update `API_SPEC.md` and `README.md` to:
  - Emphasize strict OpenAI Whisper compatibility and the requirement for `multipart/form-data`.
  - Add examples for streaming multipart uploads (e.g., using `curl` with stdin, or browser/JS FormData with blobs) to show how to upload audio without a local file path.
  - Clearly document which optional fields are supported and which are not.
- If `prompt` and `temperature` are not supported, mark them as reserved/unsupported in the spec.

### 4. Test Coverage
- Add or update tests in `tests/test_hailo_whisper_service.py` to:
  - Verify that non-multipart requests return a 415 error with a clear message.
  - Test multipart uploads using in-memory data (not just file paths).
  - (If implemented) Test that `prompt` and `temperature` are correctly handled or rejected.

### 5. Verification
- Confirm that standard OpenAI Whisper API clients (Python SDK, curl, browser FormData) work as expected.
- Confirm that streaming multipart uploads (stdin, blob) work without requiring a file on disk.
- Confirm that error messages are clear and actionable for unsupported upload types.
- Confirm that documentation is accurate and unambiguous.

---

## Decisions
- **Multipart/form-data only:** Strictly follow OpenAI Whisper API for `/v1/audio/transcriptions`.
- **Raw audio body:** Not supported unless the OpenAI Whisper API adds it in the future.
- **Optional fields:** Only support `prompt` and `temperature` if the backend model runner supports them; otherwise, mark as unsupported in docs.

---

## Rationale
- Maximizes compatibility with existing Whisper clients and SDKs.
- Avoids confusion for users expecting OpenAI Whisper API behavior.
- Provides clear guidance for clients that cannot use file paths, without breaking compatibility.
- Ensures documentation and error handling are accurate and user-friendly.

---

## Next Steps
1. Review and update handler code for field support and error handling.
2. Update documentation and add streaming multipart examples.
3. Improve test coverage for upload scenarios and error cases.
4. Verify with standard clients and streaming scenarios.
5. Maintain strict compatibility unless the upstream Whisper API changes.

import io
import wave

import numpy as np
import pytest

from hailo_audio_server import decode_pcm_wav, waveform_to_log_mel_patches


def make_wav(samples, sample_rate=16000, channels=1, sample_width=2):
    samples = np.asarray(samples, dtype=np.float32)
    if channels == 2:
        samples = np.repeat(samples[:, None], 2, axis=1)
    if sample_width == 2:
        raw = np.clip(samples * 32767, -32768, 32767).astype("<i2").tobytes()
    else:
        raise AssertionError("test helper supports 16-bit PCM only")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(raw)
    return buffer.getvalue()


def test_decode_mono_wav_and_feature_shape():
    audio = make_wav(np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000))
    waveform, duration = decode_pcm_wav(audio)
    patches = waveform_to_log_mel_patches(waveform)
    assert duration == pytest.approx(1.0)
    assert patches.shape == (1, 96, 64, 1)
    assert patches.dtype == np.float32
    assert np.isfinite(patches).all()


def test_decode_downmixes_and_resamples_stereo_audio():
    samples = np.zeros(44100, dtype=np.float32)
    audio = make_wav(samples, sample_rate=44100, channels=2)
    waveform, duration = decode_pcm_wav(audio)
    assert duration == pytest.approx(1.0)
    assert waveform.shape == (16000,)
    assert np.max(np.abs(waveform)) == 0


def test_short_audio_is_padded_to_one_patch():
    patches = waveform_to_log_mel_patches(np.zeros(100, dtype=np.float32))
    assert patches.shape == (1, 96, 64, 1)


def test_invalid_wav_is_rejected():
    with pytest.raises(ValueError, match="Invalid WAV"):
        decode_pcm_wav(b"not a wav")


def test_classify_returns_sorted_audio_events():
    import asyncio
    import base64
    from hailo_audio_server import YamNetService

    class FakeClient:
        async def infer(self, model_path, payload, model_type):
            logits = np.full((521,), -10.0, dtype=np.float32)
            logits[7] = 4.0
            logits[11] = 2.0
            raw = logits.tobytes()
            return {"result": {
                "dtype": "float32",
                "shape": [521],
                "data_b64": base64.b64encode(raw).decode("ascii"),
            }}

    service = YamNetService()
    service.client = FakeClient()
    service.labels = [f"class {i}" for i in range(521)]
    service.is_loaded = True
    audio = make_wav(np.zeros(16000, dtype=np.float32))
    result = asyncio.run(service.classify(audio, top_k=2))
    assert [item["class_id"] for item in result["predictions"]] == [7, 11]
    assert result["predictions"][0]["score"] > result["predictions"][1]["score"]

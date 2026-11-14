"""Enterprise voice reliability tests covering TTS fallback, circuit breaker,
DRM clock-skew recovery, STT fallback, non-speech tag stripping, MIME sniffing,
and concurrent filename collision prevention."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import tools.transcription_tools as stt_mod
import tools.tts_tool as tts_mod
import tools.voice_mode as voice_mode_mod
from hermes_cli.web_server import _detect_audio_mime_type


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    tts_mod._reset_tts_circuit_breaker()
    yield
    tts_mod._reset_tts_circuit_breaker()


def test_edge_tts_drm_clock_skew_recovery_and_retry(tmp_path):
    """_generate_edge_tts should sync DRM clock skew on 403 and succeed on retry."""
    out_file = tmp_path / "edge_retry.mp3"
    attempts = {"count": 0}

    class FakeHandshakeError(Exception):
        status = 403

    class FakeCommunicate:
        def __init__(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs

        async def save(self, path):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise FakeHandshakeError("403, message='Invalid response status'")
            Path(path).write_bytes(b"ID3" + b"\x00" * 256)

    fake_drm = MagicMock()
    fake_edge_mod = MagicMock()
    fake_edge_mod.Communicate = FakeCommunicate
    fake_edge_mod.drm.DRM = fake_drm

    with patch.object(tts_mod, "_import_edge_tts", return_value=fake_edge_mod):
        result_path = asyncio.run(
            tts_mod._ORIG_GENERATE_EDGE_TTS("Bonjour tout le monde", str(out_file), {})
        )

    assert result_path == str(out_file)
    assert attempts["count"] == 2
    assert fake_drm.handle_client_response_error.call_count == 1
    assert out_file.exists()


def test_tts_multi_provider_fallback_and_circuit_breaker(tmp_path, monkeypatch):
    """When primary provider (edge) fails with 403, text_to_speech_tool trips the
    circuit breaker and automatically fails over to the next available provider."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-key")
    monkeypatch.setattr(tts_mod, "_load_tts_config", lambda: {"provider": "edge"})
    monkeypatch.setattr(tts_mod, "_import_edge_tts", lambda: MagicMock())

    edge_calls = {"count": 0}
    eleven_calls = {"count": 0}

    def failing_edge_sync(text, output_path, config):
        edge_calls["count"] += 1
        raise RuntimeError("Edge TTS failed: 403, message='Invalid response status'")

    def succeeding_eleven(text, output_path, config):
        eleven_calls["count"] += 1
        Path(output_path).write_bytes(b"ID3" + b"\x00" * 512)
        return output_path

    monkeypatch.setattr(tts_mod, "_run_edge_tts_sync", failing_edge_sync)
    monkeypatch.setattr(tts_mod, "_generate_elevenlabs", succeeding_eleven)

    out1 = tmp_path / "turn1.mp3"
    raw1 = tts_mod.text_to_speech_tool(
        text="First turn response.",
        output_path=str(out1),
        allow_fallback=True,
    )
    data1 = json.loads(raw1)
    assert data1["success"] is True
    assert data1["provider"] == "elevenlabs"
    assert data1["fallback_from"] == "edge"
    assert edge_calls["count"] == 1
    assert eleven_calls["count"] == 1
    assert tts_mod._is_tts_provider_circuit_open("edge") is True

    # Second turn should fast-bypass edge because its circuit breaker is open
    out2 = tmp_path / "turn2.mp3"
    raw2 = tts_mod.text_to_speech_tool(
        text="Second turn response.",
        output_path=str(out2),
        allow_fallback=True,
    )
    data2 = json.loads(raw2)
    assert data2["success"] is True
    assert data2["provider"] == "elevenlabs"
    assert edge_calls["count"] == 1  # Not called again while circuit is open!
    assert eleven_calls["count"] == 2


def test_tts_system_offline_fallback(tmp_path, monkeypatch):
    """When cloud providers are unconfigured and edge fails, system TTS acts as last-resort fallback."""
    for env_key in (
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "MINIMAX_API_KEY",
        "MISTRAL_API_KEY",
    ):
        monkeypatch.delenv(env_key, raising=False)

    monkeypatch.setattr(tts_mod, "_load_tts_config", lambda: {"provider": "edge"})
    monkeypatch.setattr(tts_mod, "_import_edge_tts", lambda: MagicMock())

    def failing_edge_sync(text, output_path, config):
        raise RuntimeError("Edge TTS failed: 403")

    monkeypatch.setattr(tts_mod, "_run_edge_tts_sync", failing_edge_sync)
    monkeypatch.setattr(tts_mod, "_check_piper_available", lambda: False)
    monkeypatch.setattr(tts_mod, "_check_kittentts_available", lambda: False)
    monkeypatch.setattr(tts_mod, "_check_neutts_available", lambda: False)
    monkeypatch.setattr(tts_mod, "_check_system_tts_available", lambda: True)

    def fake_system_tts(text, output_path, config):
        wav_path = str(Path(output_path).with_suffix(".wav"))
        Path(wav_path).write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)
        return wav_path

    monkeypatch.setattr(tts_mod, "_generate_system_tts", fake_system_tts)

    out_path = tmp_path / "offline.mp3"
    raw = tts_mod.text_to_speech_tool(
        text="Offline fallback test.",
        output_path=str(out_path),
        allow_fallback=True,
    )
    data = json.loads(raw)
    assert data["success"] is True
    assert data["provider"] == "system"
    assert data["file_path"].endswith(".wav")
    assert Path(data["file_path"]).exists()


def test_detect_audio_mime_type_from_magic_bytes():
    """_detect_audio_mime_type inspects container headers before falling back to extension."""
    wav_bytes = b"RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00"
    ogg_bytes = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
    flac_bytes = b"fLaC\x00\x00\x00\x22\x10\x00\x10\x00"
    mp3_id3_bytes = b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00"
    mp3_sync_bytes = b"\xff\xfb\x90\x64\x00\x00\x00\x00\x00\x00\x00\x00"

    assert _detect_audio_mime_type(wav_bytes, "/tmp/out.mp3") == "audio/wav"
    assert _detect_audio_mime_type(ogg_bytes, "/tmp/out.mp3") == "audio/ogg"
    assert _detect_audio_mime_type(flac_bytes, "/tmp/out.mp3") == "audio/flac"
    assert _detect_audio_mime_type(mp3_id3_bytes, "/tmp/out.wav") == "audio/mpeg"
    assert _detect_audio_mime_type(mp3_sync_bytes, "/tmp/out.bin") == "audio/mpeg"


def test_strip_non_speech_audio_tags_and_hallucinations():
    """Verify ElevenLabs Scribe / Whisper non-speech tags and multilingual hallucinations are filtered."""
    assert voice_mode_mod.strip_non_speech_audio_tags("(background noise)") == ""
    assert voice_mode_mod.strip_non_speech_audio_tags("[music] (clicking) *sigh*") == ""
    assert (
        voice_mode_mod.strip_non_speech_audio_tags(
            "(throat clearing) Bonjour, comment allez-vous ? (breathing)"
        )
        == "Bonjour, comment allez-vous ?"
    )

    assert voice_mode_mod.is_whisper_hallucination("(background noise)") is True
    assert voice_mode_mod.is_whisper_hallucination("[BLANK_AUDIO]") is True
    assert voice_mode_mod.is_whisper_hallucination("Merci.") is True
    assert voice_mode_mod.is_whisper_hallucination("Merci d'avoir regardé!") is True
    assert voice_mode_mod.is_whisper_hallucination("Thank you for watching.") is True
    assert voice_mode_mod.is_whisper_hallucination("...") is True
    assert voice_mode_mod.is_whisper_hallucination("Can you open the project roadmap?") is False


def test_transcribe_recording_treats_empty_transcript_as_filtered_silence(tmp_path, monkeypatch):
    """Provider 'empty transcript' error or non-speech tag should return filtered=True, not an error."""
    wav_file = tmp_path / "quiet.wav"
    wav_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 32)

    monkeypatch.setattr(
        "tools.transcription_tools.transcribe_audio",
        lambda file_path, model=None, allow_fallback=False: {
            "success": False,
            "error": "ElevenLabs Scribe returned empty transcript.",
        },
    )
    res_empty = voice_mode_mod.transcribe_recording(str(wav_file))
    assert res_empty["success"] is True
    assert res_empty["transcript"] == ""
    assert res_empty.get("filtered") is True

    monkeypatch.setattr(
        "tools.transcription_tools.transcribe_audio",
        lambda file_path, model=None, allow_fallback=False: {
            "success": True,
            "transcript": "(background noise) [clicking]",
        },
    )
    res_noise = voice_mode_mod.transcribe_recording(str(wav_file))
    assert res_noise["success"] is True
    assert res_noise["transcript"] == ""
    assert res_noise.get("filtered") is True


def test_stt_runtime_fallback_and_local_privacy_guard(tmp_path, monkeypatch):
    """transcribe_audio(allow_fallback=True) fails over across cloud providers but never leaks local STT to cloud."""
    audio_file = tmp_path / "speech.wav"
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 64)

    monkeypatch.setattr(stt_mod, "_load_stt_config", lambda: {"enabled": True})
    monkeypatch.setattr(
        stt_mod,
        "_get_provider",
        lambda cfg=None: "elevenlabs",
    )
    monkeypatch.setattr(
        stt_mod,
        "_get_available_fallback_stt_providers",
        lambda primary, cfg=None: ["groq"],
    )
    monkeypatch.setattr(
        stt_mod,
        "_transcribe_elevenlabs",
        lambda path, model: {"success": False, "transcript": "", "error": "ElevenLabs HTTP 503"},
    )
    monkeypatch.setattr(
        stt_mod,
        "_transcribe_groq",
        lambda path, model: {
            "success": True,
            "transcript": "Hello from Groq fallback",
            "provider": "groq",
        },
    )

    res = stt_mod.transcribe_audio(str(audio_file), allow_fallback=True)
    assert res["success"] is True
    assert res["transcript"] == "Hello from Groq fallback"
    assert res["provider"] == "groq"
    assert res["fallback_from"] == "elevenlabs"

    # Privacy guard: when primary provider is 'local', fallback list must be empty
    monkeypatch.undo()
    assert stt_mod._get_available_fallback_stt_providers("local", {}) == []

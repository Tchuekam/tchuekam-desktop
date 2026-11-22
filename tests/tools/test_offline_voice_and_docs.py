"""Tests for offline Kokoro TTS, local Whisper PCM STT, read_document, and JARVIS /ws/voice."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def test_read_document_handles_docx_xlsx_rtf_csv_pdf(tmp_path):
    from tools.local_document_tool import read_document

    # 1. CSV
    csv_path = tmp_path / "investors.csv"
    csv_path.write_text("Name,Stage\nAcme Ventures,Seed\n", encoding="utf-8")
    res_csv = json.loads(read_document(str(csv_path)))
    assert res_csv["success"] is True
    assert "Acme Ventures" in res_csv["content"]

    # 2. RTF
    rtf_path = tmp_path / "affirmation.rtf"
    rtf_path.write_text(r"{\rtf1\ansi {\fonttbl{\f0 Arial;}} Hello TchuekaM Offline \par Second Line}", encoding="utf-8")
    res_rtf = json.loads(read_document(str(rtf_path)))
    assert res_rtf["success"] is True
    assert "Hello TchuekaM Offline" in res_rtf["content"]

    # 3. DOCX (uses python-docx when installed, pure-stdlib OOXML otherwise)
    from agent.self_consciousness import write_minimal_docx

    docx_path = tmp_path / "pitch.docx"
    write_minimal_docx(docx_path, "Giantech Empire Investor Pitch Deck", "Executive summary paragraph")
    res_docx = json.loads(read_document(str(docx_path)))
    assert res_docx["success"] is True
    assert "Giantech Empire Investor Pitch Deck" in res_docx["content"]

    # 4. Minimal valid XLSX (tests pure-stdlib XML reader as well)
    xlsx_path = tmp_path / "investors.xlsx"
    with zipfile.ZipFile(xlsx_path, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>',
        )
        zf.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Seed" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        zf.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>FundName</t></si><si><t>Horizon Capital</t></si></sst>',
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c></row><row r="2"><c r="A2" t="s"><v>1</v></c></row></sheetData></worksheet>',
        )
    res_xlsx = json.loads(read_document(str(xlsx_path)))
    assert res_xlsx["success"] is True
    assert "Horizon Capital" in res_xlsx["content"]


def test_jarvis_text_processor_and_turn_detector():
    import numpy as np
    from agent.jarvis_voice.text_processor import StreamingClauseChunker, sanitize_text_for_speech
    from agent.jarvis_voice.turn_detector import AdaptiveTurnDetector

    assert sanitize_text_for_speech("<think>internal</think>Hello **boss**! `ls -la` https://example.com") == "Hello boss! ls -la"

    chunker = StreamingClauseChunker(min_clause_chars=12)
    chunks = chunker.push("Systems are nominal. ")
    chunks.extend(chunker.push("All local models ready"))
    tail = chunker.flush()
    assert chunks[0] == "Systems are nominal."
    assert tail == "All local models ready"

    det = AdaptiveTurnDetector(speech_rms_threshold=0.02, barge_in_rms_threshold=0.04, barge_in_min_frames=2, silence_commit_seconds=0.3)
    speech_pcm = (np.ones(1600, dtype=np.int16) * 6000).tobytes()
    ev1 = det.feed_pcm(speech_pcm, assistant_speaking=True, now=1.0)
    ev2 = det.feed_pcm(speech_pcm, assistant_speaking=True, now=1.1)
    assert ev1.barge_in is False
    assert ev2.barge_in is True

    det.reset()
    det.feed_pcm(speech_pcm, assistant_speaking=False, now=2.0)
    det.feed_pcm(speech_pcm, assistant_speaking=False, now=2.1)
    silence_pcm = (np.zeros(1600, dtype=np.int16)).tobytes()
    ev_commit = det.feed_pcm(silence_pcm, assistant_speaking=False, now=2.6)
    assert ev_commit.commit_utterance is True
    assert det.has_pending_audio() is True


def test_kokoro_bilingual_selection_and_zero_byte_cleanup(tmp_path):
    from tools.tts_tool import (
        BUILTIN_TTS_PROVIDERS,
        _cleanup_empty_audio_file,
        _pick_kokoro_voice_and_lang,
    )

    assert "kokoro" in BUILTIN_TTS_PROVIDERS

    class _FakeKokoro:
        def get_voices(self):
            return ["bm_george", "ff_siwis", "af_heart"]

    v_en, l_en, _ = _pick_kokoro_voice_and_lang("All local systems operational.", {}, _FakeKokoro())
    assert v_en == "bm_george" and l_en == "en-us"

    v_fr, l_fr, _ = _pick_kokoro_voice_and_lang("Bonjour, comment allez-vous aujourd'hui ?", {}, _FakeKokoro())
    assert v_fr == "ff_siwis" and l_fr == "fr-fr"

    empty_file = tmp_path / "broken.mp3"
    empty_file.write_bytes(b"")
    _cleanup_empty_audio_file(str(empty_file))
    assert not empty_file.exists()


def test_web_server_intelligence_endpoints_and_voice_ws(monkeypatch):
    from hermes_cli import web_server

    monkeypatch.setattr(web_server.app.state, "auth_required", False, raising=False)
    monkeypatch.setattr(web_server, "_ws_auth_ok", lambda ws: True)
    monkeypatch.setattr(web_server, "_ws_request_is_allowed", lambda ws: True)

    client = TestClient(web_server.app)
    headers = {"Authorization": f"Bearer {web_server._SESSION_TOKEN}"}

    r_status = client.get("/api/intelligence/status?probe=false", headers=headers)
    assert r_status.status_code == 200
    body = r_status.json()
    assert "mode" in body
    assert "local_runtime" in body
    assert "voice" in body

    r_mode = client.post(
        "/api/intelligence/mode",
        json={"mode": "hybrid", "persist": False},
        headers=headers,
    )
    assert r_mode.status_code == 200
    assert r_mode.json()["mode"] == "hybrid"

    with client.websocket_connect("/api/ws/voice?session_id=test-voice-1") as ws:
        ready = json.loads(ws.receive_text())
        assert ready["type"] == "voice_ready"
        assert ready["session_id"] == "test-voice-1"
        state_msg = json.loads(ws.receive_text())
        assert state_msg["type"] == "state"

        ws.send_text(json.dumps({"type": "ping"}))
        pong = json.loads(ws.receive_text())
        assert pong["type"] == "pong"

        ws.send_text(json.dumps({"type": "config", "language": "fr", "barge_in": True}))
        cfg_ack = json.loads(ws.receive_text())
        assert cfg_ack["type"] == "config_ack"
        assert cfg_ack["language"] == "fr"

        ws.send_text(json.dumps({"type": "interrupt", "reason": "test_barge_in"}))
        clear_msg = json.loads(ws.receive_text())
        assert clear_msg["type"] == "tts_clear"
        assert clear_msg["reason"] == "test_barge_in"

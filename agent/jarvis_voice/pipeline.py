"""Full-duplex real-time voice session orchestrator for TchuekaM (JARVIS mode).

Bridges incoming 16kHz Int16 PCM WebSocket frames, adaptive turn detection,
local faster-whisper STT, MbowaGPT / hybrid AIAgent streaming + SessionDB
continuity, clause-level chunking, and 24kHz Kokoro-ONNX neural TTS streaming
with instant generation-gated barge-in cancellation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from agent.jarvis_voice.text_processor import StreamingClauseChunker, sanitize_text_for_speech
from agent.jarvis_voice.turn_detector import AdaptiveTurnDetector

logger = logging.getLogger(__name__)


class JarvisVoiceSession:
    """Manages one duplex WebSocket voice session with shared agent/DB state."""

    def __init__(self, ws: Any, *, session_id: Optional[str] = None) -> None:
        self.ws = ws
        self.loop = asyncio.get_running_loop()
        self.session_id = (session_id or "").strip() or f"voice-{uuid.uuid4().hex[:10]}"
        self.language: str = "auto"
        self.voice: str = ""
        self.barge_in_enabled: bool = True

        self.turn_detector = AdaptiveTurnDetector()
        self._generation_id: int = 0
        self._state: str = "listening"
        self._speaking: bool = False
        self._closed: bool = False

        self._active_agent: Any = None
        self._agent_lock = threading.Lock()
        self._active_turn_task: Optional[asyncio.Task[Any]] = None
        self._send_lock = asyncio.Lock()
        self._unsub_connectivity: Optional[Callable[[], None]] = None

    async def send_json(self, payload: Dict[str, Any]) -> bool:
        if self._closed:
            return False
        try:
            text = json.dumps(payload, ensure_ascii=False)
            async with self._send_lock:
                await self.ws.send_text(text)
            return True
        except Exception as exc:
            logger.debug("Voice WS send_json failed: %s", exc)
            return False

    async def send_bytes(self, data: bytes) -> bool:
        if self._closed or not data:
            return False
        try:
            async with self._send_lock:
                await self.ws.send_bytes(data)
            return True
        except Exception as exc:
            logger.debug("Voice WS send_bytes failed: %s", exc)
            return False

    async def _set_state(self, state: str) -> None:
        self._state = state
        await self.send_json({"type": "state", "state": state})

    def _on_connectivity_change(self, snapshot: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.send_json({"type": "intelligence", **snapshot}))
            )
        except Exception:
            pass

    async def initialize(self) -> None:
        from agent.connectivity import get_connectivity_monitor
        from tools.tts_tool import _check_kokoro_available

        mon = get_connectivity_monitor()
        self._unsub_connectivity = mon.subscribe(self._on_connectivity_change)
        status = mon.get_status(probe_if_stale=False)
        await self.send_json({
            "type": "voice_ready",
            "session_id": self.session_id,
            "sample_rate_in": 16000,
            "sample_rate_out": 24000,
            "tts_provider": "kokoro" if _check_kokoro_available() else "fallback",
            "stt_provider": "local",
            "intelligence": status,
        })
        await self._set_state("listening")

    def interrupt(self, reason: str = "barge_in") -> int:
        """Increment generation counter, flush TTS, and interrupt running agent."""
        self._generation_id += 1
        gen = self._generation_id
        self._speaking = False
        with self._agent_lock:
            ag = self._active_agent
        if ag is not None:
            try:
                ag.interrupt(reason)
            except Exception:
                pass
        return gen

    async def handle_interrupt(self, reason: str = "barge_in") -> None:
        gen = self.interrupt(reason=reason)
        if self._active_turn_task is not None and not self._active_turn_task.done():
            self._active_turn_task.cancel()
        await self.send_json({"type": "tts_clear", "generation_id": gen, "reason": reason})
        await self._set_state("listening")

    async def handle_control(self, msg: Dict[str, Any]) -> None:
        mtype = str(msg.get("type") or "").strip().lower()
        if mtype == "ping":
            await self.send_json({"type": "pong", "ts": time.time()})
            return

        if mtype == "config":
            if msg.get("session_id"):
                self.session_id = str(msg["session_id"]).strip()
            if msg.get("language"):
                self.language = str(msg["language"]).strip().lower()
            if msg.get("voice") is not None:
                self.voice = str(msg["voice"]).strip()
            if "barge_in" in msg:
                self.barge_in_enabled = bool(msg["barge_in"])
            await self.send_json({
                "type": "config_ack",
                "session_id": self.session_id,
                "language": self.language,
                "barge_in": self.barge_in_enabled,
            })
            return

        if mtype == "interrupt":
            await self.handle_interrupt(reason=str(msg.get("reason") or "client_interrupt"))
            return

        if mtype == "commit":
            if self.turn_detector.has_pending_audio():
                pcm = self.turn_detector.pop_audio()
                await self._dispatch_audio_turn(pcm)
            return

        if mtype == "text_turn":
            text = str(msg.get("text") or "").strip()
            if text:
                await self._dispatch_text_turn(text)
            return

    async def handle_audio_bytes(self, pcm_bytes: bytes) -> None:
        if self._closed or not pcm_bytes:
            return
        ev = self.turn_detector.feed_pcm(pcm_bytes, assistant_speaking=self._speaking)
        if ev.barge_in and self.barge_in_enabled:
            await self.handle_interrupt(reason="voice_barge_in")
            return
        if ev.commit_utterance and self.turn_detector.has_pending_audio():
            pcm = self.turn_detector.pop_audio()
            await self._dispatch_audio_turn(pcm)

    async def _dispatch_audio_turn(self, pcm_bytes: bytes) -> None:
        # Cancel stale generation cleanly before starting new utterance turn
        if self._active_turn_task is not None and not self._active_turn_task.done():
            await self.handle_interrupt(reason="new_utterance")

        gen = self._generation_id + 1
        self._generation_id = gen
        self._active_turn_task = asyncio.create_task(self._run_audio_turn(pcm_bytes, gen))

    async def _dispatch_text_turn(self, text: str) -> None:
        if self._active_turn_task is not None and not self._active_turn_task.done():
            await self.handle_interrupt(reason="new_text_turn")
        gen = self._generation_id + 1
        self._generation_id = gen
        self._active_turn_task = asyncio.create_task(self._run_text_turn(text, gen))

    async def _run_audio_turn(self, pcm_bytes: bytes, gen: int) -> None:
        try:
            await self._set_state("transcribing")
            from tools.transcription_tools import transcribe_pcm_bytes

            lang = None if self.language in {"", "auto"} else self.language
            stt_res = await asyncio.to_thread(transcribe_pcm_bytes, pcm_bytes, lang)
            if gen != self._generation_id or self._closed:
                return
            if not stt_res.get("success"):
                err = str(stt_res.get("error") or "Transcription failed")
                if "empty transcript" not in err.lower():
                    await self.send_json({"type": "error", "error": err})
                await self._set_state("listening")
                return

            transcript = str(stt_res.get("transcript") or "").strip()
            if not transcript:
                await self._set_state("listening")
                return

            await self.send_json({
                "type": "transcript_final",
                "text": transcript,
                "provider": stt_res.get("provider", "local"),
                "generation_id": gen,
            })
            await self._run_text_turn(transcript, gen)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.exception("Voice audio turn failed")
            await self.send_json({"type": "error", "error": str(exc)})
            await self._set_state("listening")

    def _load_or_make_agent_and_history(self) -> tuple[Any, List[Dict[str, Any]]]:
        """Load shared history and agent bound to session_id cleanly."""
        history: List[Dict[str, Any]] = []
        agent = None
        session_entry: Optional[Dict[str, Any]] = None

        try:
            from tui_gateway import server as gw_server

            sessions = getattr(gw_server, "_sessions", {})
            entry = sessions.get(self.session_id) if isinstance(sessions, dict) else None
            if not isinstance(entry, dict) and isinstance(sessions, dict):
                # Also match by persisted session_key when UI passes DB session_id
                for cand in sessions.values():
                    if isinstance(cand, dict) and cand.get("session_key") == self.session_id:
                        entry = cand
                        break
            if isinstance(entry, dict):
                session_entry = entry
                lock = entry.get("history_lock")
                if lock is not None:
                    with lock:
                        entry_history = entry.get("history")
                        if isinstance(entry_history, list):
                            history = list(entry_history)

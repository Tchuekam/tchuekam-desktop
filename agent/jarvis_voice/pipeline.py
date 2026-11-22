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
                else:
                    entry_history = entry.get("history")
                    if isinstance(entry_history, list):
                        history = list(entry_history)
                if entry.get("agent") is not None:
                    agent = entry.get("agent")
        except Exception:
            pass

        if not history:
            try:
                from hermes_state import SessionDB

                db = SessionDB()
                try:
                    raw_msgs = db.get_messages_as_conversation(self.session_id)
                    if isinstance(raw_msgs, list):
                        for m in raw_msgs:
                            if isinstance(m, dict) and m.get("role") in {"user", "assistant", "tool"}:
                                history.append({
                                    "role": m["role"],
                                    "content": m.get("content") or "",
                                })
                finally:
                    db.close()
            except Exception:
                pass

        if agent is None:
            try:
                from tui_gateway import server as gw_server

                key = (
                    str(session_entry.get("session_key") or self.session_id)
                    if isinstance(session_entry, dict)
                    else self.session_id
                )
                agent = gw_server._make_agent(self.session_id, key, session_id=key)
            except Exception:
                from run_agent import AIAgent

                agent = AIAgent(quiet_mode=True, session_id=self.session_id, platform="desktop")

        return agent, history

    async def _tts_consumer(self, clause_queue: asyncio.Queue[Optional[str]], gen: int) -> None:
        from tools.tts_tool import stream_kokoro_pcm, text_to_speech_tool

        tts_started = False
        try:
            while True:
                clause = await clause_queue.get()
                if clause is None:
                    break
                if gen != self._generation_id or self._closed:
                    break

                spoken = sanitize_text_for_speech(clause)
                if not spoken:
                    continue

                if not tts_started:
                    tts_started = True
                    self._speaking = True
                    await self._set_state("speaking")
                    await self.send_json({
                        "type": "tts_start",
                        "generation_id": gen,
                        "sample_rate": 24000,
                        "provider": "kokoro",
                    })

                streamed_any = False
                try:
                    tts_cfg = {"kokoro": {}}
                    if self.voice:
                        tts_cfg["kokoro"]["voice"] = self.voice
                    async for pcm_chunk, _sr in stream_kokoro_pcm(spoken, tts_config=tts_cfg):
                        if gen != self._generation_id or self._closed:
                            return
                        if pcm_chunk:
                            streamed_any = True
                            await self.send_bytes(pcm_chunk)
                except Exception as exc:
                    logger.debug("Kokoro stream failed (%s); falling back to file TTS", exc)

                if not streamed_any and gen == self._generation_id and not self._closed:
                    res_json = await asyncio.to_thread(text_to_speech_tool, spoken, None, True)
                    try:
                        res = json.loads(res_json)
                    except Exception:
                        res = {}
                    fpath = res.get("file_path")
                    if res.get("success") and fpath and os.path.isfile(fpath):
                        try:
                            pcm_fallback = _load_audio_file_as_pcm16_24k(fpath)
                            if pcm_fallback and gen == self._generation_id:
                                for off in range(0, len(pcm_fallback), 16384):
                                    if gen != self._generation_id or self._closed:
                                        return
                                    await self.send_bytes(pcm_fallback[off : off + 16384])
                        finally:
                            try:
                                os.unlink(fpath)
                            except OSError:
                                pass
        finally:
            self._speaking = False
            if tts_started and gen == self._generation_id and not self._closed:
                await self.send_json({"type": "tts_end", "generation_id": gen})

    async def _run_text_turn(self, text: str, gen: int) -> None:
        clause_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        chunker = StreamingClauseChunker()
        tts_task = asyncio.create_task(self._tts_consumer(clause_queue, gen))

        try:
            await self._set_state("thinking")
            agent, history = await asyncio.to_thread(self._load_or_make_agent_and_history)
            with self._agent_lock:
                self._active_agent = agent

            def _on_intel(payload: Dict[str, Any]) -> None:
                if gen != self._generation_id or self._closed:
                    return
                try:
                    self.loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self.send_json({"type": "intelligence", **payload}))
                    )
                except Exception:
                    pass

            agent.intelligence_callback = _on_intel

            def _on_delta(delta: str) -> None:
                if not delta or gen != self._generation_id or self._closed:
                    return
                try:
                    self.loop.call_soon_threadsafe(
                        lambda d=delta: asyncio.create_task(
                            self.send_json({"type": "assistant_delta", "delta": d, "generation_id": gen})
                        )
                    )
                    for clause in chunker.push(delta):
                        self.loop.call_soon_threadsafe(clause_queue.put_nowait, clause)
                except Exception:
                    pass

            result = await asyncio.to_thread(
                agent.run_conversation,
                user_message=text,
                conversation_history=history or None,
                stream_callback=_on_delta,
            )

            # Update shared tui_gateway history if that session exists in-memory
            try:
                from tui_gateway import server as gw_server

                sessions = getattr(gw_server, "_sessions", {})
                entry = sessions.get(self.session_id) if isinstance(sessions, dict) else None
                if not isinstance(entry, dict) and isinstance(sessions, dict):
                    for cand in sessions.values():
                        if isinstance(cand, dict) and cand.get("session_key") == self.session_id:
                            entry = cand
                            break
                if isinstance(entry, dict) and isinstance(result, dict) and isinstance(result.get("messages"), list):
                    lock = entry.get("history_lock")
                    if lock is not None:
                        with lock:
                            entry["history"] = list(result["messages"])
                    else:
                        entry["history"] = list(result["messages"])
            except Exception:
                pass

            if gen != self._generation_id or self._closed:
                return

            final_text = str((result or {}).get("final_response") or "").strip()
            tail = chunker.flush()
            if tail:
                await clause_queue.put(tail)
            elif final_text and not getattr(agent, "_current_streamed_assistant_text", ""):
                # Non-streaming path (or buffered local response): speak full response cleanly
                ns_chunker = StreamingClauseChunker()
                for clause in ns_chunker.push(final_text):
                    await clause_queue.put(clause)
                rem = ns_chunker.flush()
                if rem:
                    await clause_queue.put(rem)

            await clause_queue.put(None)
            await tts_task

            if gen == self._generation_id and not self._closed:
                route = getattr(agent, "_active_mbowagpt_route", None)
                await self.send_json({
                    "type": "assistant_final",
                    "text": final_text,
                    "generation_id": gen,
                    "model": getattr(agent, "model", ""),
                    "provider": getattr(agent, "provider", ""),
                    "specialist": getattr(route, "display_name", None),
                })
                await self._set_state("listening")

        except asyncio.CancelledError:
            await clause_queue.put(None)
            tts_task.cancel()
            return
        except Exception as exc:
            logger.exception("Voice text turn failed")
            await clause_queue.put(None)
            await self.send_json({"type": "error", "error": str(exc)})
            await self._set_state("listening")
        finally:
            with self._agent_lock:
                self._active_agent = None

    async def close(self) -> None:
        self._closed = True
        self.interrupt(reason="disconnect")
        if self._active_turn_task is not None and not self._active_turn_task.done():
            self._active_turn_task.cancel()
        if self._unsub_connectivity is not None:
            try:
                self._unsub_connectivity()
            except Exception:
                pass
            self._unsub_connectivity = None


def _load_audio_file_as_pcm16_24k(file_path: str) -> bytes:
    """Read a WAV/audio file into mono 24kHz Int16 PCM bytes cleanly."""
    try:
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(file_path, dtype="float32", always_2d=True)
        mono = data.mean(axis=1)
        if sr != 24000 and len(mono) > 1:
            target_len = max(1, int(round(len(mono) * 24000 / sr)))
            xp = np.linspace(0.0, 1.0, len(mono), dtype=np.float32)
            x_new = np.linspace(0.0, 1.0, target_len, dtype=np.float32)
            mono = np.interp(x_new, xp, mono)
        pcm16 = (np.clip(mono, -1.0, 1.0) * 32767.0).astype(np.int16)
        return pcm16.tobytes()
    except Exception:
        return b""

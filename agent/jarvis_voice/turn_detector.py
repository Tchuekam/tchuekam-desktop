"""Adaptive turn detector and PCM RMS voice activity / barge-in tracker.

Pause curve timings adapted from KoljaB/RealtimeVoiceChat ``turndetect.py``
(Apache-2.0), paired with pure-numpy/stdlib RMS energy gating so offline
machines require zero extra cloud calls.
"""

from __future__ import annotations

import string
import time
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np


_PUNCTUATION_PAUSES: Dict[str, float] = {
    "...": 0.95,
    ".": 0.44,
    "!": 0.42,
    "?": 0.40,
    ",": 0.68,
    ";": 0.65,
    ":": 0.62,
}


def compute_pcm16_rms(pcm_bytes: bytes) -> float:
    """Compute normalized RMS energy [0.0, 1.0] for 16-bit signed PCM mono audio."""
    if not pcm_bytes or len(pcm_bytes) < 2:
        return 0.0
    usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
    samples = np.frombuffer(pcm_bytes[:usable], dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples))) / 32768.0)
    return min(1.0, max(0.0, rms))


def _ends_with_punctuation_key(text: str) -> Optional[str]:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.endswith("..."):
        return "..."
    last = stripped[-1]
    if last in _PUNCTUATION_PAUSES:
        return last
    return None


def suggest_silence_duration(text_so_far: str, *, speed_factor: float = 0.0) -> float:
    """Return suggested silence commit delay (seconds) from trailing text shape."""
    punct = _ends_with_punctuation_key(text_so_far)
    base = _PUNCTUATION_PAUSES.get(punct or "", 0.66)
    # Slightly longer wait when text is a single short word without ending punctuation
    words = [w.strip(string.punctuation) for w in text_so_far.split() if w.strip(string.punctuation)]
    if punct is None and len(words) <= 2:
        base = max(base, 0.72)
    adjusted = base * (1.0 + max(-0.4, min(0.5, speed_factor)))
    return max(0.32, min(1.4, adjusted))


@dataclass
class TurnEvent:
    speech_started: bool = False
    barge_in: bool = False
    commit_utterance: bool = False
    rms: float = 0.0


class AdaptiveTurnDetector:
    """Tracks live 16kHz Int16 PCM chunks into discrete turns & barge-in events."""

    def __init__(
        self,
        *,
        speech_rms_threshold: float = 0.018,
        barge_in_rms_threshold: float = 0.032,
        barge_in_min_frames: int = 3,
        max_utterance_seconds: float = 22.0,
        silence_commit_seconds: float = 0.62,
    ) -> None:
        self.speech_rms_threshold = speech_rms_threshold
        self.barge_in_rms_threshold = barge_in_rms_threshold
        self.barge_in_min_frames = barge_in_min_frames
        self.max_utterance_seconds = max_utterance_seconds
        self.silence_commit_seconds = silence_commit_seconds

        self._buffer = bytearray()
        self._in_speech = False
        self._speech_start_ts: float = 0.0
        self._last_voice_ts: float = 0.0
        self._voiced_frames: int = 0
        self._barge_in_frames: int = 0

    def reset(self) -> None:
        self._buffer.clear()
        self._in_speech = False
        self._speech_start_ts = 0.0
        self._last_voice_ts = 0.0
        self._voiced_frames = 0
        self._barge_in_frames = 0

    def has_pending_audio(self) -> bool:
        return len(self._buffer) >= 3200  # >= 100ms at 16kHz int16

    def pop_audio(self) -> bytes:
        data = bytes(self._buffer)
        self.reset()
        return data

    def feed_pcm(self, pcm_bytes: bytes, *, assistant_speaking: bool, now: Optional[float] = None) -> TurnEvent:
        ts = now if now is not None else time.monotonic()
        rms = compute_pcm16_rms(pcm_bytes)
        ev = TurnEvent(rms=rms)

        threshold = self.barge_in_rms_threshold if assistant_speaking else self.speech_rms_threshold
        is_voiced = rms >= threshold

        if is_voiced:
            if not self._in_speech:
                self._in_speech = True
                self._speech_start_ts = ts
                self._voiced_frames = 0
                ev.speech_started = True
            self._voiced_frames += 1
            self._last_voice_ts = ts
            self._buffer.extend(pcm_bytes)

            if assistant_speaking:
                self._barge_in_frames += 1
                if self._barge_in_frames >= self.barge_in_min_frames:
                    ev.barge_in = True
                    self._barge_in_frames = 0
            else:
                self._barge_in_frames = 0
        else:
            self._barge_in_frames = 0
            if self._in_speech:
                # Keep trailing silence for natural Whisper boundary detection
                self._buffer.extend(pcm_bytes)
                silence_elapsed = ts - self._last_voice_ts
                speech_duration = ts - self._speech_start_ts
                # Quick commit after short utterances; allow slightly longer after long monologue
                dynamic_pause = self.silence_commit_seconds if len(self._buffer) < 160000 else 0.78
                if silence_elapsed >= dynamic_pause and self._voiced_frames >= 2:
                    ev.commit_utterance = True
                elif silence_elapsed >= 1.2 and self._voiced_frames < 2:
                    # Short cough/click noise — drop cleanly
                    self.reset()

        if self._in_speech and (ts - self._speech_start_ts) >= self.max_utterance_seconds:
            ev.commit_utterance = True

        return ev

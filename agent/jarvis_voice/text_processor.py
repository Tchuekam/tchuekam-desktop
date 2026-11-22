"""Text normalization, clause chunking, and overlap matching for Realtime Voice.

Adapted in part from KoljaB/RealtimeVoiceChat (Apache-2.0) in
``vendor/realtime_voice_chat/code/text_context.py`` and ``text_similarity.py``.
"""

from __future__ import annotations

import re
import string
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Tuple


_TRANSLATION_TABLE = str.maketrans("", "", string.punctuation)


def _clean_and_split_words(text: str) -> List[str]:
    """Normalize unicode, strip punctuation, and split into lowercase words."""
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    cleaned = normalized.translate(_TRANSLATION_TABLE)
    return cleaned.split()


class TextContext:
    """Finds meaningful suffix overlaps between trailing partial STT and target text."""

    def __init__(self, max_len: int = 80, min_len: int = 5, similarity_threshold: float = 0.72) -> None:
        self.max_len = max_len
        self.min_len = min_len
        self.similarity_threshold = similarity_threshold

    def get_context(self, text: str, target_text: str) -> Tuple[Optional[int], Optional[str]]:
        if not text or not target_text or len(text) < self.min_len:
            return None, None
        sub = text[-self.max_len:].strip() if len(text) > self.max_len else text.strip()
        if len(sub) < self.min_len:
            return None, None

        lowered_target = target_text.lower()
        lowered_sub = sub.lower()
        best_ratio = 0.0
        best_match: Optional[str] = None
        best_start: Optional[int] = None

        # Slide window over target for short suffix match
        win_len = len(lowered_sub)
        if win_len <= len(lowered_target):
            for idx in range(0, len(lowered_target) - win_len + 1, 2):
                candidate = lowered_target[idx : idx + win_len]
                ratio = SequenceMatcher(None, lowered_sub, candidate).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_start = idx
                    best_match = target_text[idx : idx + win_len]

        if best_ratio >= self.similarity_threshold and best_start is not None:
            return best_start, best_match
        return None, None


class TextSimilarity:
    """Compares transcript updates using LCS / weighted focus similarity."""

    def __init__(self, focus_weight: float = 0.7) -> None:
        self.focus_weight = focus_weight
        self.overall_weight = 1.0 - focus_weight

    def calculate_similarity(self, text1: str, text2: str, focus_n_words: int = 5) -> float:
        w1 = _clean_and_split_words(text1)
        w2 = _clean_and_split_words(text2)
        if not w1 and not w2:
            return 1.0
        if not w1 or not w2:
            return 0.0

        overall = SequenceMatcher(None, w1, w2).ratio()
        tail1 = w1[-focus_n_words:]
        tail2 = w2[-focus_n_words:]
        focus = SequenceMatcher(None, tail1, tail2).ratio()
        return self.focus_weight * focus + self.overall_weight * overall


def sanitize_text_for_speech(text: str) -> str:
    """Convert rich assistant markdown/tool output into fluid speakable prose."""
    if not text:
        return ""
    cleaned = text
    # Remove thinking / scratchpad / memory blocks
    cleaned = re.sub(r"<(?:think|thinking|reasoning|REASONING_SCRATCHPAD)[^>]*>.*?</(?:think|thinking|reasoning|REASONING_SCRATCHPAD)>", " ", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<memory-context>.*?</memory-context>", " ", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"\[\[audio_as_voice\]\]", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"MEDIA:\S+", " ", cleaned)
    # Remove fenced code blocks cleanly
    cleaned = re.sub(r"```[\s\S]*?```", " code snippet omitted. ", cleaned)
    # Inline code -> readable text
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    # Markdown links [label](url) -> label
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    # Bare URLs
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    # Headings, bullets, emphasis markers
    cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", cleaned)
    cleaned = re.sub(r"(?m)^\s*[-*•]+\s+", "", cleaned)
    cleaned = re.sub(r"[*_~]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class StreamingClauseChunker:
    """Accumulates streamed assistant tokens and yields speakable clauses early."""

    _SENTENCE_END_RE = re.compile(r"([.!?]+(?:\s+|$))")
    _SOFT_CLAUSE_RE = re.compile(r"([,;:\n]+(?:\s+|$))")

    def __init__(self, *, min_clause_chars: int = 24, max_buffer_chars: int = 180) -> None:
        self._buf = ""
        self._in_think = False
        self.min_clause_chars = min_clause_chars
        self.max_buffer_chars = max_buffer_chars

    def push(self, delta: str) -> List[str]:
        if not delta:
            return []
        self._buf += delta
        # Strip inline <think>...</think> incrementally
        while True:
            if not self._in_think:
                start = self._buf.lower().find("<think>")
                if start >= 0:
                    end = self._buf.lower().find("</think>", start + 7)
                    if end >= 0:
                        self._buf = self._buf[:start] + " " + self._buf[end + 8 :]
                        continue
                    self._buf = self._buf[:start]
                    self._in_think = True
                    break
                break
            else:
                end = self._buf.lower().find("</think>")
                if end >= 0:
                    self._buf = self._buf[end + 8 :]
                    self._in_think = False
                    continue
                self._buf = ""
                break

        out: List[str] = []
        while self._buf:
            m = self._SENTENCE_END_RE.search(self._buf)
            if m and m.end() >= 8:
                raw_chunk = self._buf[: m.end()]
                self._buf = self._buf[m.end() :]
                spoken = sanitize_text_for_speech(raw_chunk)
                if spoken:
                    out.append(spoken)
                continue

            if len(self._buf) >= self.min_clause_chars:
                sm = self._SOFT_CLAUSE_RE.search(self._buf, pos=max(0, self.min_clause_chars // 2))
                if sm and sm.end() >= self.min_clause_chars:
                    raw_chunk = self._buf[: sm.end()]
                    self._buf = self._buf[sm.end() :]
                    spoken = sanitize_text_for_speech(raw_chunk)
                    if spoken:
                        out.append(spoken)
                    continue

            if len(self._buf) >= self.max_buffer_chars:
                cut = self._buf.rfind(" ", 0, self.max_buffer_chars)
                if cut <= 0:
                    cut = self.max_buffer_chars
                raw_chunk = self._buf[:cut]
                self._buf = self._buf[cut:].lstrip()
                spoken = sanitize_text_for_speech(raw_chunk)
                if spoken:
                    out.append(spoken)
                continue
            break

        return out

    def flush(self) -> Optional[str]:
        if self._in_think:
            self._buf = ""
            self._in_think = False
            return None
        spoken = sanitize_text_for_speech(self._buf)
        self._buf = ""
        return spoken or None

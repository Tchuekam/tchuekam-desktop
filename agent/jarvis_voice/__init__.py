"""Real-time full-duplex JARVIS voice subsystem for TchuekaM Agent.

Turn detection, text overlap/similarity, and duplex pipeline architecture
adapted from KoljaB/RealtimeVoiceChat (Apache-2.0, see vendor/realtime_voice_chat/LICENSE).
"""

from agent.jarvis_voice.text_processor import (
    StreamingClauseChunker,
    TextContext,
    TextSimilarity,
    sanitize_text_for_speech,
)
from agent.jarvis_voice.turn_detector import AdaptiveTurnDetector
from agent.jarvis_voice.pipeline import JarvisVoiceSession

__all__ = [
    "AdaptiveTurnDetector",
    "JarvisVoiceSession",
    "StreamingClauseChunker",
    "TextContext",
    "TextSimilarity",
    "sanitize_text_for_speech",
]

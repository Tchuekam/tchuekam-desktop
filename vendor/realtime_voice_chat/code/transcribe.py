import logging
logger = logging.getLogger(__name__)

from turndetect import strip_ending_punctuation
from difflib import SequenceMatcher
from colors import Colors
from text_similarity import TextSimilarity
from scipy import signal
import numpy as np
import threading
import textwrap
import torch
import json
import copy
import time
import re
from typing import Optional, Callable, Any, Dict, List

# --- Configuration Flags ---
USE_TURN_DETECTION = True
START_STT_SERVER = False # Set to True to use the client/server version of RealtimeSTT

# --- Recorder Configuration (Moved here for clarity, can be externalized) ---
# Default config if none provided to constructor
DEFAULT_RECORDER_CONFIG: Dict[str, Any] = {
    "use_microphone": False,
    "spinner": False,
    "model": "base.en",
    "realtime_model_type": "base.en",
    "use_main_model_for_realtime": False,
    "language": "en", # Default, will be overridden by source_language in __init__
    "silero_sensitivity": 0.05,
    "webrtc_sensitivity": 3,
    "post_speech_silence_duration": 0.7,
    "min_length_of_recording": 0.5,
    "min_gap_between_recordings": 0,
    "enable_realtime_transcription": True,
    "realtime_processing_pause": 0.03,
    "silero_use_onnx": True,
    "silero_deactivity_detection": True,
    "early_transcription_on_silence": 0,
    "beam_size": 3,
    "beam_size_realtime": 3,
    "no_log_file": True,
    "wake_words": "jarvis",
    "wakeword_backend": "pvporcupine",
    "allowed_latency_limit": 500,
    # Callbacks will be added dynamically in _create_recorder
    "debug_mode": True,
    "initial_prompt_realtime": "The sky is blue. When the sky... She walked home. Because he... Today is sunny. If only I...",
    "faster_whisper_vad_filter": False,
}


if START_STT_SERVER:
    from RealtimeSTT import AudioToTextRecorderClient
else:
    from RealtimeSTT import AudioToTextRecorder

if USE_TURN_DETECTION:
    from turndetect import TurnDetection


INT16_MAX_ABS_VALUE: float = 32768.0
SAMPLE_RATE: int = 16000


class TranscriptionProcessor:
    """
    Manages audio transcription using RealtimeSTT, handling real-time and final
    transcription callbacks, silence detection, turn detection (optional),
    and potential sentence end detection.

    This class acts as a bridge between raw audio input and transcription results,
    coordinating the RealtimeSTT recorder, processing callbacks, and managing
    internal state related to silence, potential sentences, and turn timing.
    """
    # --- Constants for Silence Monitor Logic ---
    # Reserve time to ensure pipeline doesn't start too early or late
    _PIPELINE_RESERVE_TIME_MS: float = 0.02 # 20 ms
    # Offset from end of silence_waiting_time to start considering "hot" state
    _HOT_THRESHOLD_OFFSET_S: float = 0.35
    # Minimum duration for the "hot" condition to be meaningful
    _MIN_HOT_CONDITION_DURATION_S: float = 0.15
    # Time before full silence duration when TTS synthesis might be allowed
    _TTS_ALLOWANCE_OFFSET_S: float = 0.25
    # Minimum time for potential sentence end detection relative to silence start
    _MIN_POTENTIAL_END_DETECTION_TIME_MS: float = 0.02 # 20 ms
    # Maximum age for cached sentence end timestamps (ms)
    _SENTENCE_CACHE_MAX_AGE_MS: float = 0.2
    # Number of detections within the cache age required to trigger potential end
    _SENTENCE_CACHE_TRIGGER_COUNT: int = 3


    def __init__(
            self,
            source_language: str = "en",
            realtime_transcription_callback: Optional[Callable[[str], None]] = None,
            full_transcription_callback: Optional[Callable[[str], None]] = None,
            potential_full_transcription_callback: Optional[Callable[[str], None]] = None,
            potential_full_transcription_abort_callback: Optional[Callable[[], None]] = None,
            potential_sentence_end: Optional[Callable[[str], None]] = None,
            before_final_sentence: Optional[Callable[[Optional[np.ndarray], Optional[str]], bool]] = None,
            silence_active_callback: Optional[Callable[[bool], None]] = None,
            on_recording_start_callback: Optional[Callable[[], None]] = None,
            is_orpheus: bool = False,
            local: bool = True,
            tts_allowed_event: Optional[threading.Event] = None, # Note: This seems unused in the original code provided
            pipeline_latency: float = 0.5,
            recorder_config: Optional[Dict[str, Any]] = None, # Allow passing custom config
    ) -> None:
        """
        Initializes the TranscriptionProcessor.

        Args:
            source_language: Language code for transcription (e.g., "en").
            realtime_transcription_callback: Callback for real-time transcription updates. Receives partial text.
            full_transcription_callback: Callback for final transcription result. Receives final text.
            potential_full_transcription_callback: Callback triggered when a full transcription is likely imminent (in "hot" state). Receives current real-time text.
            potential_full_transcription_abort_callback: Callback triggered when the "hot" state ends before final transcription.
            potential_sentence_end: Callback triggered when a potential sentence end is detected. Receives the potentially complete sentence text.
            before_final_sentence: Callback triggered just before the recorder finalizes transcription. Receives audio copy and current real-time text. Return True to potentially influence recorder behavior (if supported).
            silence_active_callback: Callback triggered when silence detection state changes. Receives boolean (True if silence is active).
            on_recording_start_callback: Callback triggered when the recorder starts recording after silence or wake word.
            is_orpheus: Flag indicating if specific timing adjustments for 'Orpheus' mode should be used.
            local: Flag used by TurnDetection (if enabled) to indicate local vs remote processing context.
            tts_allowed_event: An event that might be set when TTS synthesis is allowed (currently unused in provided logic).
            pipeline_latency: Estimated latency of the downstream processing pipeline in seconds. Used for timing calculations.
            recorder_config: Optional dictionary to override default RealtimeSTT recorder configuration.
        """
        self.source_language = source_language
        self.realtime_transcription_callback = realtime_transcription_callback
        self.full_transcription_callback = full_transcription_callback
        self.potential_full_transcription_callback = potential_full_transcription_callback
        self.potential_full_transcription_abort_callback = potential_full_transcription_abort_callback
        self.potential_sentence_end = potential_sentence_end
        self.before_final_sentence = before_final_sentence
        self.silence_active_callback = silence_active_callback
        self.on_recording_start_callback = on_recording_start_callback
        self.is_orpheus = is_orpheus
        self.pipeline_latency = pipeline_latency
        self.recorder: Optional[AudioToTextRecorder | AudioToTextRecorderClient] = None
        self.is_silero_speech_active: bool = False # Note: Seems unused
        self.silero_working: bool = False         # Note: Seems unused
        self.on_wakeword_detection_start: Optional[Callable] = None # Note: Seems unused
        self.on_wakeword_detection_end: Optional[Callable] = None   # Note: Seems unused
        self.realtime_text: Optional[str] = None
        self.sentence_end_cache: List[Dict[str, Any]] = []
        self.potential_sentences_yielded: List[Dict[str, Any]] = []
        self.stripped_partial_user_text: str = ""
        self.final_transcription: Optional[str] = None
        self.shutdown_performed: bool = False
        self.silence_time: float = 0.0
        self.silence_active: bool = False
        self.last_audio_copy: Optional[np.ndarray] = None

        self.on_tts_allowed_to_synthesize: Optional[Callable] = None # Note: Seems unused

        self.text_similarity = TextSimilarity(focus='end', n_words=5)

        # Use provided config or default
        self.recorder_config = copy.deepcopy(recorder_config if recorder_config else DEFAULT_RECORDER_CONFIG)
        self.recorder_config['language'] = self.source_language # Ensure language is set

        if USE_TURN_DETECTION:
            logger.info(f"👂🔄 {Colors.YELLOW}Turn detection enabled{Colors.RESET}")
            self.turn_detection = TurnDetection(
                on_new_waiting_time=self.on_new_waiting_time,
                local=local,
                pipeline_latency=pipeline_latency
            )

        self._create_recorder()
        self._start_silence_monitor()

    # --- Recorder Parameter Abstraction ---

    def _get_recorder_param(self, param_name: str, default: Any = None) -> Any:
        """
        Internal helper to get a parameter from the recorder instance,
        abstracting client/server differences.

        Args:
            param_name: The name of the parameter to retrieve.
            default: The value to return if the recorder is not initialized or
                     the parameter doesn't exist.

        Returns:
            The value of the recorder parameter or the default value.
        """
        if not self.recorder:
            return default
        if START_STT_SERVER:
            # Assuming get_parameter exists and handles potential errors
            return self.recorder.get_parameter(param_name) # type: ignore
        else:
            # Access attribute directly for the local version
            return getattr(self.recorder, param_name, default)

    def _set_recorder_param(self, param_name: str, value: Any) -> None:
        """
        Internal helper to set a parameter on the recorder instance,
        abstracting client/server differences.

        Args:
            param_name: The name of the parameter to set.
            value: The value to set the parameter to.
        """
        if not self.recorder:
            return
        if START_STT_SERVER:
            # Assuming set_parameter exists and handles potential errors
            self.recorder.set_parameter(param_name, value) # type: ignore
        else:
            # Set attribute directly for the local version
            setattr(self.recorder, param_name, value)

    def _is_recorder_recording(self) -> bool:
        """
        Internal helper to check if the recorder is currently recording,
        abstracting client/server differences.

        Returns:
            True if the recorder is active and recording, False otherwise.
        """
        if not self.recorder:
            return False
        if START_STT_SERVER:
            return self.recorder.get_parameter("is_recording") # type: ignore
        else:
            # Ensure the attribute exists before accessing
            return getattr(self.recorder, "is_recording", False)

    # --- Silence Monitor ---
    def _start_silence_monitor(self) -> None:
        """
        Starts a background thread to monitor silence duration and trigger
        events like potential sentence end detection, TTS synthesis allowance,
        and potential full transcription ("hot") state changes.
        """
        def monitor():
            hot = False
            # Initialize silence_time using the abstracted getter
            self.silence_time = self._get_recorder_param("speech_end_silence_start", 0.0)

            while not self.shutdown_performed:
                speech_end_silence_start = self.silence_time # Use cached value updated by callback

                if self.recorder and speech_end_silence_start is not None and speech_end_silence_start != 0:
                    silence_waiting_time = self._get_recorder_param("post_speech_silence_duration", 0.0)
                    time_since_silence = time.time() - speech_end_silence_start

                    # Calculate latest time pipeline can start without exceeding silence duration
                    latest_pipe_start_time = silence_waiting_time - self.pipeline_latency - self._PIPELINE_RESERVE_TIME_MS

                    # Calculate the target time to trigger potential sentence end detection
                    potential_sentence_end_time = latest_pipe_start_time
                    # Ensure it doesn't trigger too early
                    if potential_sentence_end_time < self._MIN_POTENTIAL_END_DETECTION_TIME_MS:
                        potential_sentence_end_time = self._MIN_POTENTIAL_END_DETECTION_TIME_MS

                    # Determine the threshold time to enter the "hot" state
                    start_hot_condition_time = silence_waiting_time - self._HOT_THRESHOLD_OFFSET_S
                    # Ensure the hot condition has a minimum meaningful duration
                    if start_hot_condition_time < self._MIN_HOT_CONDITION_DURATION_S:
                        start_hot_condition_time = self._MIN_HOT_CONDITION_DURATION_S

                    # Adjust potential_sentence_end_time based on Orpheus mode
                    if self.is_orpheus:
                         # For Orpheus, ensure potential end detection doesn't happen too early relative to hot state
                        orpheus_potential_end_time = silence_waiting_time - self._HOT_THRESHOLD_OFFSET_S
                        if potential_sentence_end_time < orpheus_potential_end_time:
                             potential_sentence_end_time = orpheus_potential_end_time


                    # --- Trigger Actions Based on Timing ---

                    # 1. Force potential sentence end detection if time has passed
                    if time_since_silence > potential_sentence_end_time:
                        # Check if realtime_text exists before logging/detecting
                        current_text = self.realtime_text if self.realtime_text else ""
                        logger.info(f"👂🔚 {Colors.YELLOW}Potential sentence end detected (timed out){Colors.RESET}: {current_text}")
                        # Use force_yield=True because this is triggered by timeout, not punctuation detection
                        self.detect_potential_sentence_end(current_text, force_yield=True, force_ellipses=True) # Force ellipses if timeout occurs

                    # 2. Allow TTS synthesis shortly before the final silence duration elapses
                    tts_allowance_time = silence_waiting_time - self._TTS_ALLOWANCE_OFFSET_S
                    if time_since_silence > tts_allowance_time:
                        if self.on_tts_allowed_to_synthesize: # Check if callback exists
                            self.on_tts_allowed_to_synthesize()

                    # 3. Handle "Hot" state (potential full transcription)
                    hot_condition_met = time_since_silence > start_hot_condition_time
                    if hot_condition_met and not hot:
                        hot = True
                        print(f"{Colors.MAGENTA}HOT{Colors.RESET}")
                        if self.potential_full_transcription_callback:
                            self.potential_full_transcription_callback(self.realtime_text)
                    elif not hot_condition_met and hot:
                        # Transitioning from Hot to Cold while still in silence period (e.g., silence_waiting_time changed)
                        if self._is_recorder_recording(): # Check if still recording before aborting
                            print(f"{Colors.CYAN}COLD (during silence){Colors.RESET}")
                            if self.potential_full_transcription_abort_callback:
                                self.potential_full_transcription_abort_callback()
                        hot = False

                elif hot: # Exited silence period (speech_end_silence_start is 0 or None)
                    # If we were hot, but silence ended (e.g., new speech started), transition to cold
                    if self._is_recorder_recording(): # Check if recording actually restarted
                         print(f"{Colors.CYAN}COLD (silence ended){Colors.RESET}")
                         if self.potential_full_transcription_abort_callback:
                             self.potential_full_transcription_abort_callback()
                    hot = False

                time.sleep(0.001) # Short sleep to prevent busy-waiting dominating CPU

        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

    def on_new_waiting_time(
            self,
            waiting_time: float,
            text: Optional[str] = None,
        ) -> None:
        """
        Callback handler for when TurnDetection calculates a new waiting time.
        Updates the recorder's post_speech_silence_duration parameter.

        Args:
            waiting_time: The new calculated silence duration in seconds.
            text: The text used by TurnDetection to calculate the waiting time (for logging).
        """
        if self.recorder:
            current_duration = self._get_recorder_param("post_speech_silence_duration")
            if current_duration != waiting_time:
                log_text = text if text else "(No text provided)"
                logger.info(f"👂⏳ {Colors.GRAY}New waiting time: {Colors.RESET}{Colors.YELLOW}{waiting_time:.2f}{Colors.RESET}{Colors.GRAY} for text: {log_text}{Colors.RESET}")
                self._set_recorder_param("post_speech_silence_duration", waiting_time)
        else:
            logger.warning("👂⚠️ Recorder not initialized, cannot set new waiting time.")

    def transcribe_loop(self) -> None:
        """
        Sets up the final transcription callback mechanism with the recorder.

        This method defines the `on_final` callback that will be invoked by the
        recorder when a complete utterance transcription is available. It then
        registers this callback with the recorder instance.
        """
        def on_final(text: Optional[str]):
            if text is None or text == "":
                logger.warning("👂❓ Final transcription received None or empty string.")
                return

            self.final_transcription = text
            logger.info(f"👂✅ {Colors.apply('Final user text: ').green} {Colors.apply(text).yellow}")
            self.sentence_end_cache.clear()
            self.potential_sentences_yielded.clear()

            if USE_TURN_DETECTION and hasattr(self, 'turn_detection'):
                self.turn_detection.reset()
            if self.full_transcription_callback:
                self.full_transcription_callback(text)

        if self.recorder:
            # The specific method might differ between client/local STT versions
            # Assuming a common 'text' method exists or is adapted
            if hasattr(self.recorder, 'text'):
                self.recorder.text(on_final) # type: ignore # Assume method exists
            elif START_STT_SERVER:
                 logger.warning("👂⚠️ Recorder client does not have a 'text' method. Attempting to set 'on_final_transcription' parameter.")
                 # Attempt to set via parameter for client, might not be the correct API
                 try:
                     self._set_recorder_param('on_final_transcription', on_final)
                 except Exception as e:
                     logger.error(f"👂💥 Failed to set final transcription callback parameter for client: {e}")
            else:
                logger.warning("👂⚠️ Local recorder object does not have a 'text' method for final callback.")
        else:
            logger.error("👂❌ Cannot set final callback: Recorder not initialized.")


    def abort_generation(self) -> None:
        """
        Clears the cache of potentially yielded sentences.

        This effectively stops any further actions that might be triggered based
        on previously detected potential sentence ends, useful if processing needs
        to be reset or interrupted externally.
        """
        self.potential_sentences_yielded.clear()
        logger.info("👂⏹️ Potential sentence yield cache cleared (generation aborted).")

    def perform_final(self, audio_bytes: Optional[bytes] = None) -> None:
        """
        Manually triggers the final transcription process using the last known
        real-time text.

        This bypasses the recorder's natural end-of-speech detection and immediately
        invokes the final transcription callback with the `self.realtime_text` content.
        Useful for scenarios where transcription needs to be finalized externally.

        Args:
            audio_bytes: Optional audio data (currently unused in this method's logic
                         but kept for potential future use or API consistency).
        """
        if self.recorder: # Check if recorder exists, primarily as a gatekeeper
            if self.realtime_text is None:
                logger.warning(f"👂❓ {Colors.RED}Forcing final transcription, but realtime_text is None. Using empty string.{Colors.RESET}")
                current_text = ""
            else:
                current_text = self.realtime_text

            self.final_transcription = current_text # Update internal state
            logger.info(f"👂❗ {Colors.apply('Forced Final user text: ').green} {Colors.apply(current_text).yellow}")
            self.sentence_end_cache.clear()
            self.potential_sentences_yielded.clear()

            if USE_TURN_DETECTION and hasattr(self, 'turn_detection'):
                self.turn_detection.reset()

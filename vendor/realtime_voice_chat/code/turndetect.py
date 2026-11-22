import logging
logger = logging.getLogger(__name__)

import transformers
import collections
import threading
import queue
import torch
import time
import re

# Configuration constants
model_dir_local = "KoljaB/SentenceFinishedClassification"
model_dir_cloud = "/root/models/sentenceclassification/"
sentence_end_marks = ['.', '!', '?', '。'] # Characters considered sentence endings

# Anchor points for probability-to-pause interpolation
anchor_points = [
    (0.0, 1.0), # Probability 0.0 maps to pause 1.0
    (1.0, 0.0)  # Probability 1.0 maps to pause 0.0
]

def ends_with_string(text: str, s: str) -> bool:
    """
    Checks if a string ends with a specific substring, allowing for one trailing character.

    Useful for checking punctuation even if there's a trailing space.

    Args:
        text: The input string to check.
        s: The substring to look for at the end.

    Returns:
        True if the text ends with s, or if text[:-1] ends with s. False otherwise.
    """
    if text.endswith(s):
        return True
    # Check if it ends if we ignore the very last character (e.g., trailing space)
    if len(text) > 1 and text[:-1].endswith(s):
        return True
    return False

def preprocess_text(text: str) -> str:
    """
    Cleans and normalizes the beginning of a text string.

    Applies the following steps:
    1. Removes leading whitespace.
    2. Removes leading ellipses ("...") if present.
    3. Removes leading whitespace again (after potential ellipses removal).
    4. Uppercases the first letter of the remaining text.

    Args:
        text: The input text string.

    Returns:
        The preprocessed text string.
    """
    text = text.lstrip() # Remove leading whitespaces
    if text.startswith("..."): #  Remove starting ellipses if present
        text = text[3:]
    text = text.lstrip() # Remove any leading whitespaces again after ellipses removal
    if text:
        text = text[0].upper() + text[1:] # Uppercase the first letter

    return text

def strip_ending_punctuation(text: str) -> str:
    """
    Removes trailing punctuation marks defined in `sentence_end_marks`.

    Removes trailing whitespace first, then iteratively removes any characters
    from `sentence_end_marks` found at the end of the string.

    Args:
        text: The input text string.

    Returns:
        The text string with specified trailing punctuation removed.
    """
    text = text.rstrip()
    for char in sentence_end_marks:
        # Repeatedly strip each punctuation mark in case of multiples (e.g., "!!")
        while text.endswith(char):
             text = text.rstrip(char)
    return text # Return the stripped text

def find_matching_texts(texts_without_punctuation: collections.deque) -> list[tuple[str, str]]:
    """
    Finds recent consecutive entries with the same stripped text.

    Iterates backwards through the deque of (original_text, stripped_text) tuples.
    It collects all entries matching the stripped text of the *last* entry,
    stopping as soon as a non-matching stripped text is encountered.

    Args:
        texts_without_punctuation: A deque of tuples, where each tuple is
                                   (original_text, stripped_text).

    Returns:
        A list of matching (original_text, stripped_text) tuples in their
        original order (oldest matching first). Returns an empty list if the
        input deque is empty.
    """
    if not texts_without_punctuation:
        return []

    # Get the stripped text from the last entry
    last_stripped_text = texts_without_punctuation[-1][1]

    matching_entries = []

    # Iterate through the deque backwards
    for entry in reversed(texts_without_punctuation):
        original_text, stripped_text = entry

        # If we find a non-match, stop collecting
        if stripped_text != last_stripped_text:
            break

        # Add the matching entry (will be reversed later)
        matching_entries.append(entry)

    # Reverse the results to maintain original insertion order
    matching_entries.reverse()

    return matching_entries

def interpolate_detection(prob: float) -> float:
    """
    Linearly interpolates a value based on probability using predefined anchor points.

    Maps an input probability `prob` (clamped between 0.0 and 1.0) to an output
    value based on the `anchor_points` list. It finds the segment within
    `anchor_points` where `prob` falls and performs linear interpolation.

    Args:
        prob: The input probability, expected between 0.0 and 1.0.

    Returns:
        The interpolated value. Returns 4.0 as a fallback if interpolation fails
        (though this shouldn't happen if anchor points cover the [0,1] range).
    """
    # Clamp probability between 0.0 and 1.0 just in case
    p = max(0.0, min(prob, 1.0))

    # Check if probability exactly matches an anchor point
    for ap_p, ap_val in anchor_points:
        if abs(ap_p - p) < 1e-9: # Use tolerance for float comparison
            return ap_val

    # Find the segment [p1, p2] where p resides
    for i in range(len(anchor_points) - 1):
        p1, v1 = anchor_points[i]
        p2, v2 = anchor_points[i+1]
        # Ensure anchor points are sorted by probability for this logic to work
        if p1 <= p <= p2:
            # Avoid division by zero if anchor points have the same probability
            if abs(p2 - p1) < 1e-9:
                return v1 # or v2, they should be close if p1=p2
            # Linear interpolation formula
            ratio = (p - p1) / (p2 - p1)
            return v1 + ratio * (v2 - v1)

    # Fallback: Should not be reached if anchor_points cover [0,1] properly.
    logger.warning(f"🎤⚠️ Probability {p} fell outside defined anchor points {anchor_points}. Returning fallback value.")
    return 4.0

class TurnDetection:
    """
    Manages turn detection logic based on text input and sentence completion model.

    This class receives text segments, uses a transformer model to predict sentence
    completion probability, considers punctuation, and calculates a suggested waiting
    time (pause duration) before the next speaker might start. It uses a background
    thread for processing and provides a callback for new waiting time suggestions.
    It also maintains a history of recent texts and uses caching for model predictions.
    """

    def __init__(
        self,
        on_new_waiting_time: callable,
        local: bool = False,
        pipeline_latency: float = 0.5,
        pipeline_latency_overhead: float = 0.1,
    ) -> None:
        """
        Initializes the TurnDetection instance.

        Loads the sentence classification model and tokenizer, sets up internal state
        (deques, cache), starts the background processing thread, and performs model warmup.

        Args:
            on_new_waiting_time: Callback function invoked when a new waiting time is calculated.
                                 It receives `(time: float, text: str)`.
            local: If True, loads the model from `model_dir_local`, otherwise from `model_dir_cloud`.
            pipeline_latency: Estimated base latency of the STT/processing pipeline in seconds.
            pipeline_latency_overhead: Additional buffer added to the pipeline latency.
        """
        model_dir = model_dir_local if local else model_dir_cloud

        self.on_new_waiting_time = on_new_waiting_time

        self.current_waiting_time: float = -1 # Tracks the last suggested time
        # Use deques with maxlen for efficient, bounded history storage
        self.text_time_deque: collections.deque[tuple[float, str]] = collections.deque(maxlen=100)
        self.texts_without_punctuation: collections.deque[tuple[str, str]] = collections.deque(maxlen=20)

        self.text_queue: queue.Queue[str] = queue.Queue() # Queue for incoming text
        self.text_worker = threading.Thread(
            target=self._text_worker,
            daemon=True # Allows program to exit even if this thread is running
        )
        self.text_worker.start()

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"🎤🔌 Using device: {self.device}")
        self.tokenizer = transformers.DistilBertTokenizerFast.from_pretrained(model_dir)
        self.classification_model = transformers.DistilBertForSequenceClassification.from_pretrained(model_dir)
        self.classification_model.to(self.device)
        self.classification_model.eval() # Set model to evaluation mode
        self.max_length: int = 128 # Max sequence length for the model
        self.pipeline_latency: float = pipeline_latency
        self.pipeline_latency_overhead: float = pipeline_latency_overhead

        # Initialize completion probability cache with OrderedDict for LRU behavior
        self._completion_probability_cache: collections.OrderedDict[str, float] = collections.OrderedDict()
        self._completion_probability_cache_max_size: int = 256 # Max size for the LRU cache

        # Warmup the classification model for faster initial predictions
        logger.info("🎤🔥 Warming up the classification model...")
        with torch.no_grad():
            warmup_text = "This is a warmup sentence."
            inputs = self.tokenizer(
                warmup_text,
                return_tensors="pt",
                truncation=True,
                padding="max_length",
                max_length=self.max_length
            )
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            _ = self.classification_model(**inputs) # Run one prediction
        logger.info("🎤✅ Classification model warmed up.")

        # Default dynamic pause settings (initialized for speed_factor=0.0)
        self.detection_speed: float = 0.5
        self.ellipsis_pause: float = 2.3
        self.punctuation_pause: float = 0.39
        self.exclamation_pause: float = 0.35
        self.question_pause: float = 0.33
        self.unknown_sentence_detection_pause: float = 1.25
        # Apply initial settings (can be called again later)
        self.update_settings(speed_factor=0.0)

    def update_settings(self, speed_factor: float) -> None:
        """
        Adjusts dynamic pause parameters based on a speed factor.

        Linearly interpolates between 'fast' (speed_factor=0.0) and 'very_slow'
        (speed_factor=1.0) settings for various pause durations used in calculation.
        Clamps speed_factor between 0.0 and 1.0.

        Args:
            speed_factor: A float between 0.0 (fastest) and 1.0 (slowest) controlling
                          the interpolation between predefined settings.
        """
        speed_factor = max(0.0, min(speed_factor, 1.0)) # Clamp factor

        # Base 'fast' settings (speed_factor = 0.0)
        fast = {
            'detection_speed': 0.5,

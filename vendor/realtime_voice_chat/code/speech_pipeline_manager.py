# speech_pipeline_manager.py
from typing import Optional, Callable
import threading
import logging
import time
from queue import Queue, Empty
import sys

# (Make sure real/mock imports are correct)
from audio_module import AudioProcessor
from text_similarity import TextSimilarity
from text_context import TextContext
from llm_module import LLM
from colors import Colors

# (Logging setup)
logger = logging.getLogger(__name__)

# (Load system prompt)
try:
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()
    logger.info("🗣️📄 System prompt loaded from file.")
except FileNotFoundError:
    logger.warning("🗣️📄 system_prompt.txt not found. Using default system prompt.")
    system_prompt = "You are a helpful assistant."


USE_ORPHEUS_UNCENSORED = False

orpheus_prompt_addon_normal = """
When expressing emotions, you are ONLY allowed to use the following exact tags (including the spaces):
" <laugh> ", " <chuckle> ", " <sigh> ", " <cough> ", " <sniffle> ", " <groan> ", " <yawn> ", and " <gasp> ".

Do NOT create or use any other emotion tags. Do NOT remove the spaces. Use these tags exactly as shown, and only when appropriate.
""".strip()

orpheus_prompt_addon_uncensored = """
When expressing emotions, you are ONLY allowed to use the following exact tags (including the spaces):
" <moans> ", " <panting> ", " <grunting> ", " <gagging sounds> ", " <chokeing> ", " <kissing noises> ", " <laugh> ", " <chuckle> ", " <sigh> ", " <cough> ", " <sniffle> ", " <groan> ", " <yawn> ", " <gasp> ".
Do NOT create or use any other emotion tags. Do NOT remove the spaces. Use these tags exactly as shown, and only when appropriate.
""".strip()

orpheus_prompt_addon = orpheus_prompt_addon_uncensored if USE_ORPHEUS_UNCENSORED else orpheus_prompt_addon_normal


class PipelineRequest:
    """
    Represents a request to be processed by the SpeechPipelineManager's request queue.

    Holds information about the action to perform (e.g., 'prepare', 'abort'),
    associated data (e.g., text input), and a timestamp for potential de-duplication.
    """
    def __init__(self, action: str, data: Optional[any] = None):
        """
        Initializes a PipelineRequest instance.

        Args:
            action: The type of action requested (e.g., "prepare", "abort").
            data: Optional data associated with the action (e.g., input text for "prepare").
        """
        self.action = action
        self.data = data
        self.timestamp = time.time()

class RunningGeneration:
    """
    Holds the state and resources for a single, ongoing text-to-speech generation process.

    This includes the generation ID, input text, the LLM generator object, flags indicating
    the status of LLM and TTS stages (quick and final), threading events for synchronization,
    queues for audio chunks, and text buffers for partial/complete answers.
    """
    def __init__(self, id: int):
        """
        Initializes a RunningGeneration state object.

        Args:
            id: A unique identifier for this generation attempt.
        """
        self.id: int = id # Store the generation ID
        self.text: Optional[str] = None
        self.timestamp = time.time()

        self.llm_generator = None
        self.llm_finished: bool = False
        self.llm_finished_event = threading.Event()
        self.llm_aborted: bool = False

        self.quick_answer: str = ""
        self.quick_answer_provided: bool = False
        self.quick_answer_first_chunk_ready: bool = False
        self.quick_answer_overhang: str = "" # This is the part of the text that was not used in the context
        self.tts_quick_started: bool = False

        self.tts_quick_allowed_event = threading.Event()
        self.audio_chunks = Queue()
        self.audio_quick_finished: bool = False
        self.audio_quick_aborted: bool = False
        self.tts_quick_finished_event = threading.Event()

        self.abortion_started: bool = False

        self.tts_final_finished_event = threading.Event()
        self.tts_final_started: bool = False
        self.audio_final_aborted: bool = False
        self.audio_final_finished: bool = False
        self.final_answer: str = ""

        self.completed: bool = False


class SpeechPipelineManager:
    """
    Orchestrates the text-to-speech pipeline, managing LLM and TTS workers.

    This class handles incoming text requests, manages the lifecycle of a generation
    (including LLM inference, TTS synthesis for both quick and final parts),
    facilitates aborting ongoing generations, manages conversation history,
    and coordinates worker threads using queues and events.
    """
    def __init__(
            self,
            tts_engine: str = "kokoro",
            llm_provider: str = "ollama",
            llm_model: str = "hf.co/bartowski/huihui-ai_Mistral-Small-24B-Instruct-2501-abliterated-GGUF:Q4_K_M",
            no_think: bool = False,
            orpheus_model: str = "orpheus-3b-0.1-ft-Q8_0-GGUF/orpheus-3b-0.1-ft-q8_0.gguf",
        ):
        """
        Initializes the SpeechPipelineManager.

        Sets up configuration, instantiates dependencies (AudioProcessor, LLM, etc.),
        loads system prompts, initializes state variables (queues, events, flags),
        measures initial inference latencies, and starts the background worker threads.

        Args:
            tts_engine: The TTS engine to use (e.g., "kokoro", "orpheus").
            llm_provider: The LLM backend provider (e.g., "ollama").
            llm_model: The specific LLM model identifier.
            no_think: If True, removes specific thinking tags from LLM output.
            orpheus_model: Path or identifier for the Orpheus TTS model, if used.
        """
        self.tts_engine = tts_engine
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.no_think = no_think
        self.orpheus_model = orpheus_model

        self.system_prompt = system_prompt
        if tts_engine == "orpheus":
            self.system_prompt += f"\n{orpheus_prompt_addon}"

        # --- Instance Dependencies ---
        self.audio = AudioProcessor(
            engine=self.tts_engine,
            orpheus_model=self.orpheus_model
        )
        self.audio.on_first_audio_chunk_synthesize = self.on_first_audio_chunk_synthesize
        self.text_similarity = TextSimilarity(focus='end', n_words=5)
        self.text_context = TextContext()
        self.generation_counter: int = 0
        self.abort_lock = threading.Lock()
        self.llm = LLM(
            backend=self.llm_provider, # Or your backend
            model=self.llm_model,
            system_prompt=self.system_prompt,
            no_think=no_think,
        )
        self.llm.prewarm()
        self.llm_inference_time = self.llm.measure_inference_time()
        logger.debug(f"🗣️🧠🕒 LLM inference time: {self.llm_inference_time:.2f}ms")

        # --- State ---
        self.history = []
        self.requests_queue = Queue()
        self.running_generation: Optional[RunningGeneration] = None

        # --- Threading Events ---
        self.shutdown_event = threading.Event()
        self.generator_ready_event = threading.Event()
        self.llm_answer_ready_event = threading.Event()
        self.stop_everything_event = threading.Event()
        self.stop_llm_request_event = threading.Event()
        self.stop_llm_finished_event = threading.Event()
        self.stop_tts_quick_request_event = threading.Event()
        self.stop_tts_quick_finished_event = threading.Event()
        self.stop_tts_final_request_event = threading.Event()
        self.stop_tts_final_finished_event = threading.Event()
        self.abort_completed_event = threading.Event()
        self.abort_block_event = threading.Event()
        self.abort_block_event.set()
        self.check_abort_lock = threading.Lock()

        # --- State Flags ---
        self.llm_generation_active = False
        self.tts_quick_generation_active = False
        self.tts_final_generation_active = False
        self.previous_request = None

        # --- Worker Threads ---
        self.request_processing_thread = threading.Thread(target=self._request_processing_worker, name="RequestProcessingThread", daemon=True)
        self.llm_inference_thread = threading.Thread(target=self._llm_inference_worker, name="LLMProcessingThread", daemon=True)
        self.tts_quick_inference_thread = threading.Thread(target=self._tts_quick_inference_worker, name="TTSQuickProcessingThread", daemon=True)
        self.tts_final_inference_thread = threading.Thread(target=self._tts_final_inference_worker, name="TTSFinalProcessingThread", daemon=True)

        self.request_processing_thread.start()
        self.llm_inference_thread.start()
        self.tts_quick_inference_thread.start()
        self.tts_final_inference_thread.start()

        self.on_partial_assistant_text: Optional[Callable[[str], None]] = None

        self.full_output_pipeline_latency = self.llm_inference_time + self.audio.tts_inference_time
        logger.info(f"🗣️⏱️ Full output pipeline latency: {self.full_output_pipeline_latency:.2f}ms (LLM: {self.llm_inference_time:.2f}ms, TTS: {self.audio.tts_inference_time:.2f}ms)")

        logger.info("🗣️🚀 SpeechPipelineManager initialized and workers started.")

    def is_valid_gen(self) -> bool:
        """
        Checks if there is a currently running generation that has not started aborting.

        Returns:
            True if `running_generation` exists and its `abortion_started` flag is False,
            False otherwise.
        """
        return self.running_generation is not None and not self.running_generation.abortion_started

    def _request_processing_worker(self):
        """
        Worker thread target that processes requests from the `requests_queue`.

        Continuously monitors the queue. When a request arrives, it drains the queue
        to process only the most recent one, preventing processing of stale requests.
        It waits for any ongoing abort operation to complete (`abort_block_event`)
        before processing the next request. Handles 'prepare' actions by calling
        `process_prepare_generation`. Runs until `shutdown_event` is set.
        """
        logger.info("🗣️🚀 Request Processor: Starting...")
        while not self.shutdown_event.is_set():
            try:
                # Get the most recent request by emptying the queue first
                request = self.requests_queue.get(block=True, timeout=1)

                if self.previous_request:
                    # Simple timestamp-based deduplication for identical consecutive requests
                    if self.previous_request.data == request.data and isinstance(request.data, str):
                        if request.timestamp - self.previous_request.timestamp < 2:
                            logger.info(f"🗣️🗑️ Request Processor: Skipping duplicate request - {request.action}")
                            continue

                # Drain the queue to get the most recent request
                while not self.requests_queue.empty():
                    skipped_request = self.requests_queue.get(False)  # Non-blocking get
                    logger.debug(f"🗣️🗑️ Request Processor: Skipping older request - {skipped_request.action}")
                    request = skipped_request # Keep the last one we retrieved
                
                self.abort_block_event.wait() # Wait if an abort is in progress
                logger.debug(f"🗣️🔄 Request Processor: Processing most recent request - {request.action}")
                
                if request.action == "prepare":
                    self.process_prepare_generation(request.data)
                    self.previous_request = request
                elif request.action == "finish":
                     # Note: 'finish' action currently has no specific handling logic here.
                     logger.info(f"🗣️🤷 Request Processor: Received 'finish' action (currently no-op).")
                     self.previous_request = request # Still update previous_request
                else:
                    logger.warning(f"🗣️❓ Request Processor: Unknown action '{request.action}'")

            except Empty:
                continue
            except Exception as e:
                logger.exception(f"🗣️💥 Request Processor: Error: {e}")
        logger.info("🗣️🏁 Request Processor: Shutting down.")

    def on_first_audio_chunk_synthesize(self):
        """
        Callback method invoked by AudioProcessor when the first TTS audio chunk is ready.

        Sets the `quick_answer_first_chunk_ready` flag on the current `running_generation`
        if one exists. This flag might be used for fine-grained timing or state checks.
        """
        logger.info("🗣️🎶 First audio chunk synthesized. Setting TTS quick allowed event.")
        if self.running_generation:
            self.running_generation.quick_answer_first_chunk_ready = True

    def preprocess_chunk(self, chunk: str) -> str:
        """
        Preprocesses a text chunk before sending it to the TTS engine.

        Replaces specific characters (em-dashes, quotes, ellipsis) with simpler equivalents
        to potentially improve TTS pronunciation or compatibility.

        Args:
            chunk: The input text chunk.

        Returns:
            The preprocessed text chunk.
        """
        return chunk.replace("—", "-").replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'").replace("…", "...")

    def clean_quick_answer(self, text: str) -> str:
        """
        Removes specific leading patterns (like '<think>', newlines, spaces) from text.

        Intended for cleaning the initial output of the LLM, especially when `no_think`
        is enabled, to remove processing tags before TTS.

        Args:
            text: The input text.

        Returns:
            The text with specified leading patterns removed.
        """
        patterns_to_remove = ["<think>", "</think>", "\n", " "]
        previous_text = None
        current_text = text
        
        while previous_text != current_text:
            previous_text = current_text
            
            # Remove all patterns from the beginning of the string
            for pattern in patterns_to_remove:
                while current_text.startswith(pattern):
                    current_text = current_text[len(pattern):]
        
        return current_text

    def _llm_inference_worker(self):
        """
        Worker thread target that handles LLM inference for a generation.

        Waits for `generator_ready_event`. Once signaled, it iterates through the
        LLM generator provided in `running_generation`. It accumulates the generated
        text, optionally cleans it (`no_think`), checks for a natural sentence boundary
        to define the `quick_answer` using `TextContext`. If a quick answer is found,
        it signals `llm_answer_ready_event`. Handles stop requests (`stop_llm_request_event`)
        and signals completion/abortion via `stop_llm_finished_event` and internal flags.
        Runs until `shutdown_event` is set.
        """
        logger.info("🗣️🧠 LLM Worker: Starting...")
        while not self.shutdown_event.is_set():
            
            ready = self.generator_ready_event.wait(timeout=1.0)
            if not ready:
                continue

            # Check if aborted *while waiting* before clearing the ready event
            if self.stop_llm_request_event.is_set():
                logger.info("🗣️🧠❌ LLM Worker: Abort detected while waiting for generator_ready_event.")
                self.stop_llm_request_event.clear()
                self.stop_llm_finished_event.set()
                self.llm_generation_active = False
                continue # Go back to waiting

            self.generator_ready_event.clear()
            self.stop_everything_event.clear() # Assuming a new generation clears global stop
            current_gen = self.running_generation

            if not current_gen or not current_gen.llm_generator:
                logger.warning("🗣️🧠❓ LLM Worker: No valid generation or generator found after event.")
                self.llm_generation_active = False
                continue # Go back to waiting

            gen_id = current_gen.id
            logger.info(f"🗣️🧠🔄 [Gen {gen_id}] LLM Worker: Processing generation...")

            # Set state for active generation
            self.llm_generation_active = True
            self.stop_llm_finished_event.clear()
            start_time = time.time()
            token_count = 0

            try:
                for chunk in current_gen.llm_generator:
                    # Check for stop *before* processing the chunk
                    if self.stop_llm_request_event.is_set():
                        logger.info(f"🗣️🧠❌ [Gen {gen_id}] LLM Worker: Stop request detected during iteration.")
                        self.stop_llm_request_event.clear()
                        current_gen.llm_aborted = True
                        break # Exit the generator loop

                    chunk = self.preprocess_chunk(chunk)
                    token_count += 1
                    current_gen.quick_answer += chunk
                    if self.no_think:
                        current_gen.quick_answer = self.clean_quick_answer(current_gen.quick_answer)

                    if token_count == 1:
                        logger.info(f"🗣️🧠⏱️ [Gen {gen_id}] LLM Worker: TTFT: {(time.time() - start_time):.4f}s")

                    # Check for quick answer boundary only if not already provided
                    if not current_gen.quick_answer_provided:
                        context, overhang = self.text_context.get_context(current_gen.quick_answer)
                        if context:
                            logger.info(f"🗣️🧠✔️ [Gen {gen_id}] LLM Worker:  {Colors.apply('QUICK ANSWER FOUND:').magenta} {context}, overhang: {overhang}")
                            current_gen.quick_answer = context
                            if self.on_partial_assistant_text:
                                self.on_partial_assistant_text(current_gen.quick_answer)
                            current_gen.quick_answer_overhang = overhang
                            current_gen.quick_answer_provided = True
                            self.llm_answer_ready_event.set() # Signal TTS quick worker
                            break
                            # Do NOT break here, continue iterating to finish the full LLM response


                # Loop finished naturally or broke due to stop request
                logger.info(f"🗣️🧠🏁 [Gen {gen_id}] LLM Worker: Generator loop finished%s" % (" (Aborted)" if current_gen.llm_aborted else ""))

                # If loop finished naturally and no quick answer was ever found (e.g., short response)
                # Set the whole thing as the quick answer.
                if not current_gen.llm_aborted and not current_gen.quick_answer_provided:
                    logger.info(f"🗣️🧠✔️ [Gen {gen_id}] LLM Worker: No context boundary found, using full response as quick answer.")
                    # quick_answer already contains the full text
                    current_gen.quick_answer_provided = True # Mark as provided
                    if self.on_partial_assistant_text:
                        self.on_partial_assistant_text(current_gen.quick_answer)
                    self.llm_answer_ready_event.set() # Signal TTS quick worker

            except Exception as e:
                logger.exception(f"🗣️🧠💥 [Gen {gen_id}] LLM Worker: Error during generation: {e}")
                current_gen.llm_aborted = True # Mark as aborted on error
            finally:
                # Clean up state regardless of how the loop/try block exited
                self.llm_generation_active = False
                self.stop_llm_finished_event.set() # Signal that this worker's processing attempt is done

                if current_gen.llm_aborted:
                    # If LLM was aborted, ensure TTS (both quick and final) is also stopped
                    logger.info(f"🗣️🧠❌ [Gen {gen_id}] LLM Aborted, requesting TTS quick/final stop.")
                    self.stop_tts_quick_request_event.set()
                    self.stop_tts_final_request_event.set()
                    # Wake up TTS quick worker if it's waiting
                    self.llm_answer_ready_event.set()

                logger.info(f"🗣️🧠🏁 [Gen {gen_id}] LLM Worker: Finished processing cycle.")

                current_gen.llm_finished = True
                current_gen.llm_finished_event.set()

    def check_abort(self, txt: str, wait_for_finish: bool = True, abort_reason: str = "unknown") -> bool:
        """
        Checks if the current generation should be aborted based on new input text.

        Compares the provided text (`txt`) with the text of the `running_generation`.
        If a generation is running and not already aborting:
        1. If `txt` is very similar (>= 0.95 similarity) to the running generation's
           input text, it ignores the new request and returns False.
        2. If `txt` is different, it initiates an abort of the current generation
           by calling the public `abort_generation` method.

        If `wait_for_finish` is True, this method waits for the abortion process
        initiated by `abort_generation` to complete before returning.

        If a generation is already in the process of aborting when this method is called,
        it will wait (if `wait_for_finish` is True) for that ongoing abort to finish.

        Args:
            txt: The new text input to check against the current generation's input.
            wait_for_finish: Whether to block until the initiated/ongoing abort completes.
            abort_reason: A string describing why the abort check is being performed.

        Returns:
            True if an abortion was processed (either newly initiated or waited for),
            False if no active generation was found or the new text was too similar.
        """
        with self.check_abort_lock:
            if self.running_generation:
                current_gen_id_str = f"Gen {self.running_generation.id}"
                logger.info(f"🗣️🛑❓ {current_gen_id_str} Abort check requested (reason: {abort_reason})")

                if self.running_generation.abortion_started:
                    logger.info(f"🗣️🛑⏳ {current_gen_id_str} Active generation is already aborting, waiting to finish (if requested).")

                    # Only wait if wait_for_finish is True
                    if wait_for_finish:
                        start_time = time.time()
                        # Wait using the abort_completed_event for better synchronization
                        completed = self.abort_completed_event.wait(timeout=5.0) # Use the event from abort_generation

                        if not completed:
                             logger.error(f"🗣️🛑💥💥 {current_gen_id_str} Timeout waiting for ongoing abortion to complete. State inconsistency possible!")
                             # Force clear it just in case, though this indicates a deeper issue.
                             self.running_generation = None
                        elif self.running_generation is not None:
                            logger.error(f"🗣️🛑💥💥 {current_gen_id_str} Abortion completed event set, but running_generation still exists. State inconsistency likely!")
                            # Force clear it.
                            self.running_generation = None
                        else:
                            logger.info(f"🗣️🛑✅ {current_gen_id_str} Ongoing abortion finished.")
                    else:
                        logger.info(f"🗣️🛑🏃 {current_gen_id_str} Not waiting for ongoing abortion as wait_for_finish=False")

                    return True # An abort was processed (waited for)
                else:
                    # No abortion in progress, check similarity
                    logger.info(f"🗣️🛑🤔 {current_gen_id_str} Found active generation, checking text similarity.")
                    try:
                         # Ensure running_generation.text is not None before comparison
                        if self.running_generation.text is None:
                            logger.warning(f"🗣️🛑❓ {current_gen_id_str} Running generation text is None, cannot compare similarity. Assuming different.")
                            similarity = 0.0
                        else:
                            similarity = self.text_similarity.calculate_similarity(self.running_generation.text, txt)
                    except Exception as e:
                        logger.warning(f"🗣️🛑💥 {current_gen_id_str} Error calculating similarity: {e}. Assuming different.")
                        similarity = 0.0 # Assume different on error

                    if similarity >= 0.95:
                        logger.info(f"🗣️🛑🙅 {current_gen_id_str} Text ('{txt[:30]}...') too similar ({similarity:.2f}) to current '{self.running_generation.text[:30] if self.running_generation.text else 'None'}...'. Ignoring.")
                        return False # No abort needed

                    # Texts are different enough, initiate abort
                    logger.info(f"🗣️🛑🚀 {current_gen_id_str} Text ('{txt[:30]}...') different enough ({similarity:.2f}) from '{self.running_generation.text[:30] if self.running_generation.text else 'None'}...'. Requesting synchronous abort.")
                    start_time = time.time()
                    # Call the synchronous public abort method - THIS IS KEY
                    self.abort_generation(wait_for_completion=wait_for_finish, timeout=7.0, reason=f"check_abort found different text ({abort_reason})")

                    if wait_for_finish:
                         # Check state *after* waiting for the abort call
                        if self.running_generation is not None:
                            logger.error(f"🗣️🛑💥💥 {current_gen_id_str} !!! Abort call completed but running_generation is still not None. State inconsistency likely!")
                            # Force clear it.
                            self.running_generation = None
                        else:
                            logger.info(f"🗣️🛑✅ {current_gen_id_str} Synchronous abort completed in {time.time() - start_time:.2f}s.")

                    return True # An abort was processed (initiated)
            else:
                logger.info("🗣️🛑🤷 No active generation found during abort check.")
                return False # No active generation to abort

    def _tts_quick_inference_worker(self):
        """
        Worker thread target that handles TTS synthesis for the 'quick answer'.

        Waits for `llm_answer_ready_event`. Once signaled, it checks if the generation
        is valid and has a `quick_answer`. It then waits for the `tts_quick_allowed_event`
        (intended for potential rate limiting or timing control, currently seems unused).
        If allowed, it calls `audio.synthesize` with the `quick_answer`, feeding audio
        chunks into the `audio_chunks` queue. Handles stop requests
        (`stop_tts_quick_request_event`) and signals completion/abortion via
        `stop_tts_quick_finished_event` and internal flags. Runs until `shutdown_event` is set.
        """
        logger.info("🗣️👄🚀 Quick TTS Worker: Starting...")
        while not self.shutdown_event.is_set():
            ready = self.llm_answer_ready_event.wait(timeout=1.0)
            if not ready:
                continue

            # Check if aborted *while waiting* before clearing the ready event

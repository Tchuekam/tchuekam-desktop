# llm_module.py
import re
import logging
import os
import sys
import time
import json
import uuid
import subprocess # <-- Restored usage
from typing import Generator, List, Dict, Optional, Any
from threading import Lock

# --- Library Dependencies ---
try:
    import requests
    from requests import Session # Explicit import
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logging.warning("🤖⚠️ requests library not installed. Ollama backend (direct HTTP) will not function.")
    if sys.version_info >= (3, 9): Session = Any | None
    else: Session = Optional[Any]

try:
    from openai import OpenAI, APIError, APITimeoutError, RateLimitError, APIConnectionError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None
    class APIError(Exception): pass
    class APITimeoutError(APIError): pass
    class RateLimitError(APIError): pass
    class APIConnectionError(APIError): pass
    logging.warning("🤖⚠️ openai library not installed. OpenAI/LMStudio backends will not function.")

# Configure logging
# Use the root logger configured by the main application if available, else basic config
log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_str, logging.INFO)
# Check if root logger already has handlers (likely configured by main app)
if not logging.getLogger().handlers:
    logging.basicConfig(level=log_level,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        stream=sys.stdout) # Default to stdout if not configured
logger = logging.getLogger(__name__) # Get logger for this module
logger.setLevel(log_level) # Ensure module logger respects level

# --- Environment Variable Configuration ---
try:
    import importlib.util
    dotenv_spec = importlib.util.find_spec("dotenv")
    if dotenv_spec:
        from dotenv import load_dotenv
        load_dotenv()
        logger.debug("🤖⚙️ Loaded environment variables from .env file.")
    else:
        logger.debug("🤖⚙️ python-dotenv not installed, skipping .env load.")
except ImportError:
    logger.debug("🤖💥 Error importing dotenv, skipping .env load.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")

# --- Backend Client Creation/Check Functions ---
def _create_openai_client(api_key: Optional[str], base_url: Optional[str] = None) -> OpenAI:
    """
    Creates and configures an OpenAI API client instance.

    Handles API key logic (using a placeholder if none provided for local models)
    and optional base URL configuration. Sets default timeout and retries.

    Args:
        api_key: The OpenAI API key, or None if not required (e.g., for LMStudio).
        base_url: The base URL for the API endpoint (e.g., for LMStudio or custom deployments).

    Returns:
        An initialized OpenAI client instance.

    Raises:
        ImportError: If the 'openai' library is not installed.
        Exception: If client initialization fails for other reasons.
    """
    if not OPENAI_AVAILABLE:
        raise ImportError("openai library is required for this backend but not installed.")
    try:
        effective_key = api_key if api_key else "no-key-needed"
        client_args = {
            "api_key": effective_key,
            "timeout": 30.0,
            "max_retries": 2
        }
        if base_url:
            client_args["base_url"] = base_url

        client = OpenAI(**client_args)
        logger.info(f"🤖🔌 Prepared OpenAI-compatible client (Base URL: {base_url or 'Default'}).")
        return client
    except Exception as e:
        logger.error(f"🤖💥 Failed to initialize OpenAI client: {e}")
        raise

def _check_ollama_connection(base_url: str, session: Optional[Session]) -> bool:
    """
    Performs a quick HTTP GET request to check connectivity with an Ollama server.

    Uses the provided requests Session and base URL to attempt a connection.
    Logs success or specific connection errors.

    Args:
        base_url: The base URL of the Ollama server (e.g., "http://127.0.0.1:11434").
        session: An active requests.Session object to use for the check.

    Returns:
        True if the connection check is successful (HTTP 2xx status), False otherwise.
    """
    if not REQUESTS_AVAILABLE:
        logger.warning("🤖⚠️ Cannot check Ollama connection: requests library not installed.")
        return False
    if not session:
        logger.warning("🤖⚠️ Cannot check Ollama connection: requests session not provided.")
        return False
    try:
        base_check_url = base_url.rstrip('/')
        if not base_check_url.startswith(('http://', 'https://')):
             base_check_url = 'http://' + base_check_url
        check_endpoint = f"{base_check_url}/"
        logger.debug(f"🤖🔌 Checking Ollama connection via GET to {check_endpoint}...")
        # Use a shorter timeout for the check
        response = session.get(check_endpoint, timeout=5.0)
        response.raise_for_status()
        logger.info(f"🤖🔌 Successfully connected to Ollama server via HTTP at: {base_url}")
        return True
    except requests.exceptions.ConnectionError as e:
        # Log specific connection error, but return False for caller to handle
        logger.warning(f"🤖🔌❌ Connection Error checking Ollama at {base_url}: {e}")
        return False
    except requests.exceptions.Timeout:
        logger.warning(f"🤖🔌❌ Timeout checking Ollama connection at {base_url}.")
        return False
    except requests.exceptions.RequestException as e:
        logger.warning(f"🤖🔌❌ Error checking Ollama connection at {base_url}: {e}")
        return False
    except Exception as e:
        logger.error(f"🤖💥 Unexpected error during Ollama connection check: {e}")
        return False

# --- Restored _run_ollama_ps function ---
def _run_ollama_ps():
    """
    Attempts to run the 'ollama ps' command via subprocess.

    This is used as a potential fallback diagnostic/recovery step if the initial
    HTTP connection check to the Ollama server fails. It assumes the `ollama` CLI
    is installed and in the system PATH.

    Returns:
        True if the command executes successfully (exit code 0), False otherwise
        (command not found, execution error, timeout).
    """
    try:
        logger.info("🤖🩺 Attempting to run 'ollama ps' to check server status...")
        # Added timeout to prevent hanging indefinitely
        result = subprocess.run(["ollama", "ps"], check=True, capture_output=True, text=True, timeout=10.0)
        logger.info(f"🤖🩺 'ollama ps' executed successfully. Output:\n{result.stdout.strip()}")
        return True
    except FileNotFoundError:
        logger.error("🤖💥 'ollama ps' command not found. Make sure Ollama is installed and in your PATH.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"🤖💥 'ollama ps' command failed with exit code {e.returncode}:")
        if e.stderr:
            logger.error(f"   stderr: {e.stderr.strip()}")
        if e.stdout: # Log stdout even on error, might contain info
            logger.error(f"   stdout: {e.stdout.strip()}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("🤖💥 'ollama ps' command timed out after 10 seconds.")
        return False
    except Exception as e:
        logger.error(f"🤖💥 An unexpected error occurred while running 'ollama ps': {e}")
        return False

# --- LLM Class ---
class LLM:
    """
    Provides a unified interface for interacting with various LLM backends.

    Supports Ollama (via direct HTTP), OpenAI API, and LMStudio (via OpenAI-compatible API).
    Handles client initialization, streaming generation, request cancellation,
    system prompts, and basic connection management including an optional `ollama ps` check.
    """
    SUPPORTED_BACKENDS = ["ollama", "openai", "lmstudio"]

    def __init__(
        self,
        backend: str,
        model: str,
        system_prompt: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        no_think: bool = False,
    ):
        """
        Initializes the LLM interface for a specific backend and model.

        Args:
            backend: The name of the LLM backend to use (e.g., "ollama", "openai", "lmstudio").
            model: The identifier for the specific model to use within the backend.
            system_prompt: An optional system prompt to prepend to conversations.
            api_key: API key, primarily for OpenAI backend (can be omitted for others if not needed).
            base_url: Optional base URL for the backend API (overrides defaults/env vars).
            no_think: Experimental flag (currently unused in core logic, intended for future prompt modification).

        Raises:
            ValueError: If an unsupported backend is specified.
            ImportError: If required libraries for the selected backend are not installed.
        """
        logger.info(f"🤖⚙️ Initializing LLM with backend: {backend}, model: {model}, system_prompt: {system_prompt}")
        self.backend = backend.lower()
        if self.backend not in self.SUPPORTED_BACKENDS:
            raise ValueError(f"Unsupported backend '{backend}'. Supported: {self.SUPPORTED_BACKENDS}")

        if self.backend == "ollama" and not REQUESTS_AVAILABLE:
             raise ImportError("requests library is required for the 'ollama' backend but not installed.")
        if self.backend in ["openai", "lmstudio"] and not OPENAI_AVAILABLE:
             raise ImportError("openai library is required for the 'openai'/'lmstudio' backends but not installed.")

        self.model = model
        self.system_prompt = system_prompt
        self._api_key = api_key
        self._base_url = base_url
        self.no_think = no_think # Not used yet, but kept for future use

        self.client: Optional[OpenAI] = None
        self.ollama_session: Optional[Session] = None
        self._client_initialized: bool = False
        self._client_init_lock = Lock()
        self._active_requests: Dict[str, Dict[str, Any]] = {}
        self._requests_lock = Lock()
        self._ollama_connection_ok: bool = False # Added explicit init

        logger.info(f"🤖⚙️ Configuring LLM instance: backend='{self.backend}', model='{self.model}'")

        self.effective_openai_key = self._api_key or OPENAI_API_KEY
        self.effective_ollama_url = self._base_url or OLLAMA_BASE_URL if self.backend == "ollama" else None
        self.effective_lmstudio_url = self._base_url or LMSTUDIO_BASE_URL if self.backend == "lmstudio" else None
        self.effective_openai_base_url = self._base_url if self.backend == "openai" and self._base_url else None

        if self.backend == "ollama" and self.effective_ollama_url:
             url = self.effective_ollama_url
             if not url.startswith(('http://', 'https://')):
                  url = 'http://' + url
             url = url.replace('/api/chat', '').replace('/api/generate', '').rstrip('/')
             self.effective_ollama_url = url
             logger.debug(f"🤖⚙️ Normalized Ollama URL: {self.effective_ollama_url}")

        if self.backend == "ollama" and REQUESTS_AVAILABLE:
            self.ollama_session = requests.Session()
            logger.info("🤖🔌 Initialized requests.Session for Ollama backend.")

        self.system_prompt_message = None
        if self.system_prompt:
            self.system_prompt_message = {"role": "system", "content": self.system_prompt}
            logger.info(f"🤖💬 System prompt set.")

    def _lazy_initialize_clients(self) -> bool:
        """
        Initializes backend clients or checks connections on first use (thread-safe).

        Creates the appropriate HTTP client (OpenAI SDK or requests.Session) and performs
        an initial connection check for Ollama. If the Ollama check fails, optionally
        attempts to run `ollama ps` as a fallback before retrying the connection check.

        Returns:
            True if the client is initialized and ready (or connection check passed for Ollama),
            False otherwise.
        """
        if self._client_initialized:
            if self.backend in ["openai", "lmstudio"]: return self.client is not None
            if self.backend == "ollama": return self.ollama_session is not None and self._ollama_connection_ok # Check flag
            return False

        with self._client_init_lock:
            if self._client_initialized: # Double check
                if self.backend in ["openai", "lmstudio"]: return self.client is not None
                if self.backend == "ollama": return self.ollama_session is not None and self._ollama_connection_ok
                return False

            logger.debug(f"🤖🔄 Lazy initializing/checking connection for backend: {self.backend}")
            init_ok = False
            self._ollama_connection_ok = False # Reset Ollama specific flag

            try:
                if self.backend == "openai":
                    self.client = _create_openai_client(self.effective_openai_key, base_url=self.effective_openai_base_url)
                    init_ok = self.client is not None
                elif self.backend == "lmstudio":
                    self.client = _create_openai_client(api_key="lmstudio-key", base_url=self.effective_lmstudio_url)
                    init_ok = self.client is not None
                elif self.backend == "ollama":
                    if self.ollama_session and self.effective_ollama_url:
                        # Initial direct check
                        initial_check_ok = _check_ollama_connection(self.effective_ollama_url, self.ollama_session)
                        if initial_check_ok:
                            init_ok = True
                            self._ollama_connection_ok = True
                        else:
                            # --- Restored ollama ps fallback logic ---
                            logger.warning(f"🤖🔌 Initial Ollama connection check failed for {self.effective_ollama_url}. Attempting 'ollama ps' fallback.")
                            if _run_ollama_ps():
                                # ollama ps ran, wait a bit and try connecting again
                                logger.info("🤖⏳ 'ollama ps' succeeded, waiting 3 seconds before re-checking connection...")
                                time.sleep(3)
                                second_check_ok = _check_ollama_connection(self.effective_ollama_url, self.ollama_session)
                                if second_check_ok:
                                    logger.info("🤖🔌✅ Ollama connection successful after running 'ollama ps'.")
                                    init_ok = True
                                    self._ollama_connection_ok = True
                                else:
                                    logger.error(f"🤖💥 Ollama connection check still failed after running 'ollama ps'.")
                                    init_ok = False # Explicitly set to false
                            else:
                                # ollama ps command failed or was not found
                                logger.error(f"🤖💥 'ollama ps' command failed or not found. Cannot verify/start server. Initialization failed for {self.effective_ollama_url}.")
                                init_ok = False # Explicitly set to false
                            # --- End of restored logic ---
                    else:
                        logger.error("🤖💥 Ollama session object is None or URL not set during lazy init.")
                        init_ok = False

                if init_ok:
                    logger.info(f"🤖✅ Client/Connection initialized successfully for backend: {self.backend}.")
                else:
                    logger.error(f"🤖💥 Initialization failed for backend: {self.backend}.")
            except Exception as e:
                logger.exception(f"🤖💥 Critical failure during lazy initialization for {self.backend}: {e}")
                init_ok = False
            finally:
                # Mark as initialized regardless of success/failure
                self._client_initialized = True
                # Ensure connection flag reflects reality if init failed
                if self.backend == "ollama" and not init_ok:
                    self._ollama_connection_ok = False

            return init_ok


    def cancel_generation(self, request_id: Optional[str] = None) -> bool:
        """
        Requests cancellation of active generation streams.

        If `request_id` is provided, cancels that specific stream.
        If `request_id` is None, attempts to cancel all currently active streams.
        Cancellation involves removing the request from tracking and attempting to
        close the underlying network stream/response object.

        Args:
            request_id: The unique ID of the generation request to cancel, or None to cancel all.

        Returns:
            True if at least one request cancellation was attempted, False otherwise.
        """
        cancelled_any = False
        with self._requests_lock:
            ids_to_cancel = []
            if request_id is None:
                if not self._active_requests:
                    logger.debug("🤖🗑️ Cancel all requested, but no active requests found.")
                    return False
                logger.info(f"🤖🗑️ Attempting to cancel ALL active generation requests ({len(self._active_requests)}).")
                ids_to_cancel = list(self._active_requests.keys())
            else:
                if request_id not in self._active_requests:
                    logger.warning(f"🤖🗑️ Cancel requested for ID '{request_id}', but it's not an active request.")
                    return False
                logger.info(f"🤖🗑️ Attempting to cancel generation request: {request_id}")
                ids_to_cancel.append(request_id)

            # Perform the cancellation
            for req_id in ids_to_cancel:
                # Call the internal cancellation method which now tries to close the stream
                if self._cancel_single_request_unsafe(req_id):
                    cancelled_any = True
        return cancelled_any

    def _cancel_single_request_unsafe(self, request_id: str) -> bool:
        """
        Internal helper to handle cancellation for a single request (thread-unsafe).

        Removes the request data from the `_active_requests` dictionary and attempts
        to call the `close()` method on the associated stream/response object, if available.
        Must be called while holding `_requests_lock`.

        Args:
            request_id: The unique ID of the request to cancel.

        Returns:
            True if the request was found and removal/close attempt was made, False otherwise.
        """
        request_data = self._active_requests.pop(request_id, None)
        if not request_data:
            # This might happen if it finished or was cancelled concurrently
            logger.debug(f"🤖🗑️ Request {request_id} already removed before cancellation attempt.")
            return False

        request_type = request_data.get("type", "unknown")
        stream_obj = request_data.get("stream")
        logger.debug(f"🤖🗑️ Cancelling request {request_id} (type: {request_type}). Stream object: {type(stream_obj)}")

        # --- Attempt to close the underlying stream/response ---
        if stream_obj:
            try:
                # Check if it has a close method and call it
                if hasattr(stream_obj, 'close') and callable(stream_obj.close):
                    logger.debug(f"🤖🗑️ [{request_id}] Attempting to close stream/response object...")
                    stream_obj.close()
                    logger.info(f"🤖🗑️ Closed stream/response for cancelled request {request_id}.")
                else:
                    logger.warning(f"🤖⚠️ [{request_id}] Stream object of type {type(stream_obj)} does not have a callable 'close' method. Cannot explicitly close.")
            except Exception as e:
                # Log error during close but continue - the request is still removed from tracking
                logger.error(f"🤖💥 Error closing stream/response for request {request_id}: {e}", exc_info=False)
        else:
             logger.warning(f"🤖⚠️ [{request_id}] No stream object found in request data to close.")

        # Log the removal from tracking
        logger.info(f"🤖🗑️ Removed generation request {request_id} from tracking (close attempted).")
        return True # Indicate removal occurred

    def _register_request(self, request_id: str, request_type: str, stream_obj: Optional[Any]):
        """
        Registers an active generation stream for cancellation tracking (thread-safe).

        Stores the request ID, type, stream object, and start time internally.

        Args:
            request_id: The unique ID for the generation request.
            request_type: The backend type (e.g., "openai", "ollama").
            stream_obj: The underlying stream/response object associated with the request.
        """
        with self._requests_lock:
            if request_id in self._active_requests:
                logger.warning(f"🤖⚠️ Request ID {request_id} already registered. Overwriting.")
            self._active_requests[request_id] = {
                "type": request_type,
                "stream": stream_obj,
                "start_time": time.time()
            }
            logger.debug(f"🤖ℹ️ Registered active request: {request_id} (Type: {request_type}, Stream: {type(stream_obj)}, Count: {len(self._active_requests)})")

    def cleanup_stale_requests(self, timeout_seconds: int = 300):
        """
        Finds and attempts to cancel requests older than the specified timeout.

        Iterates through active requests and calls `cancel_generation` for any
        request whose start time exceeds the timeout duration.

        Args:
            timeout_seconds: The maximum age in seconds before a request is considered stale.

        Returns:
            The number of stale requests for which cancellation was attempted.
        """
        stale_ids = []
        now = time.time()
        # Find stale IDs without holding lock for too long
        with self._requests_lock:
            stale_ids = [
                req_id for req_id, req_data in self._active_requests.items()
                if (now - req_data.get("start_time", 0)) > timeout_seconds
            ]

        if stale_ids:
            logger.info(f"🤖🧹 Found {len(stale_ids)} potentially stale requests (>{timeout_seconds}s). Cleaning up...")
            cleaned_count = 0
            for req_id in stale_ids:
                # cancel_generation handles locking internally and now attempts to close stream
                if self.cancel_generation(req_id):
                    cleaned_count += 1
            logger.info(f"🤖🧹 Cleaned up {cleaned_count}/{len(stale_ids)} stale requests (attempted stream close).")
            return cleaned_count
        return 0

    def prewarm(self, max_retries: int = 1) -> bool:
        """
        Attempts to "prewarm" the LLM connection and potentially load the model.

        Runs a simple, short generation task ("Respond with only the word 'OK'.")
        to trigger lazy initialization (including potential `ollama ps` check)
        and ensure the backend is responsive before actual use. Includes basic retry logic.

        Args:
            max_retries: The number of times to retry the generation task if a
                         connection/timeout error occurs (0 means one attempt total).

        Returns:
            True if the prewarm generation completed successfully (even with no content),
            False if initialization or generation failed after retries.
        """
        prompt = "Respond with only the word 'OK'."
        logger.info(f"🤖🔥 Attempting prewarm for '{self.model}' on backend '{self.backend}'...")

        # Lazy initialization now includes the 'ollama ps' logic if needed
        if not self._lazy_initialize_clients():
            logger.error("🤖🔥💥 Prewarm failed: Could not initialize backend client/connection.")
            return False

        attempts = 0
        last_error = None
        while attempts <= max_retries:
            prewarm_start_time = time.time()
            prewarm_request_id = f"prewarm-{self.backend}-{uuid.uuid4()}"
            generator = None
            full_response = ""
            token_count = 0
            first_token_time = None

            try:
                logger.info(f"🤖🔥 Prewarm Attempt {attempts + 1}/{max_retries+1} calling generate (ID: {prewarm_request_id})...")
                generator = self.generate(
                    text=prompt,
                    history=None,
                    use_system_prompt=True,
                    request_id=prewarm_request_id,
                    temperature=0.1
                )

                gen_start_time = time.time()
                # Consume the generator fully
                for token in generator:
                    if first_token_time is None:
                        first_token_time = time.time()
                        logger.info(f"🤖🔥⏱️ Prewarm TTFT: {(first_token_time - gen_start_time):.4f}s")
                    full_response += token
                    token_count += 1
                # End of loop means generator is exhausted
                gen_end_time = time.time()
                logger.info(f"🤖🔥ℹ️ Prewarm consumed {token_count} tokens in {(gen_end_time - gen_start_time):.4f}s. Full response: '{full_response}'")

                if token_count == 0 and not full_response:
                     logger.warning(f"🤖🔥⚠️ Prewarm yielded no response content, but generation finished.")
                # else: pass # If we got content, great.

                prewarm_end_time = time.time()
                logger.info(f"🤖🔥✅ Prewarm successful (generation finished naturally). Total time: {(prewarm_end_time - prewarm_start_time):.4f}s.")
                return True

            except (APIConnectionError, requests.exceptions.ConnectionError, ConnectionError, TimeoutError, APITimeoutError, requests.exceptions.Timeout) as e:
                last_error = e
                logger.warning(f"🤖🔥⚠️ Prewarm attempt {attempts + 1}/{max_retries+1} connection/timeout error during generation: {e}")
                if attempts < max_retries:
                    attempts += 1
                    wait_time = 2 * attempts
                    logger.info(f"🤖🔥🔄 Retrying prewarm generation in {wait_time}s...")
                    time.sleep(wait_time)
                    # Force re-check on next attempt via lazy_init in generate()
                    # Crucially, setting this False forces _lazy_initialize_clients to run again
                    # which will re-attempt the connection check AND the `ollama ps` fallback if needed.
                    self._client_initialized = False
                    logger.debug("🤖🔥🔄 Resetting client initialized flag to force re-check on retry.")
                    continue
                else:
                    logger.error(f"🤖🔥💥 Prewarm failed permanently after {attempts + 1} generation attempts due to connection issues.")
                    return False
            except (APIError, RateLimitError, requests.exceptions.RequestException, RuntimeError) as e:
                last_error = e
                logger.error(f"🤖🔥💥 Prewarm attempt {attempts + 1}/{max_retries+1} API/Request/Runtime error: {e}")
                if isinstance(e, ConnectionError) and "connection failed" in str(e):
                     logger.error("   (This likely indicates the initial lazy initialization failed its connection check or `ollama ps` fallback)")
                elif isinstance(e, RuntimeError) and "client failed" in str(e):
                    logger.error("   (This might indicate the initial lazy initialization failed)")
                return False # Non-connection errors are usually fatal for prewarm
            except Exception as e:
                last_error = e
                logger.exception(f"🤖🔥💥 Prewarm attempt {attempts + 1}/{max_retries+1} unexpected error.")
                return False
            finally:
                # Generate's finally block handles tracking cleanup.
                # Explicitly try closing generator here in case of error mid-stream.
                logger.debug(f"🤖🔥ℹ️ [{prewarm_request_id}] Prewarm attempt finished. generate()'s finally handles tracking cleanup.")
                if generator is not None and hasattr(generator, 'close'):
                    try:
                        generator.close()
                    except Exception as close_err:
                         logger.warning(f"🤖🔥⚠️ [{prewarm_request_id}] Error closing generator in prewarm finally: {close_err}", exc_info=False)
                generator = None # Clear local ref

            if attempts >= max_retries:
                break # Exit loop if max_retries reached without success

        logger.error(f"🤖🔥💥 Prewarm failed after exhausting retries. Last error: {last_error}")
        return False

    def generate(
        self,
        text: str,
        history: Optional[List[Dict[str, str]]] = None,
        use_system_prompt: bool = True,
        request_id: Optional[str] = None,
        **kwargs: Any
    ) -> Generator[str, None, None]:
        """
        Generates text using the configured backend, yielding tokens as a stream.

        Handles lazy initialization (including potential `ollama ps` check), message formatting,
        backend-specific API calls, stream registration, token yielding, and resource cleanup.

        Args:
            text: The user's input prompt/text.
            history: An optional list of previous messages (dicts with "role" and "content").
            use_system_prompt: If True, prepends the configured system prompt (if any).
            request_id: An optional unique ID for this generation request. If None, one is generated.
            **kwargs: Additional backend-specific keyword arguments (e.g., temperature, top_p, stop sequences).

        Yields:
            str: Individual tokens (or small chunks of text) as they are generated by the LLM.

        Raises:
            RuntimeError: If the backend client fails to initialize.
            ConnectionError: If communication with the backend fails (initial connection or during streaming).
            ValueError: If configuration is invalid (e.g., missing Ollama URL).
            APIError: For backend-specific API errors (OpenAI/LMStudio).
            RateLimitError: For backend-specific rate limit errors (OpenAI/LMStudio).
            requests.exceptions.RequestException: For Ollama HTTP request errors.
            Exception: For other unexpected errors during the generation process.
        """
        # Lazy initialization now includes the 'ollama ps' logic if needed
        if not self._lazy_initialize_clients():
            # Provide a clearer error if initialization failed
            if self.backend == "ollama" and not self._ollama_connection_ok:
                 raise ConnectionError(f"LLM backend '{self.backend}' connection failed. Could not connect to {self.effective_ollama_url} even after attempting 'ollama ps'. Check server status and configuration.")
            raise RuntimeError(f"LLM backend '{self.backend}' client failed to initialize.")

        req_id = request_id if request_id else f"{self.backend}-{uuid.uuid4()}"
        logger.info(f"🤖💬 Starting generation (Request ID: {req_id})")

        messages = []
        if use_system_prompt and self.system_prompt_message:

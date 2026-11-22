"""Local MbowaGPT runtime manager wrapping llama-server and Ollama discovery.

Manages the three MbowaGPT specialist intelligence identities under a single
memory-safe local inference runtime:

1. ``mbowagpt`` — Main conversational & coordination model
2. ``mbowagpt-cybertrunk`` — Technical operations, code, diagnostics, cyber defense
3. ``mbowagpt-relentless`` — Persistent multi-step execution & follow-through

On memory-constrained CPU hosts (for example 8 GB RAM laptops), only a single
``llama-server`` child process runs at a time and weights are hot-swapped
cleanly when a specialist role resolves to a different ``.gguf`` file.
Already-installed GGUF weights under ``%LOCALAPPDATA%\\hermes\\business-agent\\models``
or ``~/.hermes/models/mbowagpt`` are discovered automatically so offline mode
works immediately with zero mandatory downloads.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MBOWAGPT_AUTO_MODEL_ID = "mbowagpt-auto"


@dataclass(frozen=True)
class MbowaGPTModelSpec:
    id: str
    display_name: str
    role_title: str
    description: str
    recommended_hf_repo: str
    recommended_filename: str
    recommended_url: str
    recommended_size_mb: int
    fallback_filenames: Tuple[str, ...] = field(default_factory=tuple)


MBOWAGPT_MODELS: Dict[str, MbowaGPTModelSpec] = {
    "mbowagpt": MbowaGPTModelSpec(
        id="mbowagpt",
        display_name="MbowaGPT",
        role_title="Primary Conversational Intelligence",
        description=(
            "General reasoning, natural conversation, contextual memory, "
            "and cross-specialist coordination."
        ),
        recommended_hf_repo="unsloth/Qwen3-1.7B-GGUF",
        recommended_filename="Qwen3-1.7B-Q4_K_M.gguf",
        recommended_url=(
            "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/"
            "Qwen3-1.7B-Q4_K_M.gguf?download=true"
        ),
        recommended_size_mb=1107,
        fallback_filenames=(
            "Qwen3-1.7B-Q4_K_M.gguf",
            "Qwen3-0.6B-Q4_K_M.gguf",
            "SmolLM2-360M-Instruct-Q4_K_M.gguf",
        ),
    ),
    "mbowagpt-cybertrunk": MbowaGPTModelSpec(
        id="mbowagpt-cybertrunk",
        display_name="MbowaGPT Cybertrunk",
        role_title="Technical Operations & Cyber Intelligence",
        description=(
            "Code understanding, debugging, infrastructure diagnostics, "
            "and defensive cybersecurity analysis."
        ),
        recommended_hf_repo="Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF",
        recommended_filename="qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
        recommended_url=(
            "https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF/resolve/main/"
            "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf?download=true"
        ),
        recommended_size_mb=986,
        fallback_filenames=(
            "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            "Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf",
            "Qwen3-1.7B-Q4_K_M.gguf",
            "Qwen3-0.6B-Q4_K_M.gguf",
            "SmolLM2-360M-Instruct-Q4_K_M.gguf",
        ),
    ),
    "mbowagpt-relentless": MbowaGPTModelSpec(
        id="mbowagpt-relentless",
        display_name="MbowaGPT Relentless",
        role_title="Autonomous Execution & Follow-Through",
        description=(
            "Persistent task completion, multi-step operational workflows, "
            "verification checklists, and reliable follow-through."
        ),
        recommended_hf_repo="unsloth/Qwen3-1.7B-GGUF",
        recommended_filename="Qwen3-1.7B-Q4_K_M.gguf",
        recommended_url=(
            "https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/"
            "Qwen3-1.7B-Q4_K_M.gguf?download=true"
        ),
        recommended_size_mb=1107,
        fallback_filenames=(
            "Qwen3-1.7B-Q4_K_M.gguf",
            "Qwen3-0.6B-Q4_K_M.gguf",
            "SmolLM2-360M-Instruct-Q4_K_M.gguf",
        ),
    ),
}

_MODEL_ALIASES: Dict[str, str] = {
    "mbowagpt": "mbowagpt",
    "mbowagpt-main": "mbowagpt",
    "main": "mbowagpt",
    "default": "mbowagpt",
    "mbowagpt-auto": MBOWAGPT_AUTO_MODEL_ID,
    "auto": MBOWAGPT_AUTO_MODEL_ID,
    "local": MBOWAGPT_AUTO_MODEL_ID,
    "mbowagpt-cybertrunk": "mbowagpt-cybertrunk",
    "cybertrunk": "mbowagpt-cybertrunk",
    "cyber": "mbowagpt-cybertrunk",
    "mbowagpt-relentless": "mbowagpt-relentless",
    "relentless": "mbowagpt-relentless",
}


def canonicalize_mbowagpt_model(model_id: Optional[str]) -> str:
    """Normalize any MbowaGPT model id/alias to canonical identifier."""
    raw = (model_id or "").strip().lower()
    if not raw:
        return MBOWAGPT_AUTO_MODEL_ID
    if raw.startswith("mbowagpt/"):
        raw = raw.split("/", 1)[1]
    return _MODEL_ALIASES.get(raw, "mbowagpt" if raw.startswith("mbowagpt") else raw)


def is_mbowagpt_model(model_id: Optional[str]) -> bool:
    raw = (model_id or "").strip().lower()
    if raw.startswith("mbowagpt/"):
        raw = raw.split("/", 1)[1]
    return raw in _MODEL_ALIASES or raw in MBOWAGPT_MODELS or raw == MBOWAGPT_AUTO_MODEL_ID


def detect_hardware_profile() -> Dict[str, Any]:
    """Detect RAM and CPU core count to size context/KV cache safely."""
    cpu_count = os.cpu_count() or 4
    total_ram_bytes = 0

    try:
        if os.name == "nt":
            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_ram_bytes = int(stat.ullTotalPhys)
        elif Path("/proc/meminfo").exists():
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    total_ram_bytes = kb * 1024
                    break
        elif platform.system() == "Darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=2).strip()
            total_ram_bytes = int(out)
    except Exception:
        total_ram_bytes = 8 * 1024 ** 3

    if total_ram_bytes <= 0:
        total_ram_bytes = 8 * 1024 ** 3

    ram_gb = round(total_ram_bytes / (1024 ** 3), 1)
    if ram_gb < 5.0:
        ctx_size = 2048
    elif ram_gb <= 9.0:
        ctx_size = 4096
    else:
        ctx_size = 8192

    recommended_threads = max(2, min(cpu_count - 1 if cpu_count > 2 else cpu_count, 6))
    return {
        "ram_gb": ram_gb,
        "cpu_count": cpu_count,
        "recommended_ctx_size": ctx_size,
        "recommended_threads": recommended_threads,
        "gpu_layers": 0,
    }


def _find_free_port(preferred: int = 18080) -> int:
    for port in (preferred, 18081, 18082, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return int(s.getsockname()[1])
        except OSError:
            continue
    raise RuntimeError("No free loopback port available for local llama-server")


@dataclass
class LocalRuntimeEndpoint:
    base_url: str
    api_key: str
    model_id: str
    served_model: str
    weights_path: str
    backend: str = "llama-server"
    ctx_size: int = 4096


class LocalRuntimeManager:
    """Single-process hot-swapping local LLM orchestrator for MbowaGPT."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen[Any]] = None
        self._port: Optional[int] = None
        self._active_weights: Optional[str] = None
        self._active_role: Optional[str] = None
        self._active_served_model: Optional[str] = None
        self._active_ctx_size: int = 4096
        self._stderr_log_path: Optional[Path] = None
        self._download_state: Dict[str, Any] = {}
        self._hardware: Optional[Dict[str, Any]] = None
        self._supports_reasoning_flag: Optional[bool] = None

    @property
    def hardware(self) -> Dict[str, Any]:
        if self._hardware is None:
            self._hardware = detect_hardware_profile()
        return self._hardware

    def _candidate_base_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        seen: set[str] = set()

        def _add(p: Optional[str | Path]) -> None:
            if not p:
                return
            try:
                resolved = Path(p).expanduser()
            except Exception:
                return
            key = str(resolved).lower()
            if key not in seen:
                seen.add(key)
                dirs.append(resolved)

        _add(os.getenv("HERMES_LOCAL_AI_DIR"))
        try:
            from hermes_constants import get_hermes_home

            home = Path(get_hermes_home())
            _add(home / "local-ai")
            _add(home / "business-agent")
            _add(home)
        except Exception:
            pass

        localappdata = os.getenv("LOCALAPPDATA")
        if localappdata:
            _add(Path(localappdata) / "hermes" / "local-ai")
            _add(Path(localappdata) / "hermes" / "business-agent")
            _add(Path(localappdata) / "hermes")

        _add(Path.home() / ".hermes" / "local-ai")
        _add(Path.home() / ".hermes")
        return dirs

    def get_writable_models_dir(self) -> Path:
        env_dir = os.getenv("HERMES_LOCAL_AI_DIR")
        if env_dir:
            target = Path(env_dir).expanduser() / "models"
        else:
            try:
                from hermes_constants import get_hermes_home

                target = Path(get_hermes_home()) / "models" / "mbowagpt"
            except Exception:
                target = Path.home() / ".hermes" / "models" / "mbowagpt"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def discover_binary(self) -> Optional[Path]:
        exe_names = ("llama-server.exe", "llama-server") if os.name == "nt" else ("llama-server",)
        for base in self._candidate_base_dirs():
            for rel in ("runtime", "bin", ""):
                for name in exe_names:
                    cand = (base / rel / name) if rel else (base / name)
                    if cand.is_file():
                        return cand
        for name in exe_names:
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    def _model_search_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        seen: set[str] = set()
        for base in self._candidate_base_dirs():
            for sub in ("models", "models/mbowagpt", "mbowagpt"):
                cand = base / sub
                key = str(cand).lower()
                if key not in seen and cand.is_dir():
                    seen.add(key)
                    dirs.append(cand)
        return dirs

    def discover_installed_ggufs(self) -> Dict[str, Path]:
        """Return mapping of lowercase filename -> Path for non-empty local GGUFs."""
        found: Dict[str, Path] = {}
        for folder in self._model_search_dirs():
            try:
                for item in folder.rglob("*.gguf"):
                    try:
                        if item.is_file() and item.stat().st_size > 1_000_000:
                            key = item.name.lower()
                            if key not in found:
                                found[key] = item
                    except OSError:
                        continue
            except OSError:
                continue
        return found

    def _load_role_overrides(self) -> Dict[str, Any]:
        try:
            from hermes_cli.config import load_config

            cfg = load_config()
            intel = cfg.get("intelligence") if isinstance(cfg, dict) else {}
            models_cfg = intel.get("local_models") if isinstance(intel, dict) else {}
            return dict(models_cfg) if isinstance(models_cfg, dict) else {}
        except Exception:
            return {}

    def resolve_model_weights(self, role_id: str) -> Optional[Path]:
        role = canonicalize_mbowagpt_model(role_id)
        if role == MBOWAGPT_AUTO_MODEL_ID:
            role = "mbowagpt"
        spec = MBOWAGPT_MODELS.get(role) or MBOWAGPT_MODELS["mbowagpt"]

        overrides = self._load_role_overrides()
        override_val = overrides.get(role)
        if isinstance(override_val, str) and override_val.strip():
            cand = Path(override_val).expanduser()
            if cand.is_file():
                return cand

        installed = self.discover_installed_ggufs()
        for preferred in spec.fallback_filenames:
            match = installed.get(preferred.lower())
            if match is not None:
                return match

        # Cybertrunk fallback prefers coder models if any GGUF has "coder" in name
        if role == "mbowagpt-cybertrunk":
            for fname, path in installed.items():
                if "coder" in fname:
                    return path

        # Ultimate fallback: any larger Qwen/Llama/Smol GGUF on disk
        if installed:
            return max(installed.values(), key=lambda p: p.stat().st_size)
        return None

    def probe_ollama(self, timeout: float = 0.4) -> List[str]:
        base = (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"http://{base}"
        try:
            req = urllib.request.Request(f"{base}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                models = data.get("models") or []
                return [str(m.get("name")) for m in models if isinstance(m, dict) and m.get("name")]
        except Exception:
            return []

    def is_local_available(self) -> bool:
        if self.discover_binary() is not None and bool(self.discover_installed_ggufs()):
            return True
        if self.probe_ollama(timeout=0.35):
            return True
        return False

    def _get_log_path(self) -> Path:
        try:
            from hermes_constants import get_hermes_home

            return Path(get_hermes_home()) / "logs" / "llama-server.log"
        except Exception:
            return Path.home() / ".hermes" / "logs" / "llama-server.log"

    def _is_proc_alive_locked(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _check_llama_health(self, port: int, timeout: float = 1.0) -> bool:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def _probe_supports_reasoning_flag(self, binary: Path) -> bool:
        if self._supports_reasoning_flag is not None:
            return self._supports_reasoning_flag
        try:
            kwargs: Dict[str, Any] = {
                "capture_output": True,
                "text": True,
                "timeout": 4,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            res = subprocess.run([str(binary), "--help"], **kwargs)
            help_text = (res.stdout or "") + (res.stderr or "")
            self._supports_reasoning_flag = "--reasoning" in help_text
        except Exception:
            self._supports_reasoning_flag = False
        return self._supports_reasoning_flag

    def _terminate_proc_locked(self) -> None:
        proc = self._proc
        self._proc = None
        self._port = None
        self._active_weights = None
        self._active_role = None
        self._active_served_model = None
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
        except Exception as exc:
            logger.debug("Ignoring llama-server shutdown error: %s", exc)

    def unload(self) -> None:
        """Stop the active llama-server process cleanly."""
        with self._lock:
            self._terminate_proc_locked()

    def ensure_started(self, role_id: str = "mbowagpt", *, timeout: float = 45.0) -> LocalRuntimeEndpoint:
        """Ensure the local model for *role_id* is ready and return its OpenAI endpoint."""
        role = canonicalize_mbowagpt_model(role_id)
        if role == MBOWAGPT_AUTO_MODEL_ID:
            role = "mbowagpt"

        binary = self.discover_binary()
        weights = self.resolve_model_weights(role)

        if binary is not None and weights is not None:
            weights_resolved = str(weights.resolve())
            with self._lock:
                if (
                    self._is_proc_alive_locked()
                    and self._active_weights == weights_resolved
                    and self._port is not None
                    and self._check_llama_health(self._port, timeout=1.0)
                ):
                    self._active_role = role
                    return LocalRuntimeEndpoint(
                        base_url=f"http://127.0.0.1:{self._port}/v1",
                        api_key="local-mbowagpt",
                        model_id=role,
                        served_model=self._active_served_model or weights.stem,
                        weights_path=weights_resolved,
                        backend="llama-server",
                        ctx_size=self._active_ctx_size,
                    )

                # Hot-swap cleanly to avoid exceeding host RAM
                self._terminate_proc_locked()

                port = _find_free_port(18080)
                hw = self.hardware
                ctx_size = int(os.getenv("MBOWAGPT_CTX_SIZE") or hw["recommended_ctx_size"])
                threads = int(os.getenv("MBOWAGPT_THREADS") or hw["recommended_threads"])
                alias = weights.stem

                cmd = [
                    str(binary),
                    "-m",
                    weights_resolved,
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--ctx-size",
                    str(ctx_size),
                    "--threads",
                    str(threads),
                    "--n-gpu-layers",
                    "0",
                    "--cache-type-k",
                    "q8_0",
                    "--cache-type-v",
                    "q8_0",
                    "--jinja",
                    "--alias",
                    alias,
                ]
                if self._probe_supports_reasoning_flag(binary):
                    cmd.extend(["--reasoning", "off", "--reasoning-budget", "0"])

                log_path = self._get_log_path()
                log_path.parent.mkdir(parents=True, exist_ok=True)
                stderr_handle = open(log_path, "wb")
                popen_kwargs: Dict[str, Any] = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": stderr_handle,
                    "stdin": subprocess.DEVNULL,
                }
                if os.name == "nt":
                    popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                else:
                    popen_kwargs["start_new_session"] = True

                logger.info(
                    "Starting MbowaGPT (%s) via llama-server on 127.0.0.1:%d using %s (ctx=%d, threads=%d)",
                    role,
                    port,
                    weights.name,
                    ctx_size,
                    threads,
                )
                try:
                    proc = subprocess.Popen(cmd, **popen_kwargs)
                finally:
                    try:
                        stderr_handle.close()
                    except OSError:
                        pass
                self._proc = proc
                self._port = port
                self._active_weights = weights_resolved
                self._active_role = role
                self._active_served_model = alias
                self._active_ctx_size = ctx_size
                self._stderr_log_path = log_path

            # Poll health outside lock (or re-verify process is alive)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    stderr_tail = ""
                    try:
                        if log_path.is_file():
                            stderr_tail = log_path.read_text(encoding="utf-8", errors="ignore")[-400:]
                    except Exception:
                        pass
                    self.unload()
                    raise RuntimeError(
                        f"llama-server exited early (code {proc.returncode}): {stderr_tail}"
                    )
                if self._check_llama_health(port, timeout=0.8):
                    return LocalRuntimeEndpoint(
                        base_url=f"http://127.0.0.1:{port}/v1",
                        api_key="local-mbowagpt",
                        model_id=role,
                        served_model=alias,
                        weights_path=weights_resolved,
                        backend="llama-server",
                        ctx_size=ctx_size,
                    )
                time.sleep(0.25)

            self.unload()
            raise TimeoutError(f"llama-server did not become healthy within {timeout:.0f}s")

        # Secondary local fallback: Ollama on loopback if installed
        ollama_models = self.probe_ollama(timeout=0.5)
        if ollama_models:
            chosen = ollama_models[0]
            if role == "mbowagpt-cybertrunk":
                for m in ollama_models:
                    if any(k in m.lower() for k in ("coder", "deepseek", "qwen")):
                        chosen = m
                        break
            base = (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
            if not base.startswith(("http://", "https://")):
                base = f"http://{base}"
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            return LocalRuntimeEndpoint(
                base_url=base,
                api_key="ollama",
                model_id=role,
                served_model=chosen,
                weights_path=f"ollama://{chosen}",
                backend="ollama",
                ctx_size=4096,
            )

        raise RuntimeError(
            "No local MbowaGPT runtime or GGUF model found. Install a local model or configure llama-server."
        )

    def install_model(
        self,
        role_id: str,
        *,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Download the recommended GGUF weights for *role_id* into local storage."""
        role = canonicalize_mbowagpt_model(role_id)
        if role == MBOWAGPT_AUTO_MODEL_ID:
            role = "mbowagpt"
        spec = MBOWAGPT_MODELS.get(role)
        if spec is None:
            raise ValueError(f"Unknown MbowaGPT model: {role_id}")

        target_dir = self.get_writable_models_dir()
        dest_path = target_dir / spec.recommended_filename
        if dest_path.is_file() and dest_path.stat().st_size > 10_000_000:
            return {"ok": True, "model_id": role, "path": str(dest_path), "already_installed": True}

        part_path = target_dir / f"{spec.recommended_filename}.part"
        req = urllib.request.Request(
            spec.recommended_url,
            headers={"User-Agent": "TchuekaM-Agent/1.0"},
        )
        downloaded = 0
        total = 0
        with self._lock:
            self._download_state = {
                "model_id": role,
                "status": "downloading",
                "downloaded_bytes": 0,
                "total_bytes": 0,
                "percent": 0,
            }

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                with open(part_path, "wb") as out:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        pct = int((downloaded * 100) / total) if total > 0 else 0
                        state = {
                            "model_id": role,
                            "status": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total,
                            "percent": pct,
                        }
                        with self._lock:
                            self._download_state = dict(state)
                        if progress_cb is not None:
                            progress_cb(state)
            os.replace(part_path, dest_path)
            done_state = {
                "ok": True,
                "model_id": role,
                "path": str(dest_path),
                "downloaded_bytes": downloaded,
                "total_bytes": total or downloaded,
                "status": "installed",
                "percent": 100,
            }
            with self._lock:
                self._download_state = dict(done_state)
            return done_state
        except Exception as exc:
            try:
                if part_path.exists():
                    part_path.unlink()
            except OSError:
                pass
            with self._lock:
                self._download_state = {"model_id": role, "status": "error", "error": str(exc)}
            raise

    def get_status(self) -> Dict[str, Any]:
        binary = self.discover_binary()
        installed = self.discover_installed_ggufs()
        ollama_models = self.probe_ollama(timeout=0.25)

        models_info: List[Dict[str, Any]] = []
        for role_id, spec in MBOWAGPT_MODELS.items():
            resolved = self.resolve_model_weights(role_id)
            rec_installed = spec.recommended_filename.lower() in installed
            models_info.append({
                "id": spec.id,
                "display_name": spec.display_name,
                "role_title": spec.role_title,
                "description": spec.description,
                "recommended_filename": spec.recommended_filename,
                "recommended_size_mb": spec.recommended_size_mb,
                "recommended_installed": rec_installed,
                "resolved_weights": resolved.name if resolved else None,
                "resolved_path": str(resolved) if resolved else None,
                "ready": bool(resolved and binary) or bool(ollama_models),
            })

        with self._lock:
            running = self._is_proc_alive_locked()
            return {
                "ready": bool((binary and installed) or ollama_models),
                "binary_path": str(binary) if binary else None,
                "running": running,
                "active_role": self._active_role if running else None,
                "active_port": self._port if running else None,
                "active_served_model": self._active_served_model if running else None,
                "active_weights": Path(self._active_weights).name if running and self._active_weights else None,
                "hardware": self.hardware,
                "installed_ggufs": sorted(p.name for p in installed.values()),
                "ollama_models": ollama_models,
                "models": models_info,
                "download": dict(self._download_state) if self._download_state else None,
            }


_RUNTIME_SINGLETON: Optional[LocalRuntimeManager] = None
_RUNTIME_LOCK = threading.Lock()


def get_local_runtime_manager() -> LocalRuntimeManager:
    global _RUNTIME_SINGLETON
    if _RUNTIME_SINGLETON is None:
        with _RUNTIME_LOCK:
            if _RUNTIME_SINGLETON is None:
                _RUNTIME_SINGLETON = LocalRuntimeManager()
                atexit.register(_RUNTIME_SINGLETON.unload)
    return _RUNTIME_SINGLETON

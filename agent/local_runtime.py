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

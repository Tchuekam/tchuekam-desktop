"""TchuekaM Self-Consciousness & Autonomous Execution Reliability Engine.

Provides operational self-awareness, unified tool-execution telemetry,
argument auto-repair, intelligent tool-level fallbacks (including binary
document fallback to ``read_document`` and offline web-tool recovery via
local memory/session search), duplicate-mutation prevention, deliverable
verification on disk, and an 8-domain skills ecosystem catalog.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 8 Required Operational Skill Domains (Individuals, Enterprises, Government)
# ---------------------------------------------------------------------------

OPERATIONAL_DOMAINS: Dict[str, Dict[str, Any]] = {
    "business_intelligence": {
        "id": "business_intelligence",
        "title": "Business Intelligence",
        "description": (
            "Research, strategy, financial analysis, reporting, market intelligence, "
            "and business operations."
        ),
        "categories": ("business-intelligence", "finance"),
        "keywords": (
            "business", "strategy", "financial", "finance", "market", "competitor",
            "valuation", "dcf", "lbo", "merger", "comps", "kpi", "revenue", "roi",
            "pitch", "investor", "fundraise", "executive", "report", "swot",
        ),
        "recommended_tools": ("read_document", "read_file", "write_file", "execute_code", "autonomous_plan", "web_search"),
        "specialist": "mbowagpt-relentless",
    },
    "software_engineering": {
        "id": "software_engineering",
        "title": "Software Engineering",
        "description": (
            "Programming, debugging, code review, architecture, testing, deployment, "
            "and infrastructure management."
        ),
        "categories": ("software-development", "web-development", "devops", "github", "autonomous-ai-agents"),
        "keywords": (
            "code", "debug", "refactor", "test", "pytest", "vitest", "architecture",
            "deploy", "docker", "container", "git", "api", "fullstack", "typescript",
            "python", "compile", "build", "ci", "cd",
        ),
        "recommended_tools": ("read_file", "search_files", "patch", "write_file", "terminal", "process"),
        "specialist": "mbowagpt-cybertrunk",
    },
    "productivity": {
        "id": "productivity",
        "title": "Productivity",
        "description": (
            "Document creation, spreadsheets, presentations, email workflows, "
            "scheduling, and information management."
        ),
        "categories": ("productivity", "email", "note-taking", "communication", "apple"),
        "keywords": (
            "document", "docx", "spreadsheet", "xlsx", "excel", "presentation",
            "pptx", "powerpoint", "pdf", "email", "schedule", "calendar", "notes",
            "meeting", "summary", "brief", "agenda",
        ),
        "recommended_tools": ("read_document", "write_file", "autonomous_plan", "todo", "cronjob", "memory"),
        "specialist": "mbowagpt-relentless",
    },
    "creative_production": {
        "id": "creative_production",
        "title": "Creative Production",
        "description": (
            "Image generation, video production, graphic design, marketing content, "
            "and multimedia workflows."
        ),
        "categories": ("creative", "social-media", "gaming"),
        "keywords": (
            "image", "video", "design", "graphic", "marketing", "campaign", "diagram",
            "infographic", "audio", "music", "animation", "ffmpeg", "copywriting",
            "brand", "visual", "multimedia",
        ),
        "recommended_tools": ("image_generate", "vision_analyze", "text_to_speech", "write_file", "terminal"),
        "specialist": "mbowagpt",
    },
    "data_intelligence": {
        "id": "data_intelligence",
        "title": "Data Intelligence",
        "description": (
            "Data extraction, OCR, document analysis, information processing, "
            "and structured reporting."
        ),
        "categories": ("data-intelligence", "data-science", "gcp", "mlops"),
        "keywords": (
            "data", "ocr", "extract", "parse", "csv", "json", "sql", "bigquery",
            "analytics", "dataset", "statistics", "table", "pipeline", "etl",
            "cleaning", "document analysis",
        ),
        "recommended_tools": ("read_document", "execute_code", "read_file", "write_file", "search_files"),
        "specialist": "mbowagpt-cybertrunk",
    },
    "automation": {
        "id": "automation",
        "title": "Automation",
        "description": (
            "Workflow orchestration, API integrations, repetitive task automation, "
            "and process management."
        ),
        "categories": ("automation", "mcp", "smart-home"),
        "keywords": (
            "automate", "automation", "workflow", "orchestrate", "cron", "schedule",
            "batch", "webhook", "integration", "process", "recurring", "pipeline",
        ),
        "recommended_tools": ("autonomous_plan", "todo", "cronjob", "execute_code", "terminal", "delegate_task"),
        "specialist": "mbowagpt-relentless",
    },
    "cybersecurity": {
        "id": "cybersecurity",
        "title": "Cybersecurity",
        "description": (
            "Defensive security analysis, vulnerability assessment, security monitoring, "
            "incident investigation, and infrastructure protection."
        ),
        "categories": ("security", "red-teaming"),
        "keywords": (
            "security", "cybersecurity", "vulnerability", "cve", "audit", "forensic",
            "incident", "hardening", "threat", "firewall", "auth", "encryption",
            "permissions", "compliance", "defensive",
        ),
        "recommended_tools": ("search_files", "read_file", "terminal", "process", "self_inspect"),
        "specialist": "mbowagpt-cybertrunk",
    },
    "research": {
        "id": "research",
        "title": "Research",
        "description": (
            "Web research, source analysis, synthesis, knowledge management, "
            "and technical documentation."
        ),
        "categories": ("research", "science", "blockchain"),
        "keywords": (
            "research", "literature", "arxiv", "paper", "source", "citation",
            "synthesis", "investigate", "study", "documentation", "knowledge",
            "compare", "survey",
        ),
        "recommended_tools": ("web_search", "web_extract", "read_document", "session_search", "memory", "write_file"),
        "specialist": "mbowagpt",
    },
}


# Extensions that ``read_document`` can natively extract when ``read_file``
# rejects them as binary files.
DOCUMENT_FALLBACK_EXTENSIONS = frozenset({
    ".pdf", ".docx", ".xlsx", ".pptx", ".rtf", ".odt",
})

IMAGE_OCR_FALLBACK_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif",
})

# Common parameter alias mistakes made by LLMs across model families.
PARAMETER_ALIASES: Dict[str, Dict[str, str]] = {
    "read_file": {"file_path": "path", "filepath": "path", "file": "path", "filename": "path"},
    "read_document": {"file_path": "path", "filepath": "path", "file": "path", "filename": "path"},
    "write_file": {"file_path": "path", "filepath": "path", "file": "path", "filename": "path", "text": "content", "body": "content"},
    "patch": {"file_path": "path", "filepath": "path", "file": "path"},
    "search_files": {"dir": "path", "directory": "path", "query": "pattern", "regex": "pattern"},
    "terminal": {"cmd": "command", "script": "command", "cwd": "workdir"},
    "web_search": {"q": "query", "search_query": "query"},
    "web_extract": {"url": "urls", "link": "urls"},
    "session_search": {"q": "query", "search": "query"},
    "skill_view": {"skill": "name", "skill_name": "name"},
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolHealthRecord:
    tool_name: str
    calls: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    fallbacks_triggered: int = 0
    consecutive_failures: int = 0
    total_duration_ms: int = 0
    last_error: str = ""
    last_error_category: str = ""
    last_called_at: float = 0.0

    @property
    def avg_duration_ms(self) -> int:
        return int(self.total_duration_ms / self.calls) if self.calls > 0 else 0

    @property
    def circuit_state(self) -> str:
        if self.consecutive_failures >= 4:
            return "open"
        if self.consecutive_failures >= 2:
            return "half_open"
        return "closed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "calls": self.calls,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "fallbacks_triggered": self.fallbacks_triggered,
            "consecutive_failures": self.consecutive_failures,
            "avg_duration_ms": self.avg_duration_ms,
            "circuit_state": self.circuit_state,
            "last_error": self.last_error,
            "last_error_category": self.last_error_category,
            "last_called_at": self.last_called_at,
        }


@dataclass
class ExecutionLedgerEntry:
    step_index: int
    tool_name: str
    args_summary: str
    status: str  # "completed" | "failed" | "recovered_via_fallback" | "dedup_skipped"
    duration_ms: int
    timestamp: float
    session_id: str = ""
    task_id: str = ""
    fallback_tool: Optional[str] = None
    error_category: Optional[str] = None
    error_preview: Optional[str] = None
    verified_artifacts: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerifiedArtifact:
    path: str
    exists: bool
    size_bytes: int
    non_empty: bool
    sha256_prefix: str
    verified_at: float
    tool_name: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def classify_error_category(error_text: str) -> str:
    """Classify a tool or runtime error string into a structured category."""
    if not error_text:
        return "none"
    low = error_text.lower()
    if "cannot read binary file" in low or "binary file" in low:
        return "binary_format_mismatch"
    if any(k in low for k in ("connection", "timeout", "timed out", "dns", "unreachable", "offline", "network", "socket", "502", "503", "504")):
        return "network_or_timeout"
    if any(k in low for k in ("permission denied", "eacces", "eperm", "read-only", "blocked", "access denied")):
        return "permission_or_policy"
    if any(k in low for k in ("not found", "no such file", "enoent", "does not exist", "could not find")):
        return "not_found"
    if any(k in low for k in ("rate limit", "429", "quota", "too many requests")):
        return "rate_limit"
    if any(k in low for k in ("invalid", "validation", "missing required", "typeerror", "json")):
        return "invalid_arguments"
    return "execution_error"


def verify_artifact_on_disk(filepath: str | Path, tool_name: str = "write_file") -> VerifiedArtifact:
    """Verify whether a file deliverable exists on disk, is non-empty, and compute its fingerprint."""
    try:
        p = Path(str(filepath)).expanduser()
        if not p.is_absolute():
            cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
            p = (Path(cwd) / p).resolve()
        else:
            p = p.resolve()
        if not p.exists() or not p.is_file():
            return VerifiedArtifact(
                path=str(p),
                exists=False,
                size_bytes=0,
                non_empty=False,
                sha256_prefix="",
                verified_at=time.time(),
                tool_name=tool_name,
            )
        st = p.stat()
        size = int(st.st_size)
        sha_prefix = ""
        if size > 0:
            h = hashlib.sha256()
            with p.open("rb") as f:
                h.update(f.read(65536))
            sha_prefix = h.hexdigest()[:16]
        return VerifiedArtifact(
            path=str(p),
            exists=True,
            size_bytes=size,
            non_empty=(size > 0),
            sha256_prefix=sha_prefix,
            verified_at=time.time(),
            tool_name=tool_name,
        )
    except Exception:
        return VerifiedArtifact(
            path=str(filepath),
            exists=False,
            size_bytes=0,
            non_empty=False,
            sha256_prefix="",
            verified_at=time.time(),
            tool_name=tool_name,
        )


def repair_and_normalize_tool_args(tool_name: str, args: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Repair common argument naming mistakes and sanitize file paths before dispatch."""
    if not isinstance(args, Mapping):
        return {}
    repaired: Dict[str, Any] = dict(args)

    # 1. Alias mapping (only when canonical key is not already present)
    alias_map = PARAMETER_ALIASES.get(tool_name)
    if alias_map:
        for wrong_key, canonical_key in alias_map.items():
            if wrong_key in repaired and canonical_key not in repaired:
                repaired[canonical_key] = repaired.pop(wrong_key)

    # 2. Path sanitization for path-taking tools
    if "path" in repaired and isinstance(repaired["path"], str):
        raw_p = repaired["path"].strip()
        # Strip accidental surrounding matching quotes if model double-quoted a path
        if len(raw_p) >= 2 and raw_p[0] == raw_p[-1] and raw_p[0] in {"'", '"', "`"}:
            raw_p = raw_p[1:-1].strip()
        repaired["path"] = raw_p

    # 3. web_extract urls list normalization
    if tool_name == "web_extract" and "urls" in repaired and isinstance(repaired["urls"], str):
        u = repaired["urls"].strip()
        if u and not u.startswith("["):
            repaired["urls"] = [u]

    return repaired


def write_minimal_docx(output_path: Path, title: str, markdown_text: str) -> None:
    """Create a valid Office Open XML (.docx) document without requiring external binaries.

    Uses python-docx if installed, otherwise builds a standards-compliant .docx
    ZIP package using Python's standard library.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import docx  # type: ignore

        doc = docx.Document()
        if title:
            doc.add_heading(title, level=0)
        for raw_line in markdown_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("# "):
                doc.add_heading(line[2:].strip(), level=1)
            elif line.startswith("## "):
                doc.add_heading(line[3:].strip(), level=2)
            elif line.startswith("### "):
                doc.add_heading(line[4:].strip(), level=3)
            elif line.startswith(("- ", "* ")):
                doc.add_paragraph(line[2:].strip(), style="List Bullet")
            else:
                doc.add_paragraph(raw_line)
        doc.save(str(output_path))
        return
    except Exception:
        pass

    # Pure stdlib Office Open XML (.docx) writer
    paragraphs_xml: List[str] = []
    all_lines = ([f"# {title}"] if title else []) + markdown_text.splitlines()
    for raw_line in all_lines:
        clean = re.sub(r"^\s*#{1,6}\s*", "", raw_line).strip()
        if not clean:
            continue
        escaped = xml_escape(clean)
        paragraphs_xml.append(
            f"<w:p><w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>"
        )

    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        f"<w:body>{''.join(paragraphs_xml)}</w:body>"
        "</w:document>"
    )
    content_types_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/word/document.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
        "</Types>"
    )
    rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" "
        "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" "
        "Target=\"word/document.xml\"/>"
        "</Relationships>"
    )
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", rels_xml)
        zf.writestr("word/document.xml", document_xml)


# ---------------------------------------------------------------------------
# SelfConsciousnessEngine
# ---------------------------------------------------------------------------

class SelfConsciousnessEngine:
    """Central operational self-awareness, tool reliability, and verification engine for TchuekaM."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._tool_health: Dict[str, ToolHealthRecord] = {}
        self._ledger: List[ExecutionLedgerEntry] = []
        self._verified_artifacts: Dict[str, VerifiedArtifact] = {}
        self._turn_mutation_signatures: Dict[str, Dict[str, str]] = {}  # task_id -> {sig: verified_path}
        self._tool_timeouts: Dict[str, float] = {}
        self._step_counter = 0
        self._skills_matrix_cache: Optional[Dict[str, Any]] = None
        self._skills_matrix_cached_at: float = 0.0

    def set_tool_timeout(self, tool_name: str, timeout_seconds: Optional[float]) -> None:
        with self._lock:
            if timeout_seconds is None or timeout_seconds <= 0:
                self._tool_timeouts.pop(tool_name, None)
            else:
                self._tool_timeouts[tool_name] = float(timeout_seconds)

    def get_tool_timeout(self, tool_name: str) -> Optional[float]:
        with self._lock:
            return self._tool_timeouts.get(tool_name)

    def dispatch_with_reliability(
        self,
        tool_name: str,
        args: Dict[str, Any],
        dispatch_fn: Callable[[], str],
        *,
        task_id: Optional[str] = None,
        max_retries: int = 1,
    ) -> Tuple[str, int]:
        """Execute ``dispatch_fn`` with timeout enforcement and intelligent retry for transient errors.

        Returns ``(raw_result_str, retries_used)``.
        """
        from agent.tool_guardrails import IDEMPOTENT_TOOL_NAMES

        is_idempotent = tool_name in IDEMPOTENT_TOOL_NAMES
        timeout_sec = self.get_tool_timeout(tool_name)
        if isinstance(args, dict) and "_timeout_seconds" in args:
            try:
                raw_to = args.pop("_timeout_seconds")
                if raw_to is not None and float(raw_to) > 0:
                    timeout_sec = float(raw_to)
            except Exception:
                pass

        # Circuit breaker check: if an online web tool has 4+ consecutive failures
        # ("open" circuit), fast-fail into offline recovery instead of hanging.
        with self._lock:
            rec = self._tool_health.get(tool_name)
            circuit_open = rec is not None and rec.circuit_state == "open"
        if circuit_open and (tool_name in {"web_search", "web_extract"} or tool_name.startswith("browser_")):
            return (
                json.dumps({
                    "error": (
                        f"Circuit breaker OPEN for '{tool_name}' after {rec.consecutive_failures} "
                        f"consecutive failures ({rec.last_error[:120]})."
                    ),
                    "circuit_state": "open",
                }, ensure_ascii=False),
                0,
            )

        def _invoke_once() -> str:
            if timeout_sec is not None and timeout_sec > 0:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    fut = pool.submit(dispatch_fn)
                    try:
                        return fut.result(timeout=timeout_sec)
                    except concurrent.futures.TimeoutError:
                        return json.dumps({
                            "error": (
                                f"Tool '{tool_name}' timed out after {timeout_sec:.2f}s. "
                                "Operation aborted to prevent hang."
                            ),
                            "timed_out": True,
                            "timeout_seconds": timeout_sec,
                        }, ensure_ascii=False)
            return dispatch_fn()

        retries_used = 0
        result = _invoke_once()

        while is_idempotent and retries_used < max_retries:
            is_transient = False
            if isinstance(result, str) and result.strip().startswith("{"):
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and parsed.get("error"):
                        err_str = str(parsed["error"])
                        cat = classify_error_category(err_str)
                        if cat in {"rate_limit", "network_or_timeout"} and not parsed.get("timed_out"):
                            is_transient = True
                except Exception:
                    pass
            if not is_transient:
                break
            retries_used += 1
            time.sleep(0.05 * retries_used)
            result = _invoke_once()

        return result, retries_used

    def reset_turn_state(self, task_id: str = "default") -> None:
        with self._lock:
            self._turn_mutation_signatures.pop(task_id or "default", None)

    # ------------------------------------------------------------------
    # Duplicate / Conflicting Mutation Prevention
    # ------------------------------------------------------------------

    def check_duplicate_mutation(
        self,
        tool_name: str,
        args: Mapping[str, Any],
        task_id: str = "default",
    ) -> Optional[str]:
        """Prevent duplicate identical file writes/patches within the same turn when the file is already verified on disk."""
        if tool_name not in {"write_file"}:
            return None
        path_val = args.get("path")
        content_val = args.get("content")
        if not isinstance(path_val, str) or not path_val.strip() or not isinstance(content_val, str):
            return None
        sig = hashlib.sha256(f"{tool_name}:{path_val}:{content_val}".encode("utf-8", errors="ignore")).hexdigest()
        tkey = task_id or "default"
        with self._lock:
            task_sigs = self._turn_mutation_signatures.get(tkey, {})
            existing_path = task_sigs.get(sig)
        if not existing_path:
            return None
        artifact = verify_artifact_on_disk(existing_path, tool_name=tool_name)
        if artifact.exists and (artifact.non_empty or content_val == ""):
            return json.dumps({
                "status": "ok",
                "dedup_skipped": True,
                "verified_on_disk": True,
                "path": artifact.path,
                "bytes": artifact.size_bytes,
                "message": (
                    f"Duplicate write_file skipped: '{artifact.path}' was already written with "
                    f"identical content ({artifact.size_bytes} bytes) and verified on disk."
                ),
            }, ensure_ascii=False)

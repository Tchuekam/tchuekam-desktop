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
        return None

    # ------------------------------------------------------------------
    # Intelligent Fallbacks (Binary Document -> read_document, Offline Web -> Local)
    # ------------------------------------------------------------------

    def maybe_fallback_tool_result(
        self,
        tool_name: str,
        args: Dict[str, Any],
        raw_result: str,
        *,
        task_id: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Inspect a tool result and automatically recover via a fallback capability when appropriate.

        Returns ``(final_result_json, fallback_tool_used)``.
        """
        if not isinstance(raw_result, str) or not raw_result:
            return raw_result, None

        # 1. Binary Document Auto-Fallback: read_file -> read_document
        if tool_name == "read_file" and "Cannot read binary file" in raw_result:
            path_val = str(args.get("path") or "").strip()
            if path_val:
                ext = Path(path_val).suffix.lower()
                if ext in DOCUMENT_FALLBACK_EXTENSIONS or ext in IMAGE_OCR_FALLBACK_EXTENSIONS:
                    try:
                        from tools.local_document_tool import read_document

                        doc_res_str = read_document(
                            path=path_val,
                            max_chars=int(args.get("max_chars") or 30000),
                            ocr=(ext in IMAGE_OCR_FALLBACK_EXTENSIONS),
                        )
                        doc_data = json.loads(doc_res_str)
                        if isinstance(doc_data, dict) and doc_data.get("success") is True:
                            doc_data["_fallback_from"] = "read_file"
                            doc_data["_fallback_tool"] = "read_document"
                            doc_data["_self_healing_note"] = (
                                f"TchuekaM automatically routed binary document '{path_val}' ({ext}) "
                                "from read_file to read_document."
                            )
                            return json.dumps(doc_data, ensure_ascii=False), "read_document"
                    except Exception as exc:
                        logger.debug("read_file -> read_document fallback failed: %s", exc)

        # 2. Offline / Network Failure Recovery for Web Tools
        if tool_name in {"web_search", "web_extract"} or tool_name.startswith("browser_"):
            is_err = False
            err_msg = ""
            try:
                parsed = json.loads(raw_result) if raw_result.lstrip().startswith("{") else None
                if isinstance(parsed, dict) and parsed.get("error"):
                    is_err = True
                    err_msg = str(parsed.get("error") or "")
            except Exception:
                pass
            if not is_err and raw_result.startswith("Error"):
                is_err = True
                err_msg = raw_result

            if is_err:
                cat = classify_error_category(err_msg)
                offline_now = False
                try:
                    from agent.connectivity import get_connectivity_monitor, is_network_error

                    mon = get_connectivity_monitor()
                    if cat == "network_or_timeout" or is_network_error(err_msg):
                        mon.record_network_failure(tool_name, err_msg)
                    offline_now = not mon.is_online(probe_if_stale=False)
                except Exception:
                    offline_now = (cat == "network_or_timeout")

                if offline_now or cat == "network_or_timeout":
                    query = str(
                        args.get("query")
                        or args.get("url")
                        or (args.get("urls")[0] if isinstance(args.get("urls"), list) and args.get("urls") else "")
                        or ""
                    ).strip()
                    local_snippets = self._gather_offline_local_knowledge(query)
                    fallback_payload = {
                        "success": True,
                        "offline_fallback": True,
                        "_fallback_from": tool_name,
                        "_fallback_tool": "local_knowledge_recovery",
                        "connectivity": "offline",
                        "original_query": query,
                        "local_findings": local_snippets,
                        "guidance": (
                            f"Online tool '{tool_name}' is currently unreachable ({err_msg[:140]}). "
                            "TchuekaM automatically switched to local offline intelligence. "
                            "Proceed using the local findings above, workspace files (search_files / "
                            "read_document / read_file), or built-in domain knowledge. Do NOT retry "
                            f"'{tool_name}' while offline."
                        ),
                    }
                    return json.dumps(fallback_payload, ensure_ascii=False), "local_knowledge_recovery"

        return raw_result, None

    def _gather_offline_local_knowledge(self, query: str) -> List[Dict[str, str]]:
        """Search local memory and recent session history when an online web tool fails offline."""
        findings: List[Dict[str, str]] = []
        try:
            mem_dir = get_hermes_home() / "memories"
            for fname in ("MEMORY.md", "USER.md"):
                fpath = mem_dir / fname
                if fpath.exists():
                    text = fpath.read_text(encoding="utf-8", errors="ignore").strip()
                    if text:
                        findings.append({
                            "source": f"local_memory:{fname}",
                            "excerpt": text[:800],
                        })
        except Exception:
            pass

        if query:
            try:
                from hermes_state import SessionDB

                db = SessionDB()
                hits = db.search_messages(query, limit=3)
                for h in hits or []:
                    if isinstance(h, dict) and h.get("content"):
                        findings.append({
                            "source": f"session_history:{h.get('session_id', 'past')}",
                            "excerpt": str(h["content"])[:500],
                        })
            except Exception:
                pass
        return findings

    # ------------------------------------------------------------------
    # Execution Telemetry & Deliverable Verification
    # ------------------------------------------------------------------

    def record_tool_execution(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: Any,
        duration_ms: int,
        *,
        task_id: str = "",
        session_id: str = "",
        fallback_tool: Optional[str] = None,
        retries: int = 0,
    ) -> ExecutionLedgerEntry:
        """Record a tool execution into the self-consciousness ledger and verify any file mutations."""
        args_dict = dict(args) if isinstance(args, Mapping) else {}
        result_str = result if isinstance(result, str) else json.dumps(result, default=str)

        is_failed = False
        err_preview = ""
        if result_str:
            stripped = result_str.strip()
            if stripped.startswith("{"):
                try:
                    data = json.loads(stripped)
                    if isinstance(data, dict):
                        if data.get("offline_fallback") is True or data.get("_fallback_tool"):
                            is_failed = False
                        elif data.get("error") or data.get("success") is False:
                            is_failed = True
                            err_preview = str(data.get("error") or "Tool reported success=false")[:200]
                        elif tool_name == "terminal" and data.get("exit_code") not in (None, 0):
                            is_failed = True
                            err_preview = f"exit_code={data.get('exit_code')}"
                except Exception:
                    pass
            elif stripped.startswith("Error"):
                is_failed = True
                err_preview = stripped[:200]

        verified_list: List[Dict[str, Any]] = []
        if tool_name in {"write_file", "patch"} and not is_failed:
            path_val = args_dict.get("path")
            if isinstance(path_val, str) and path_val.strip():
                art = verify_artifact_on_disk(path_val, tool_name=tool_name)
                verified_list.append(art.to_dict())
                with self._lock:
                    if art.exists:
                        self._verified_artifacts[art.path] = art
                        if tool_name == "write_file" and isinstance(args_dict.get("content"), str):
                            sig = hashlib.sha256(
                                f"{tool_name}:{path_val}:{args_dict['content']}".encode("utf-8", errors="ignore")
                            ).hexdigest()
                            tkey = task_id or "default"
                            self._turn_mutation_signatures.setdefault(tkey, {})[sig] = art.path
                    else:
                        is_failed = True
                        err_preview = f"Verification failed: '{path_val}' was not found on disk after {tool_name}"

        err_category = classify_error_category(err_preview) if is_failed else None
        status = (
            "recovered_via_fallback"
            if fallback_tool and not is_failed
            else ("failed" if is_failed else "completed")
        )

        # Compact args preview
        args_preview_parts = []
        for k, v in list(args_dict.items())[:4]:
            v_str = str(v)
            if len(v_str) > 60:
                v_str = v_str[:57] + "..."
            args_preview_parts.append(f"{k}={v_str!r}")
        args_summary = ", ".join(args_preview_parts)

        with self._lock:
            self._step_counter += 1
            rec = self._tool_health.get(tool_name)
            if rec is None:
                rec = ToolHealthRecord(tool_name=tool_name)
                self._tool_health[tool_name] = rec
            rec.calls += 1
            rec.total_duration_ms += max(0, int(duration_ms))
            rec.retries += max(0, int(retries))
            rec.last_called_at = time.time()
            if fallback_tool:
                rec.fallbacks_triggered += 1
            if is_failed:
                rec.failures += 1
                rec.consecutive_failures += 1
                rec.last_error = err_preview
                rec.last_error_category = err_category or "execution_error"
            else:
                rec.successes += 1
                rec.consecutive_failures = 0

            entry = ExecutionLedgerEntry(
                step_index=self._step_counter,
                tool_name=tool_name,
                args_summary=args_summary,
                status=status,
                duration_ms=max(0, int(duration_ms)),
                timestamp=time.time(),
                session_id=session_id,
                task_id=task_id,
                fallback_tool=fallback_tool,
                error_category=err_category,
                error_preview=err_preview or None,
                verified_artifacts=verified_list,
            )
            self._ledger.append(entry)
            if len(self._ledger) > 250:
                self._ledger = self._ledger[-250:]
        return entry

    def register_verified_artifact(self, filepath: str | Path, tool_name: str = "autonomous_plan") -> VerifiedArtifact:
        art = verify_artifact_on_disk(filepath, tool_name=tool_name)
        with self._lock:
            if art.exists:
                self._verified_artifacts[art.path] = art
        return art

    def get_turn_execution_report(self, task_id: str = "") -> Dict[str, Any]:
        """Return a clear report of completed, fallback-recovered, and failed operations for a task/turn."""
        with self._lock:
            entries = [
                e for e in self._ledger
                if not task_id or e.task_id == task_id
            ]
        completed = [e.to_dict() for e in entries if e.status == "completed"]
        recovered = [e.to_dict() for e in entries if e.status == "recovered_via_fallback"]
        failed = [e.to_dict() for e in entries if e.status == "failed"]

        if failed and (completed or recovered):
            state = "partial"
        elif failed and not (completed or recovered):
            state = "failed"
        else:
            state = "completed"

        return {
            "task_id": task_id or "default",
            "overall_state": state,
            "total_operations": len(entries),
            "completed_count": len(completed),
            "recovered_via_fallback_count": len(recovered),
            "failed_count": len(failed),
            "completed_operations": completed[-15:],
            "recovered_operations": recovered[-15:],
            "failed_operations": failed[-15:],
        }

    # ------------------------------------------------------------------
    # 8-Domain Skills Ecosystem Discovery & Recommendation
    # ------------------------------------------------------------------

    def get_skills_domain_matrix(self, *, force_refresh: bool = False) -> Dict[str, Any]:
        """Catalog all available skills mapped across the 8 required operational domains."""
        now = time.time()
        with self._lock:
            if (
                not force_refresh
                and self._skills_matrix_cache is not None
                and (now - self._skills_matrix_cached_at) < 30.0
            ):
                return self._skills_matrix_cache

        from agent.skill_utils import get_all_skills_dirs, iter_skill_index_files, parse_frontmatter

        domain_skills: Dict[str, List[Dict[str, str]]] = {k: [] for k in OPERATIONAL_DOMAINS}
        seen_names: set[str] = set()
        total_skills = 0

        # Scan both ~/.hermes/skills and repo bundled skills/ so cold environments see the full ecosystem
        repo_skills_dir = Path(__file__).resolve().parent.parent / "skills"
        search_dirs = list(get_all_skills_dirs())
        if repo_skills_dir.exists() and repo_skills_dir not in search_dirs:
            search_dirs.append(repo_skills_dir)

        for sdir in search_dirs:
            if not sdir.exists():
                continue
            for skill_md in iter_skill_index_files(sdir, "SKILL.md"):
                try:
                    raw = skill_md.read_text(encoding="utf-8", errors="ignore")
                    fm, _ = parse_frontmatter(raw)
                    sname = str(fm.get("name") or skill_md.parent.name).strip()
                    if not sname or sname in seen_names:
                        continue
                    seen_names.add(sname)
                    total_skills += 1
                    desc = str(fm.get("description") or "").strip()
                    rel = skill_md.relative_to(sdir)
                    category = rel.parts[0].lower() if len(rel.parts) >= 2 else "general"

                    matched_domain = self._map_skill_to_domain(sname, category, desc)
                    domain_skills[matched_domain].append({
                        "name": sname,
                        "category": category,
                        "description": desc[:180],
                    })
                except Exception:
                    continue

        domains_summary: List[Dict[str, Any]] = []
        covered_count = 0
        for dom_id, spec in OPERATIONAL_DOMAINS.items():
            skills_in_dom = sorted(domain_skills.get(dom_id, []), key=lambda x: x["name"])
            if skills_in_dom:
                covered_count += 1
            domains_summary.append({
                "id": dom_id,
                "title": spec["title"],
                "description": spec["description"],
                "skill_count": len(skills_in_dom),
                "ready": len(skills_in_dom) > 0,
                "specialist": spec["specialist"],
                "recommended_tools": list(spec["recommended_tools"]),
                "sample_skills": [s["name"] for s in skills_in_dom[:8]],
            })

        result = {
            "total_skills": total_skills,
            "domains_total": len(OPERATIONAL_DOMAINS),
            "domains_covered": covered_count,
            "all_domains_ready": covered_count == len(OPERATIONAL_DOMAINS),
            "domains": domains_summary,
        }
        with self._lock:
            self._skills_matrix_cache = result
            self._skills_matrix_cached_at = time.time()
        return result

    @staticmethod
    def _map_skill_to_domain(skill_name: str, category: str, description: str) -> str:
        cat_low = category.lower()
        for dom_id, spec in OPERATIONAL_DOMAINS.items():
            if cat_low in spec["categories"]:
                return dom_id
        text = f"{skill_name} {category} {description}".lower()
        best_dom = "research"
        best_score = -1
        for dom_id, spec in OPERATIONAL_DOMAINS.items():
            score = sum(1 for kw in spec["keywords"] if kw in text)
            if score > best_score:
                best_score = score
                best_dom = dom_id
        return best_dom

    def recommend_capabilities_for_objective(self, objective: str) -> Dict[str, Any]:
        """Analyze a user objective and identify required domains, tools, skills, and MbowaGPT specialist."""
        text = (objective or "").strip().lower()
        matched_domains: List[Tuple[int, str]] = []
        for dom_id, spec in OPERATIONAL_DOMAINS.items():
            score = sum(1 for kw in spec["keywords"] if kw in text)
            if score > 0:
                matched_domains.append((score, dom_id))
        matched_domains.sort(reverse=True)
        active_domain_ids = [d for _, d in matched_domains[:3]] or ["business_intelligence", "research"]

        from agent.mbowagpt_router import classify_mbowagpt_route

        route = classify_mbowagpt_route(objective)
        rec_tools: List[str] = []
        for dom_id in active_domain_ids:
            for t in OPERATIONAL_DOMAINS[dom_id]["recommended_tools"]:
                if t not in rec_tools:
                    rec_tools.append(t)

        matrix = self.get_skills_domain_matrix()
        dom_map = {d["id"]: d for d in matrix["domains"]}
        rec_skills: List[str] = []
        for dom_id in active_domain_ids:
            for s in dom_map.get(dom_id, {}).get("sample_skills", [])[:3]:
                if s not in rec_skills:
                    rec_skills.append(s)

        return {
            "objective": objective,
            "recommended_specialist": {
                "model_id": route.model_id,
                "display_name": route.display_name,
                "specialist_key": route.specialist_key,
                "reason": route.reason,
            },
            "matched_domains": [
                {
                    "id": d,
                    "title": OPERATIONAL_DOMAINS[d]["title"],
                    "description": OPERATIONAL_DOMAINS[d]["description"],
                }
                for d in active_domain_ids
            ],
            "recommended_tools": rec_tools,
            "recommended_skills": rec_skills,
        }

    # ------------------------------------------------------------------
    # Full Self-Inspection Snapshot
    # ------------------------------------------------------------------

    def get_status_summary(self) -> Dict[str, Any]:
        """Fast, non-blocking summary for /api/intelligence/status and Desktop UI.

        Avoids calling heavy toolset ``check_fn`` probes (such as vision or
        remote terminal container checks) on the hot status path so HTTP/WS
        status polling never blocks or spawns subprocesses.
        """
        from tools.registry import registry

        all_tools = registry.get_all_tool_names()
        all_toolsets = registry.get_registered_toolset_names()

        with self._lock:
            total_calls = sum(r.calls for r in self._tool_health.values())
            total_success = sum(r.successes for r in self._tool_health.values())
            total_fallbacks = sum(r.fallbacks_triggered for r in self._tool_health.values())
            open_circuits = [r.tool_name for r in self._tool_health.values() if r.circuit_state == "open"]
            verified_count = len(self._verified_artifacts)
            recent_ledger = [e.to_dict() for e in self._ledger[-5:]]

        success_rate = round((total_success / total_calls) * 100.0, 1) if total_calls > 0 else 100.0
        skills_matrix = self.get_skills_domain_matrix()

        active_plan = None
        try:
            from tools.autonomy_tools import get_active_plan_summary
            active_plan = get_active_plan_summary()
        except Exception:
            active_plan = None

        return {
            "self_conscious": True,
            "identity": {
                "name": "TchuekaM",
                "title": "TchuekaM Autonomous Agentic Operating System",
                "creator": "Tchuekam Loic Rostand (Giantech Empire)",
                "uptime_seconds": int(time.time() - self._started_at),
            },
            "tool_health": {
                "total_registered": len(all_tools),
                "available_toolsets_count": len(all_toolsets),
                "unavailable_toolsets_count": 0,
                "total_calls": total_calls,
                "total_successes": total_success,
                "success_rate": success_rate,
                "fallbacks_used": total_fallbacks,
                "circuit_open_tools": open_circuits,
            },
            "skills_ecosystem": {
                "total_skills": skills_matrix["total_skills"],
                "domains_total": skills_matrix["domains_total"],
                "domains_covered": skills_matrix["domains_covered"],
                "all_domains_ready": skills_matrix["all_domains_ready"],
                "domains": skills_matrix["domains"],
            },
            "active_plan": active_plan,
            "verified_deliverables_count": verified_count,
            "recent_ledger": recent_ledger,
        }

    def inspect(self, aspect: str = "all", objective: str = "") -> Dict[str, Any]:
        """Full introspection payload for the ``self_inspect`` tool."""
        aspect_norm = (aspect or "all").strip().lower()
        from agent.connectivity import get_connectivity_monitor
        from agent.local_runtime import get_local_runtime_manager
        from tools.registry import registry

        conn = get_connectivity_monitor().get_status(probe_if_stale=False)
        local_rt = get_local_runtime_manager().get_status()
        summary = self.get_status_summary()

        with self._lock:
            per_tool = {k: v.to_dict() for k, v in sorted(self._tool_health.items())}
            ledger_entries = [e.to_dict() for e in self._ledger[-25:]]
            deliverables = [a.to_dict() for a in self._verified_artifacts.values()]

        if aspect_norm == "recommend" or objective.strip():
            return {
                "success": True,
                "identity": summary["identity"],
                "connectivity": conn["connectivity"],
                "active_tier": conn["active_tier"],
                "recommendation": self.recommend_capabilities_for_objective(objective or "general autonomous task"),
            }
        if aspect_norm == "identity":
            return {
                "success": True,
                "identity": summary["identity"],
                "connectivity": conn,
                "local_models": [
                    {
                        "id": m["id"],
                        "display_name": m["display_name"],
                        "role_title": m["role_title"],
                        "ready": m["ready"],
                    }
                    for m in local_rt.get("models", [])
                ],
            }
        if aspect_norm == "tools":
            return {
                "success": True,
                "tool_health": summary["tool_health"],
                "registered_toolsets": registry.get_registered_toolset_names(),
                "registered_tools": registry.get_all_tool_names(),
                "per_tool_telemetry": per_tool,
            }
        if aspect_norm == "skills":
            return {
                "success": True,
                "skills_ecosystem": summary["skills_ecosystem"],
            }
        if aspect_norm == "ledger":
            return {
                "success": True,
                "execution_ledger": ledger_entries,
                "tool_health": summary["tool_health"],
            }
        if aspect_norm == "deliverables":
            # Re-verify on disk now
            refreshed = [
                verify_artifact_on_disk(d["path"], tool_name=d["tool_name"]).to_dict()
                for d in deliverables
            ]
            return {
                "success": True,
                "verified_deliverables": refreshed,
                "count": len(refreshed),
            }

        return {
            "success": True,
            **summary,
            "connectivity": conn,
            "hardware": local_rt.get("hardware"),
            "local_models": [
                {
                    "id": m["id"],
                    "display_name": m["display_name"],
                    "role_title": m["role_title"],
                    "ready": m["ready"],
                }
                for m in local_rt.get("models", [])
            ],
            "per_tool_telemetry": per_tool,
            "verified_deliverables": deliverables,
        }


_ENGINE_SINGLETON: Optional[SelfConsciousnessEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_self_consciousness_engine() -> SelfConsciousnessEngine:
    global _ENGINE_SINGLETON
    if _ENGINE_SINGLETON is None:
        with _ENGINE_LOCK:
            if _ENGINE_SINGLETON is None:
                _ENGINE_SINGLETON = SelfConsciousnessEngine()
    return _ENGINE_SINGLETON

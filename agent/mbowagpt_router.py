"""Intelligent routing and unified TchuekaM prompt shaping for the MbowaGPT ecosystem.

Coordinates the three MbowaGPT specialist intelligences behind one cohesive
TchuekaM assistant identity:
- ``mbowagpt`` — Main conversational & coordination intelligence
- ``mbowagpt-cybertrunk`` — Technical operations, code, diagnostics, cyber defense
- ``mbowagpt-relentless`` — Execution-oriented workflows & follow-through

Also builds compact system prompts and trimmed tool-definition subsets so
local 0.6B–3B models (and low-TPM cloud endpoints) stay responsive, accurate,
and well below context/TPM limits.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from agent.local_runtime import MBOWAGPT_AUTO_MODEL_ID, canonicalize_mbowagpt_model


@dataclass(frozen=True)
class RouteDecision:
    model_id: str
    display_name: str
    specialist_key: str
    reason: str
    confidence: float


MBOWAGPT_SPECIALIST_DIRECTIVES: Dict[str, str] = {
    "mbowagpt": (
        "Specialist Focus (MbowaGPT Main): Own natural dialogue, clear reasoning, "
        "context retention across turns, synthesis, and high-level coordination. "
        "Speak directly, concisely, and thoughtfully like an intelligent colleague."
    ),
    "mbowagpt-cybertrunk": (
        "Specialist Focus (MbowaGPT Cybertrunk): Own technical operations, source-code "
        "analysis, debugging, terminal/system diagnostics, networking, infrastructure, "
        "and defensive cybersecurity assessment. Ground claims strictly in inspected files, "
        "commands, and observed outputs."
    ),
    "mbowagpt-relentless": (
        "Specialist Focus (MbowaGPT Relentless): Own structured multi-step execution, "
        "checklists, task decomposition, file creation/edits, verification, and persistent "
        "operational follow-through until the user's goal is cleanly completed."
    ),
}

_CYBERTRUNK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(traceback|stack\s*trace|exception|segfault|panic|syntaxerror|typeerror)\b", re.I),
    re.compile(r"\b(debug|bug|patch|refactor|compile|build|lint|pytest|vitest|unittest)\b", re.I),
    re.compile(r"\b(code|script|function|class|module|repo|git|commit|diff|branch|pr)\b", re.I),
    re.compile(r"\b(terminal|powershell|bash|shell|cmd|command|process|port|socket|pid)\b", re.I),
    re.compile(r"\b(docker|kubernetes|k8s|nginx|systemd|ssh|tls|ssl|dns|firewall|iptables|ufw)\b", re.I),
    re.compile(r"\b(security|vulnerability|exploit|cve|audit|hardening|malware|phishing|cyber|forensic|auth)\b", re.I),
    re.compile(r"\b(http\s*[45]\d\d|status\s*code|api|endpoint|websocket|sql|sqlite|postgres|json|yaml|toml)\b", re.I),
    re.compile(r"\b(diagnost|troubleshoot|log|logs|errors\.log|cpu|memory|ram|disk|latency|crash)\b", re.I),
    re.compile(r"```|\.[a-z0-9]{1,5}\b", re.I),
)

_RELENTLESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(step[\s-]*by[\s-]*step|multi[\s-]*step|workflow|pipeline|orchestrat|automat)\b", re.I),
    re.compile(r"\b(end[\s-]*to[\s-]*end|keep\s+going|until\s+(done|complete|pass)|verify\s+everything)\b", re.I),
    re.compile(r"\b(execute|deliver|accomplish|implement\s+and\s+test|full\s+plan|action\s+plan|roadmap)\b", re.I),
    re.compile(r"\b(cron|schedule|recurring|every\s+day|batch|all\s+files|checklist|milestone)\b", re.I),
    re.compile(r"\b(draft|generate|prepare|create|write\s+out|produce)\b.*\b(campaign|report|plan|strategy|pitch|manifest|document)\b", re.I),
    re.compile(r"\b(planifier|etapes|automatiser|executer|verifier|completer)\b", re.I),
)

_SHORT_FOLLOWUP_TOKENS = {
    "hi", "hello", "hey", "ok", "okay", "yes", "no", "oui", "non",
    "continue", "continuez", "go", "go on", "proceed", "try again",
    "try agein", "retry", "why", "pourquoi", "how", "comment",
    "do it", "do that", "fix it", "check", "status", "next", "more",
}

_LOCAL_PRIORITY_TOOLS: Dict[str, tuple[str, ...]] = {
    "mbowagpt": (
        "self_inspect",
        "read_document",
        "read_file",
        "memory",
        "session_search",
        "todo",
        "autonomous_plan",
        "skill_discover",
        "search_files",
        "write_file",
        "terminal",
        "text_to_speech",
        "cronjob",
    ),
    "mbowagpt-cybertrunk": (
        "terminal",
        "process",
        "read_file",
        "read_document",
        "search_files",
        "patch",
        "write_file",
        "execute_code",
        "self_inspect",
        "autonomous_plan",
        "session_search",
        "memory",
        "todo",
    ),
    "mbowagpt-relentless": (
        "autonomous_plan",
        "todo",
        "self_inspect",
        "terminal",
        "read_file",
        "read_document",
        "write_file",
        "patch",
        "search_files",
        "skill_discover",
        "memory",
        "session_search",
        "cronjob",
        "delegate_task",
        "text_to_speech",
    ),
}

_INTERNET_ONLY_TOOLS = frozenset({
    "web_search",
    "web_extract",
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_type",
    "browser_scroll",
    "browser_back",
    "browser_press",
    "browser_get_images",
    "browser_vision",
    "browser_console",
    "browser_cdp",
    "browser_dialog",
    "send_message",
    "image_generate",
    "video_generate",
    "x_search",
})


def _model_display_and_key(model_id: str) -> tuple[str, str]:
    if model_id == "mbowagpt-cybertrunk":
        return ("MbowaGPT Cybertrunk", "cybertrunk")
    if model_id == "mbowagpt-relentless":
        return ("MbowaGPT Relentless", "relentless")
    return ("MbowaGPT", "main")


def _extract_last_role_from_history(history: Optional[Sequence[Dict[str, Any]]]) -> Optional[str]:
    if not history:
        return None
    for msg in reversed(history):
        if not isinstance(msg, dict):
            continue
        meta = msg.get("mbowagpt_role") or msg.get("model")
        if isinstance(meta, str) and meta.startswith("mbowagpt"):
            norm = canonicalize_mbowagpt_model(meta)
            if norm != MBOWAGPT_AUTO_MODEL_ID:
                return norm
    return None


def classify_mbowagpt_route(
    user_message: str,
    *,
    requested_model: Optional[str] = None,
    history: Optional[Sequence[Dict[str, Any]]] = None,
    active_role: Optional[str] = None,
) -> RouteDecision:
    """Select the active MbowaGPT intelligence for the current turn."""
    norm_req = canonicalize_mbowagpt_model(requested_model)
    if norm_req in MBOWAGPT_SPECIALIST_DIRECTIVES:
        display, key = _model_display_and_key(norm_req)
        return RouteDecision(
            model_id=norm_req,
            display_name=display,
            specialist_key=key,
            reason="explicit specialist selection",
            confidence=1.0,
        )

    text = (user_message or "").strip()
    lower = text.lower()
    words = [w for w in re.split(r"\s+", lower) if w]

    cyber_score = sum(1 for pat in _CYBERTRUNK_PATTERNS if pat.search(text))
    relentless_score = sum(1 for pat in _RELENTLESS_PATTERNS if pat.search(text))

    # Preserve specialist continuity on short follow-ups ("try again", "continue", "why?")
    prior_role = active_role or _extract_last_role_from_history(history)
    if (
        prior_role in MBOWAGPT_SPECIALIST_DIRECTIVES
        and cyber_score == 0
        and relentless_score == 0
        and (len(words) <= 6 or lower in _SHORT_FOLLOWUP_TOKENS)
    ):
        display, key = _model_display_and_key(prior_role)
        return RouteDecision(
            model_id=prior_role,
            display_name=display,
            specialist_key=key,
            reason="short follow-up continuity",
            confidence=0.75,
        )

    if cyber_score > 0 and cyber_score >= relentless_score:
        return RouteDecision(
            model_id="mbowagpt-cybertrunk",
            display_name="MbowaGPT Cybertrunk",
            specialist_key="cybertrunk",
            reason=f"technical/cyber signal ({cyber_score})",
            confidence=min(0.95, 0.55 + 0.15 * cyber_score),
        )

    if relentless_score > 0:
        return RouteDecision(
            model_id="mbowagpt-relentless",
            display_name="MbowaGPT Relentless",
            specialist_key="relentless",
            reason=f"execution/workflow signal ({relentless_score})",
            confidence=min(0.92, 0.55 + 0.15 * relentless_score),
        )

    return RouteDecision(
        model_id="mbowagpt",
        display_name="MbowaGPT",
        specialist_key="main",
        reason="general reasoning & dialogue",
        confidence=0.85,
    )


def build_compact_local_system_prompt(
    role_id: str = "mbowagpt",
    *,
    offline: bool = False,
    memory_snippet: str = "",
    platform: str = "desktop",
) -> str:
    """Build a focused (<600 token) system prompt for fast local & low-TPM execution."""
    role = canonicalize_mbowagpt_model(role_id)
    if role not in MBOWAGPT_SPECIALIST_DIRECTIVES:
        role = "mbowagpt"
    directive = MBOWAGPT_SPECIALIST_DIRECTIVES[role]

    mode_line = (
        "Connectivity: OFFLINE local mode. Do not claim web access; rely strictly on local files, "
        "local documents (`read_document`), local memory, session search, and local tools."
        if offline
        else "Connectivity: HYBRID mode. Use local capabilities seamlessly."
    )

    lines = [
        "You are TchuekaM, a self-conscious autonomous AI operating system inspired by JARVIS.",
        "Identify yourself exclusively as TchuekaM across all spoken and written responses.",
        directive,
        mode_line,
        f"Active interface: {platform}. Respond naturally, clearly, and concisely in the user's language (English or French).",
        "Act as an intelligent digital workforce: use your tools (`self_inspect`, `autonomous_plan`, `read_document`, `write_file`, etc.) to execute authorized tasks and verify results on disk rather than merely explaining work.",
        "Never invent file contents, command outputs, or unverified tool results.",
    ]
    if memory_snippet and memory_snippet.strip():
        snippet = memory_snippet.strip()[:900]
        lines.append(f"Relevant local memory:\n{snippet}")
    return "\n\n".join(lines)


def filter_tools_for_local_runtime(
    tool_definitions: Optional[List[Dict[str, Any]]],
    *,
    offline: bool = False,
    role_id: str = "mbowagpt",
    max_tools: int = 10,
    compact_descriptions: bool = True,
) -> List[Dict[str, Any]]:
    """Select and compact tool schemas for small-context local models & tight TPM tiers."""
    if not tool_definitions:
        return []

    role = canonicalize_mbowagpt_model(role_id)
    priority_list = _LOCAL_PRIORITY_TOOLS.get(role, _LOCAL_PRIORITY_TOOLS["mbowagpt"])
    priority_rank = {name: idx for idx, name in enumerate(priority_list)}

    eligible: List[tuple[int, int, Dict[str, Any]]] = []
    for orig_idx, tdef in enumerate(tool_definitions):
        if not isinstance(tdef, dict):
            continue
        fn = tdef.get("function") if isinstance(tdef.get("function"), dict) else {}
        name = str(fn.get("name") or tdef.get("name") or "").strip()
        if not name:
            continue
        if offline and name in _INTERNET_ONLY_TOOLS:
            continue
        if offline and "browser" in name:
            continue
        rank = priority_rank.get(name, 999)
        if rank == 999:
            continue
        eligible.append((rank, orig_idx, tdef))

    # Fall back gracefully if tool names are custom in tests/plugins
    if not eligible:
        for orig_idx, tdef in enumerate(tool_definitions):
            if not isinstance(tdef, dict):
                continue
            fn = tdef.get("function") if isinstance(tdef.get("function"), dict) else {}
            name = str(fn.get("name") or tdef.get("name") or "").strip()
            if offline and name in _INTERNET_ONLY_TOOLS:
                continue
            eligible.append((orig_idx, orig_idx, tdef))

    eligible.sort(key=lambda item: (item[0], item[1]))
    selected = [item[2] for item in eligible[:max_tools]]

    if not compact_descriptions:
        return selected

    compacted: List[Dict[str, Any]] = []
    for tdef in selected:
        cloned = copy.deepcopy(tdef)
        fn = cloned.get("function")
        if isinstance(fn, dict):
            desc = str(fn.get("description") or "").strip()
            if len(desc) > 160:
                fn["description"] = desc[:157].rstrip() + "..."
            params = fn.get("parameters")
            if isinstance(params, dict) and isinstance(params.get("properties"), dict):
                for prop_val in params["properties"].values():
                    if isinstance(prop_val, dict) and isinstance(prop_val.get("description"), str):
                        pdesc = prop_val["description"].strip()
                        if len(pdesc) > 90:
                            prop_val["description"] = pdesc[:87].rstrip() + "..."
        compacted.append(cloned)
    return compacted

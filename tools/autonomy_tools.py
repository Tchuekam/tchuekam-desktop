#!/usr/bin/env python3
"""Autonomous Agentic Engine & Self-Consciousness Tools for TchuekaM.

Provides three core tools available in both online and 100% offline modes:
1. ``self_inspect``: Live operational self-awareness (identity, active MbowaGPT
   or cloud specialist, connectivity, hardware, unified tool health & circuit
   breakers, 8-domain skills matrix, execution ledger, verified deliverables,
   and capability recommendation for objectives).
2. ``autonomous_plan``: Persistent, recoverable multi-step task planning,
   dependency-ordered multi-tool workflow execution (`execute_workflow` & `run_step`)
   with inter-tool data passing (`{{step_id.output}}`, `{{step_id.content}}`),
   deliverable synthesis (.md, .html, .docx, .json), and strict on-disk artifact
   verification so TchuekaM never claims unsupported completion.
3. ``skill_discover``: 8-domain skill discovery & online/offline capability
   expansion (searches installed skills, bundled optional skills, and online
   Skills Hub extensions, evaluates relevance/security/offline-compatibility,
   integrates approved extensions, and maintains a persistent capability catalog).
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.self_consciousness import (
    OPERATIONAL_DOMAINS,
    get_self_consciousness_engine,
    verify_artifact_on_disk,
    write_minimal_docx,
)
from hermes_constants import get_hermes_home
from tools.registry import registry, tool_error

logger = logging.getLogger(__name__)

_PLANS_LOCK = threading.RLock()


def _autonomy_dir() -> Path:
    d = get_hermes_home() / "autonomy"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _plans_file() -> Path:
    return _autonomy_dir() / "plans.json"


def _catalog_file() -> Path:
    return _autonomy_dir() / "capability_catalog.json"


def _load_plans_store() -> Dict[str, Any]:
    with _PLANS_LOCK:
        pf = _plans_file()
        if pf.exists():
            try:
                data = json.loads(pf.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("plans"), dict):
                    return data
            except Exception as exc:
                logger.debug("Could not load autonomy plans store: %s", exc)
        return {"active_plan_id": None, "plans": {}}


def _save_plans_store(store: Dict[str, Any]) -> None:
    with _PLANS_LOCK:
        pf = _plans_file()
        tmp = pf.with_suffix(".tmp")
        tmp.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(pf)


def _load_capability_catalog() -> Dict[str, Any]:
    with _PLANS_LOCK:
        cf = _catalog_file()
        if cf.exists():
            try:
                data = json.loads(cf.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("extensions"), dict):
                    return data
            except Exception:
                pass
        return {"updated_at": time.time(), "extensions": {}}


def _save_capability_catalog(catalog: Dict[str, Any]) -> None:
    with _PLANS_LOCK:
        catalog["updated_at"] = time.time()
        cf = _catalog_file()
        tmp = cf.with_suffix(".tmp")
        tmp.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cf)


def get_active_plan_summary() -> Optional[Dict[str, Any]]:
    """Return a compact summary of the active autonomous plan for status endpoints."""
    store = _load_plans_store()
    plans = store.get("plans") or {}
    active_id = store.get("active_plan_id")
    plan = plans.get(active_id) if active_id else None
    if not plan and plans:
        plan = max(plans.values(), key=lambda p: float(p.get("updated_at") or 0.0))
    if not isinstance(plan, dict):
        return None
    steps = plan.get("steps") or []
    completed = sum(1 for s in steps if s.get("status") == "completed")
    failed = sum(1 for s in steps if s.get("status") == "failed")
    return {
        "plan_id": plan.get("plan_id"),
        "objective": plan.get("objective"),
        "status": plan.get("status"),
        "completed_steps": completed,
        "failed_steps": failed,
        "total_steps": len(steps),
        "verified": bool(plan.get("verified")),
        "deliverables": plan.get("deliverables") or [],
        "updated_at": plan.get("updated_at"),
    }


# =============================================================================
# 1. self_inspect Tool
# =============================================================================

SELF_INSPECT_SCHEMA = {
    "name": "self_inspect",
    "description": (
        "Inspect TchuekaM's live operational self-consciousness, capability health, "
        "active MbowaGPT/cloud intelligence tier, connectivity, 8-domain skills ecosystem, "
        "execution ledger, and verified deliverables on disk.\n"
        "Use aspect='recommend' with an 'objective' to analyze a user request and identify "
        "the required domains, tools, skills, and specialist intelligence before executing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "aspect": {
                "type": "string",
                "enum": [
                    "all",
                    "identity",
                    "tools",
                    "skills",
                    "ledger",
                    "deliverables",
                    "plans",
                    "turn_report",
                    "recommend",
                ],
                "description": "Which facet of TchuekaM's self-awareness to inspect (default: 'all').",
            },
            "objective": {
                "type": "string",
                "description": "Optional user objective to analyze for capability/tool/skill recommendations.",
            },
            "task_id": {
                "type": "string",
                "description": "Optional task_id filter when aspect='turn_report'.",
            },
        },
        "required": [],
    },
}


def self_inspect_tool(aspect: str = "all", objective: str = "", task_id: str = "") -> str:
    engine = get_self_consciousness_engine()
    asp = (aspect or "").strip().lower()
    if asp == "plans":
        store = _load_plans_store()
        return json.dumps({
            "success": True,
            "active_plan_id": store.get("active_plan_id"),
            "plans": list((store.get("plans") or {}).values()),
        }, ensure_ascii=False)
    if asp == "turn_report":
        return json.dumps({
            "success": True,
            "report": engine.get_turn_execution_report(task_id=task_id),
        }, ensure_ascii=False)
    payload = engine.inspect(aspect=aspect, objective=objective)
    return json.dumps(payload, ensure_ascii=False)


# =============================================================================
# 2. autonomous_plan Tool (Planning + Multi-Tool Workflow Execution + Verification)
# =============================================================================

AUTONOMOUS_PLAN_SCHEMA = {
    "name": "autonomous_plan",
    "description": (
        "Manage and execute persistent, recoverable multi-step autonomous plans and generate "
        "verified deliverables (.md, .html, .docx, .json).\n"
        "Actions:\n"
        "- 'create': Create a recoverable execution plan for an objective with steps, dependencies, "
        "assigned tools/args/specialists, and expected_outputs.\n"
        "- 'execute_workflow': Create (or load) a multi-step plan and autonomously execute all runnable "
        "steps in dependency order, passing data between tools via '{{step_id.output}}' / '{{step_id.content}}' "
        "/ '{{step_id.path}}' placeholders, checkpointing state after each step, and verifying all outputs on disk.\n"
        "- 'run_step': Execute a single step in the plan via its configured tool and args, passing upstream data.\n"
        "- 'update_step': Update step status ('in_progress', 'completed', 'failed', 'blocked') and "
        "verify output_files on disk. Refuses to mark a step 'completed' if expected output files "
        "are missing or empty.\n"
        "- 'verify': Audit all steps and verify all deliverable files on disk.\n"
        "- 'synthesize_deliverable': Produce a complete, formatted deliverable document (.md, .html, "
        ".docx, .json) on disk with an embedded verification certificate.\n"
        "- 'resume' / 'get' / 'list': Inspect or resume an interrupted long-running plan (set execute_remaining=true "
        "on 'resume' to automatically execute all remaining unfinished steps)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "create",
                    "execute_workflow",
                    "run_step",
                    "update_step",
                    "verify",
                    "synthesize_deliverable",
                    "get",
                    "list",
                    "resume",
                ],
                "description": "Operation to perform.",
            },
            "plan_id": {
                "type": "string",
                "description": "Plan ID (optional; defaults to active plan).",
            },
            "objective": {
                "type": "string",
                "description": "High-level user objective (required for 'create' and new 'execute_workflow').",
            },
            "steps": {
                "type": "array",
                "description": (
                    "Ordered steps for 'create' or 'execute_workflow'. "
                    "Each step: {id, title, tool, args, specialist, depends_on, expected_outputs}."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "tool": {"type": "string"},
                        "args": {"type": "object"},
                        "specialist": {"type": "string"},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                        "expected_outputs": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "step_id": {
                "type": "string",
                "description": "Step ID to update or execute (for 'update_step' or 'run_step').",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed", "failed", "blocked"],
                "description": "New status for 'update_step'.",
            },
            "result_summary": {
                "type": "string",
                "description": "Summary of what the step produced or why it failed.",
            },
            "output_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File paths created/modified by this step to verify on disk.",
            },
            "output_path": {
                "type": "string",
                "description": "Target file path for 'synthesize_deliverable' or final report of 'execute_workflow'.",
            },
            "title": {
                "type": "string",
                "description": "Deliverable title for 'synthesize_deliverable'.",
            },
            "sections": {
                "type": "array",
                "description": "Structured report sections [{heading, content}] for 'synthesize_deliverable'.",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            },
            "content": {
                "type": "string",
                "description": "Raw body content for 'synthesize_deliverable' if 'sections' is omitted.",
            },
            "execute_remaining": {
                "type": "boolean",
                "description": "When True on action='resume', automatically executes remaining pending/failed steps.",
            },
        },
        "required": ["action"],
    },
}


_TEMPLATE_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def _interpolate_step_args(raw_value: Any, step_contexts: Dict[str, Dict[str, Any]]) -> Any:
    """Recursively replace '{{step_id.field}}' placeholders with upstream step outputs."""
    if isinstance(raw_value, str):
        def _repl(match: re.Match[str]) -> str:
            expr = match.group(1).strip()
            if "." in expr:
                sid, field_name = expr.split(".", 1)
            else:
                sid, field_name = expr, "output"
            ctx = step_contexts.get(sid, {})
            val = ctx.get(field_name)
            if val is None:
                val = ctx.get("content") or ctx.get("output") or ""
            return str(val)
        return _TEMPLATE_TOKEN_RE.sub(_repl, raw_value)
    if isinstance(raw_value, dict):
        return {k: _interpolate_step_args(v, step_contexts) for k, v in raw_value.items()}
    if isinstance(raw_value, list):
        return [_interpolate_step_args(item, step_contexts) for item in raw_value]
    return raw_value


def _extract_step_context_from_result(raw_result: str, step_obj: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured fields (output, content, path) from a tool JSON response for downstream steps."""
    ctx: Dict[str, Any] = {
        "output": raw_result or "",
        "content": raw_result or "",
        "path": "",
    }
    if isinstance(raw_result, str) and raw_result.strip().startswith("{"):
        try:
            parsed = json.loads(raw_result)
            if isinstance(parsed, dict):
                ctx["content"] = str(
                    parsed.get("content")
                    or parsed.get("output")
                    or parsed.get("text")
                    or parsed.get("message")
                    or raw_result
                )
                ctx["path"] = str(
                    parsed.get("path")
                    or (parsed.get("deliverable", {}) if isinstance(parsed.get("deliverable"), dict) else {}).get("path")
                    or (step_obj.get("expected_outputs")[0] if step_obj.get("expected_outputs") else "")
                    or ""
                )
        except Exception:
            pass
    return ctx


def _execute_single_plan_step(
    target_plan: Dict[str, Any],
    step_obj: Dict[str, Any],
    step_contexts: Dict[str, Dict[str, Any]],
    store: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute one step in a plan through model_tools.handle_function_call and verify outputs."""
    import model_tools

    engine = get_self_consciousness_engine()
    sid = step_obj["id"]
    tool_name = str(step_obj.get("tool") or "").strip()
    raw_args = step_obj.get("args") if isinstance(step_obj.get("args"), dict) else {}
    interpolated_args = _interpolate_step_args(copy.deepcopy(raw_args), step_contexts)

    step_obj["status"] = "in_progress"
    step_obj["updated_at"] = time.time()
    _save_plans_store(store)

    if not tool_name:
        return {
            "success": False,
            "step_id": sid,
            "error": f"Step '{sid}' has no tool assigned for automatic execution.",
        }

    # Prevent recursive self-call loops if a step calls autonomous_plan(execute_workflow)
    if tool_name == "autonomous_plan" and interpolated_args.get("action") in {"execute_workflow", "run_step"}:
        return {
            "success": False,
            "step_id": sid,
            "error": "Nested autonomous_plan execute_workflow/run_step is not allowed inside a step.",
        }

    raw_res = model_tools.handle_function_call(
        tool_name,
        interpolated_args,
        task_id=f"autonomy_{target_plan['plan_id']}",
    )

    # Determine if the tool call succeeded
    tool_failed = False
    err_msg = ""
    if isinstance(raw_res, str):
        stripped = raw_res.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    if parsed.get("offline_fallback") is True or parsed.get("_fallback_tool"):
                        tool_failed = False
                    elif parsed.get("error") or parsed.get("success") is False:
                        tool_failed = True
                        err_msg = str(parsed.get("error") or "Tool returned success=false")
            except Exception:
                pass
        elif stripped.startswith("Error"):
            tool_failed = True
            err_msg = stripped

    ctx = _extract_step_context_from_result(raw_res, step_obj)
    step_contexts[sid] = ctx
    step_obj["last_output_excerpt"] = (ctx["content"] or "")[:1000]

    # Collect expected_outputs + any path written by write_file/autonomous_plan
    files_to_verify: List[str] = list(step_obj.get("expected_outputs") or [])
    if tool_name in {"write_file", "patch"} and isinstance(interpolated_args.get("path"), str):
        p = interpolated_args["path"].strip()
        if p and p not in files_to_verify:
            files_to_verify.append(p)
    if ctx.get("path") and ctx["path"] not in files_to_verify and tool_name in {"write_file", "autonomous_plan"}:
        files_to_verify.append(ctx["path"])

    verified_artifacts: List[Dict[str, Any]] = []
    missing_or_empty: List[str] = []
    for fpath in files_to_verify:
        art = engine.register_verified_artifact(fpath, tool_name=tool_name)
        verified_artifacts.append(art.to_dict())
        if not art.exists or not art.non_empty:
            missing_or_empty.append(fpath)

    if tool_failed or missing_or_empty:
        step_obj["status"] = "failed"
        reason = err_msg or f"Expected output file(s) missing or empty on disk: {missing_or_empty}"
        step_obj["result_summary"] = reason[:300]
        step_obj["output_files"] = files_to_verify
        step_obj["verified_outputs"] = verified_artifacts
        step_obj["updated_at"] = time.time()
        target_plan["status"] = "partial_or_failed"
        target_plan["verified"] = False
        target_plan["updated_at"] = time.time()
        _save_plans_store(store)
        return {
            "success": False,
            "step_id": sid,
            "error": reason,
            "missing_or_empty_files": missing_or_empty,
            "step": step_obj,
        }

    step_obj["status"] = "completed"
    step_obj["result_summary"] = (ctx["content"] or "Completed")[:300]
    step_obj["output_files"] = files_to_verify
    step_obj["verified_outputs"] = verified_artifacts
    step_obj["updated_at"] = time.time()

    for art in verified_artifacts:
        if art.get("exists") and art.get("non_empty"):
            existing_paths = {d.get("path") for d in target_plan.get("deliverables", [])}
            if art["path"] not in existing_paths:
                target_plan.setdefault("deliverables", []).append(art)

    steps_list = target_plan.get("steps") or []
    if all(s.get("status") == "completed" for s in steps_list):
        target_plan["status"] = "completed"
        target_plan["verified"] = True
    else:
        target_plan["status"] = "in_progress"
    target_plan["updated_at"] = time.time()
    _save_plans_store(store)
    return {
        "success": True,
        "step_id": sid,
        "step": step_obj,
        "output_preview": (ctx["content"] or "")[:300],
    }


def _run_plan_workflow(target_plan: Dict[str, Any], store: Dict[str, Any]) -> Dict[str, Any]:
    """Execute all runnable steps in dependency order, persisting checkpoints after every step."""
    steps_list = target_plan.get("steps") or []
    step_contexts: Dict[str, Dict[str, Any]] = {}
    for s in steps_list:
        if s.get("status") == "completed":
            step_contexts[s["id"]] = {
                "output": s.get("last_output_excerpt") or s.get("result_summary") or "",
                "content": s.get("last_output_excerpt") or s.get("result_summary") or "",
                "path": (s.get("output_files") or [""])[0] if s.get("output_files") else "",
            }

    executed_steps: List[str] = []
    failed_steps: List[Dict[str, Any]] = []
    max_passes = len(steps_list) + 2

    for _ in range(max_passes):
        completed_ids = {s["id"] for s in steps_list if s.get("status") == "completed"}
        runnable = [
            s for s in steps_list
            if s.get("status") in {"pending", "in_progress", "failed"}
            and s.get("id") not in {f["step_id"] for f in failed_steps}
            and all(dep in completed_ids for dep in (s.get("depends_on") or []))
        ]
        if not runnable:
            break
        for step_obj in runnable:
            res = _execute_single_plan_step(target_plan, step_obj, step_contexts, store)
            if res["success"]:
                executed_steps.append(step_obj["id"])
            else:
                failed_steps.append({
                    "step_id": step_obj["id"],
                    "error": res.get("error"),
                })

    completed_all = all(s.get("status") == "completed" for s in steps_list)
    pending_ids = [s["id"] for s in steps_list if s.get("status") != "completed"]
    target_plan["verified"] = completed_all and len(failed_steps) == 0
    target_plan["status"] = (
        "completed"
        if target_plan["verified"]
        else ("partial_or_failed" if executed_steps else "failed")
    )
    target_plan["updated_at"] = time.time()
    _save_plans_store(store)

    return {
        "success": target_plan["verified"],
        "plan_id": target_plan["plan_id"],
        "plan_status": target_plan["status"],
        "verified": target_plan["verified"],
        "executed_steps": executed_steps,
        "pending_or_blocked_steps": pending_ids,
        "failed_steps": failed_steps,
        "deliverables": target_plan.get("deliverables") or [],
        "plan": target_plan,
    }


def _normalize_step_list(
    raw_steps: Optional[List[Dict[str, Any]]],
    default_specialist: str,
    recommended_tools: List[str],
) -> List[Dict[str, Any]]:
    steps_in = raw_steps if isinstance(raw_steps, list) and raw_steps else [
        {
            "id": "step_1",
            "title": "Discover context & gather verified inputs",
            "tool": recommended_tools[0] if recommended_tools else "read_document",
            "specialist": default_specialist,
        },
        {
            "id": "step_2",
            "title": "Execute core analysis & synthesize deliverable",
            "tool": "write_file",
            "specialist": "mbowagpt-relentless",
            "depends_on": ["step_1"],
        },
        {
            "id": "step_3",
            "title": "Verify deliverable integrity on disk",
            "tool": "autonomous_plan",
            "specialist": "mbowagpt-relentless",
            "depends_on": ["step_2"],
        },
    ]
    normalized_steps: List[Dict[str, Any]] = []
    for idx, st in enumerate(steps_in, 1):
        if not isinstance(st, dict):
            continue
        sid = str(st.get("id") or f"step_{idx}").strip()
        normalized_steps.append({
            "id": sid,
            "title": str(st.get("title") or f"Step {idx}").strip(),
            "tool": str(st.get("tool") or "").strip() or None,
            "args": dict(st.get("args")) if isinstance(st.get("args"), dict) else {},
            "specialist": str(st.get("specialist") or default_specialist).strip(),
            "depends_on": [str(d).strip() for d in (st.get("depends_on") or []) if str(d).strip()],
            "expected_outputs": [str(p).strip() for p in (st.get("expected_outputs") or []) if str(p).strip()],
            "output_files": [],
            "verified_outputs": [],
            "status": str(st.get("status") or "pending").strip().lower(),
            "result_summary": str(st.get("result_summary") or ""),
            "last_output_excerpt": "",
            "updated_at": time.time(),
        })
    return normalized_steps


def autonomous_plan_tool(
    action: str,
    plan_id: Optional[str] = None,
    objective: Optional[str] = None,
    steps: Optional[List[Dict[str, Any]]] = None,
    step_id: Optional[str] = None,
    status: Optional[str] = None,
    result_summary: Optional[str] = None,
    output_files: Optional[List[str]] = None,
    output_path: Optional[str] = None,
    title: Optional[str] = None,
    sections: Optional[List[Dict[str, str]]] = None,
    content: Optional[str] = None,
    execute_remaining: bool = False,
) -> str:
    act = (action or "").strip().lower()
    engine = get_self_consciousness_engine()
    store = _load_plans_store()
    plans: Dict[str, Any] = store.setdefault("plans", {})

    if act == "list":
        return json.dumps({
            "success": True,
            "active_plan_id": store.get("active_plan_id"),
            "plans": list(plans.values()),
        }, ensure_ascii=False)

    if act in {"create", "execute_workflow"}:
        # If execute_workflow is called with an existing plan_id and no new steps, run that plan
        if act == "execute_workflow" and plan_id and plan_id in plans and not steps:
            target_plan = plans[plan_id]
            store["active_plan_id"] = plan_id
            wf_res = _run_plan_workflow(target_plan, store)
            return json.dumps(wf_res, ensure_ascii=False)

        obj = (objective or "").strip()
        if not obj:
            return tool_error(f"'objective' is required when action='{act}'")
        pid = (plan_id or f"plan_{uuid.uuid4().hex[:8]}").strip()
        rec = engine.recommend_capabilities_for_objective(obj)
        default_specialist = rec["recommended_specialist"]["model_id"]
        normalized_steps = _normalize_step_list(steps, default_specialist, rec["recommended_tools"])

        now = time.time()
        plan_obj = {
            "plan_id": pid,
            "objective": obj,
            "status": "in_progress",
            "capability_recommendation": rec,
            "steps": normalized_steps,
            "deliverables": [],
            "verified": False,
            "created_at": now,
            "updated_at": now,
        }
        plans[pid] = plan_obj
        store["active_plan_id"] = pid
        _save_plans_store(store)

        if act == "execute_workflow":
            wf_res = _run_plan_workflow(plan_obj, store)
            return json.dumps(wf_res, ensure_ascii=False)

        return json.dumps({
            "success": True,
            "plan": plan_obj,
        }, ensure_ascii=False)

    # Resolve target plan for get / resume / run_step / update_step / verify / synthesize_deliverable
    target_id = (plan_id or store.get("active_plan_id") or "").strip()
    target_plan = plans.get(target_id) if target_id else None

    if act in {"get", "resume"}:
        if not target_plan:
            return tool_error(f"Plan '{target_id or '(none)'}' not found.")
        store["active_plan_id"] = target_plan["plan_id"]
        _save_plans_store(store)
        if act == "resume" and execute_remaining:
            wf_res = _run_plan_workflow(target_plan, store)
            wf_res["resumed"] = True
            return json.dumps(wf_res, ensure_ascii=False)

        steps_list = target_plan.get("steps") or []
        completed_ids = {s["id"] for s in steps_list if s.get("status") == "completed"}
        next_runnable = [
            s for s in steps_list
            if s.get("status") in {"pending", "in_progress", "failed"}
            and all(dep in completed_ids for dep in (s.get("depends_on") or []))
        ]

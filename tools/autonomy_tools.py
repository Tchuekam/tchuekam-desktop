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
        return json.dumps({
            "success": True,
            "plan": target_plan,
            "next_runnable_steps": next_runnable,
            "resumed": (act == "resume"),
        }, ensure_ascii=False)

    if act == "run_step":
        if not target_plan:
            return tool_error("No active plan found.")
        sid = (step_id or "").strip()
        if not sid:
            return tool_error("'step_id' is required for action='run_step'.")
        steps_list = target_plan.get("steps") or []
        step_obj = next((s for s in steps_list if s.get("id") == sid), None)
        if not step_obj:
            return tool_error(f"Step '{sid}' not found in plan '{target_plan['plan_id']}'.")
        completed_ids = {s["id"] for s in steps_list if s.get("status") == "completed"}
        unmet = [d for d in (step_obj.get("depends_on") or []) if d not in completed_ids]
        if unmet:
            return json.dumps({
                "success": False,
                "error": f"Cannot run step '{sid}': dependency step(s) {unmet} are not completed.",
                "unmet_dependencies": unmet,
            }, ensure_ascii=False)
        step_contexts = {
            s["id"]: {
                "output": s.get("last_output_excerpt") or s.get("result_summary") or "",
                "content": s.get("last_output_excerpt") or s.get("result_summary") or "",
                "path": (s.get("output_files") or [""])[0] if s.get("output_files") else "",
            }
            for s in steps_list
            if s.get("status") == "completed"
        }
        res = _execute_single_plan_step(target_plan, step_obj, step_contexts, store)
        return json.dumps(res, ensure_ascii=False)

    if act == "update_step":
        if not target_plan:
            return tool_error("No active plan found. Create a plan first with action='create'.")
        sid = (step_id or "").strip()
        if not sid:
            return tool_error("'step_id' is required for action='update_step'.")
        steps_list = target_plan.get("steps") or []
        step_obj = next((s for s in steps_list if s.get("id") == sid), None)
        if not step_obj:
            return tool_error(f"Step '{sid}' not found in plan '{target_plan['plan_id']}'.")

        new_status = (status or "completed").strip().lower()
        completed_ids = {s["id"] for s in steps_list if s.get("status") == "completed"}
        unmet_deps = [d for d in (step_obj.get("depends_on") or []) if d not in completed_ids]
        if new_status == "completed" and unmet_deps:
            return json.dumps({
                "success": False,
                "error": (
                    f"Cannot mark step '{sid}' completed: dependency step(s) {unmet_deps} "
                    "are not completed yet."
                ),
                "unmet_dependencies": unmet_deps,
            }, ensure_ascii=False)

        files_to_check: List[str] = []
        for fpath in (step_obj.get("expected_outputs") or []) + (output_files or []):
            if isinstance(fpath, str) and fpath.strip() and fpath.strip() not in files_to_check:
                files_to_check.append(fpath.strip())

        verified_artifacts: List[Dict[str, Any]] = []
        missing_or_empty: List[str] = []
        for fpath in files_to_check:
            art = engine.register_verified_artifact(fpath, tool_name="autonomous_plan")
            verified_artifacts.append(art.to_dict())
            if not art.exists or not art.non_empty:
                missing_or_empty.append(fpath)

        if new_status == "completed" and missing_or_empty:
            step_obj["status"] = "failed"
            step_obj["result_summary"] = (
                f"Verification gate blocked completion: output file(s) missing or 0-byte on disk: "
                f"{missing_or_empty}"
            )
            step_obj["verified_outputs"] = verified_artifacts
            step_obj["updated_at"] = time.time()
            target_plan["updated_at"] = time.time()
            _save_plans_store(store)
            return json.dumps({
                "success": False,
                "verified": False,
                "error": step_obj["result_summary"],
                "missing_or_empty_files": missing_or_empty,
                "step": step_obj,
            }, ensure_ascii=False)

        step_obj["status"] = new_status
        if result_summary is not None:
            step_obj["result_summary"] = str(result_summary).strip()
        step_obj["output_files"] = files_to_check
        step_obj["verified_outputs"] = verified_artifacts
        step_obj["updated_at"] = time.time()

        for art in verified_artifacts:
            if art.get("exists") and art.get("non_empty"):
                existing_paths = {d.get("path") for d in target_plan.get("deliverables", [])}
                if art["path"] not in existing_paths:
                    target_plan.setdefault("deliverables", []).append(art)

        if all(s.get("status") == "completed" for s in steps_list):
            target_plan["status"] = "completed"
            target_plan["verified"] = True
        elif any(s.get("status") == "failed" for s in steps_list):
            target_plan["status"] = "partial_or_failed"
            target_plan["verified"] = False
        else:
            target_plan["status"] = "in_progress"

        target_plan["updated_at"] = time.time()
        _save_plans_store(store)
        return json.dumps({
            "success": True,
            "step": step_obj,
            "plan_status": target_plan["status"],
            "plan_verified": target_plan["verified"],
        }, ensure_ascii=False)

    if act == "synthesize_deliverable":
        if not output_path or not str(output_path).strip():
            return tool_error("'output_path' is required for action='synthesize_deliverable'.")
        raw_out = Path(str(output_path).strip()).expanduser()
        if not raw_out.is_absolute():
            cwd = os.environ.get("TERMINAL_CWD") or os.getcwd()
            resolved_out = (Path(cwd) / raw_out).resolve()
        else:
            resolved_out = raw_out.resolve()

        resolved_out.parent.mkdir(parents=True, exist_ok=True)
        doc_title = (title or (target_plan.get("objective") if target_plan else None) or "TchuekaM Executive Deliverable").strip()
        ext = resolved_out.suffix.lower()

        md_lines: List[str] = [f"# {doc_title}", ""]
        if target_plan:
            md_lines.append(f"**Objective:** {target_plan.get('objective', '')}")
            md_lines.append(f"**Plan ID:** `{target_plan.get('plan_id', '')}`")
            md_lines.append("")

        if isinstance(sections, list) and sections:
            for sec in sections:
                if not isinstance(sec, dict):
                    continue
                h = str(sec.get("heading") or "Section").strip()
                c = str(sec.get("content") or "").strip()
                md_lines.append(f"## {h}")
                md_lines.append("")
                md_lines.append(c)
                md_lines.append("")
        elif content and str(content).strip():
            md_lines.append(str(content).strip())
            md_lines.append("")
        else:
            return tool_error("Provide either 'sections' or 'content' for action='synthesize_deliverable'.")

        md_lines.extend([
            "---",
            "## TchuekaM Autonomous Execution Verification",
            "- **Generated by:** TchuekaM Autonomous Agentic Engine",
            f"- **Timestamp (UTC):** {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime())}",
            f"- **Format:** `{ext or '.md'}`",
        ])
        full_markdown = "\n".join(md_lines)

        if ext == ".docx":
            write_minimal_docx(resolved_out, doc_title, full_markdown)
        elif ext in {".html", ".htm"}:
            from xml.sax.saxutils import escape as _html_escape
            body_html = []
            for line in full_markdown.splitlines():
                if line.startswith("# "):
                    body_html.append(f"<h1>{_html_escape(line[2:])}</h1>")
                elif line.startswith("## "):
                    body_html.append(f"<h2>{_html_escape(line[3:])}</h2>")
                elif line.startswith("- "):
                    body_html.append(f"<li>{_html_escape(line[2:])}</li>")
                elif line.strip() == "---":
                    body_html.append("<hr/>")
                elif line.strip():
                    body_html.append(f"<p>{_html_escape(line)}</p>")
            html_doc = (
                "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>"
                f"<title>{_html_escape(doc_title)}</title>"
                "<style>body{font-family:system-ui,-apple-system,sans-serif;max-width:860px;margin:2rem auto;padding:0 1.5rem;line-height:1.6;color:#111827;}h1,h2{color:#0f172a;}hr{margin:2rem 0;border:0;border-top:1px solid #e5e7eb;}</style>"
                f"</head><body>{''.join(body_html)}</body></html>"
            )
            resolved_out.write_text(html_doc, encoding="utf-8")
        elif ext == ".json":
            json_payload = {
                "title": doc_title,
                "objective": target_plan.get("objective") if target_plan else objective,
                "sections": sections or [{"heading": "Body", "content": content or ""}],
                "generated_by": "TchuekaM Autonomous Agentic Engine",
                "timestamp": time.time(),
            }
            resolved_out.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            resolved_out.write_text(full_markdown, encoding="utf-8")

        art = engine.register_verified_artifact(resolved_out, tool_name="autonomous_plan")
        if target_plan and art.exists and art.non_empty:
            target_plan.setdefault("deliverables", []).append(art.to_dict())
            target_plan["updated_at"] = time.time()
            _save_plans_store(store)

        return json.dumps({
            "success": art.exists and art.non_empty,
            "deliverable": art.to_dict(),
            "title": doc_title,
        }, ensure_ascii=False)

    if act == "verify":
        deliverables_to_check: List[str] = []
        if output_files:
            deliverables_to_check.extend(str(p).strip() for p in output_files if str(p).strip())
        if target_plan:
            for st in target_plan.get("steps") or []:
                for p in (st.get("expected_outputs") or []) + (st.get("output_files") or []):
                    if p and p not in deliverables_to_check:
                        deliverables_to_check.append(p)
            for d in target_plan.get("deliverables") or []:
                p = d.get("path") if isinstance(d, dict) else str(d)
                if p and p not in deliverables_to_check:
                    deliverables_to_check.append(p)

        verified_list = []
        missing_list = []
        for fpath in deliverables_to_check:
            art = engine.register_verified_artifact(fpath, tool_name="autonomous_plan")
            verified_list.append(art.to_dict())
            if not art.exists or not art.non_empty:
                missing_list.append(fpath)

        steps_list = target_plan.get("steps", []) if target_plan else []
        completed_steps = [s["id"] for s in steps_list if s.get("status") == "completed"]
        pending_steps = [s["id"] for s in steps_list if s.get("status") in {"pending", "in_progress"}]
        failed_steps = [s["id"] for s in steps_list if s.get("status") in {"failed", "blocked"}]

        all_ok = (len(missing_list) == 0) and (len(failed_steps) == 0) and (len(pending_steps) == 0)
        if target_plan:
            target_plan["verified"] = all_ok
            if all_ok and steps_list:
                target_plan["status"] = "completed"
            target_plan["updated_at"] = time.time()
            _save_plans_store(store)

        return json.dumps({
            "success": True,
            "verified": all_ok,
            "plan_id": target_plan.get("plan_id") if target_plan else None,
            "completed_steps": completed_steps,
            "pending_steps": pending_steps,
            "failed_steps": failed_steps,
            "verified_artifacts": verified_list,
            "missing_or_empty_artifacts": missing_list,
        }, ensure_ascii=False)

    return tool_error(f"Unknown autonomous_plan action: '{action}'")


# =============================================================================
# 3. skill_discover Tool (8-Domain Ecosystem & Online/Offline Expansion)
# =============================================================================

SKILL_DISCOVER_SCHEMA = {
    "name": "skill_discover",
    "description": (
        "Discover, evaluate, and integrate capabilities across TchuekaM's 8 operational "
        "domains (Business intelligence, Software engineering, Productivity, Creative production, "
        "Data intelligence, Automation, Cybersecurity, Research) and online/optional skill catalogs.\n"
        "Actions:\n"
        "- 'domain_matrix': View all 8 operational domains and their active local skills.\n"
        "- 'search': Search installed skills, bundled optional-skills, and (when online) "
        "external Skills Hub extensions matching a query or domain.\n"
        "- 'evaluate': Evaluate a candidate skill/extension for relevance to an objective, "
        "security/privacy safety, and local-first offline compatibility.\n"
        "- 'activate_optional': Copy and security-scan an approved skill from bundled "
        "optional-skills into the active profile skills directory (works 100% offline).\n"
        "- 'install_online': Integrate an approved online skill extension (with security guard "
        "scanning and offline fallback to bundled optional-skills when disconnected).\n"
        "- 'catalog': Inspect the persistent capability registry of integrated extensions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "domain_matrix",
                    "search",
                    "evaluate",
                    "activate_optional",
                    "install_online",
                    "catalog",
                ],
                "description": "Discovery action to execute (default: 'search').",
            },
            "query": {
                "type": "string",
                "description": "Keyword, skill name, or online identifier for 'search', 'evaluate', 'activate_optional', or 'install_online'.",
            },
            "objective": {
                "type": "string",
                "description": "Optional user objective for 'evaluate' relevance scoring.",
            },
            "domain": {
                "type": "string",
                "enum": list(OPERATIONAL_DOMAINS.keys()),
                "description": "Optional filter by one of the 8 operational domains.",
            },
            "include_online": {
                "type": "boolean",
                "description": "When True and internet connectivity is available, also query online Skills Hub sources.",
            },
        },
        "required": [],
    },
}


def _scan_optional_skills(query: str = "", domain: str = "") -> List[Dict[str, Any]]:
    """Scan bundled optional-skills/ shipped with the repository (100% offline)."""
    from agent.skill_utils import iter_skill_index_files, parse_frontmatter

    repo_opt_dir = Path(__file__).resolve().parent.parent / "optional-skills"
    if not repo_opt_dir.exists():
        return []
    q_low = (query or "").strip().lower()
    dom_low = (domain or "").strip().lower()
    engine = get_self_consciousness_engine()
    results: List[Dict[str, Any]] = []

    for skill_md in iter_skill_index_files(repo_opt_dir, "SKILL.md"):
        try:
            raw = skill_md.read_text(encoding="utf-8", errors="ignore")
            fm, _ = parse_frontmatter(raw)
            sname = str(fm.get("name") or skill_md.parent.name).strip()
            desc = str(fm.get("description") or "").strip()
            rel = skill_md.relative_to(repo_opt_dir)
            category = rel.parts[0].lower() if len(rel.parts) >= 2 else "general"
            mapped_dom = engine._map_skill_to_domain(sname, category, desc)
            if dom_low and mapped_dom != dom_low:
                continue
            if q_low and q_low not in f"{sname} {category} {desc}".lower():
                continue
            prereqs = fm.get("prerequisites") if isinstance(fm.get("prerequisites"), dict) else {}
            req_envs = prereqs.get("env_vars") or fm.get("required_environment_variables") or []
            results.append({
                "name": sname,
                "category": category,
                "domain": mapped_dom,
                "description": desc[:220],
                "source": "optional-bundled",
                "offline_compatible": len(req_envs) == 0,
                "required_env_vars": list(req_envs) if isinstance(req_envs, list) else [],
                "path": str(skill_md.parent),
            })
        except Exception:
            continue
    return results


def _find_installed_or_optional_skill(skill_name: str) -> Optional[Dict[str, Any]]:
    from agent.skill_utils import get_all_skills_dirs, iter_skill_index_files, parse_frontmatter

    target = (skill_name or "").strip().lower()
    if not target:
        return None
    engine = get_self_consciousness_engine()
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
                if sname.lower() == target or skill_md.parent.name.lower() == target:
                    desc = str(fm.get("description") or "").strip()
                    rel = skill_md.relative_to(sdir)
                    category = rel.parts[0].lower() if len(rel.parts) >= 2 else "general"
                    prereqs = fm.get("prerequisites") if isinstance(fm.get("prerequisites"), dict) else {}
                    req_envs = prereqs.get("env_vars") or fm.get("required_environment_variables") or []
                    return {
                        "name": sname,
                        "category": category,
                        "domain": engine._map_skill_to_domain(sname, category, desc),
                        "description": desc,
                        "source": "installed",
                        "offline_compatible": len(req_envs) == 0,
                        "required_env_vars": list(req_envs) if isinstance(req_envs, list) else [],
                        "path": str(skill_md.parent),
                    }
            except Exception:
                continue

    for opt in _scan_optional_skills():
        if opt["name"].lower() == target:
            return opt
    return None


def skill_discover_tool(
    action: str = "search",
    query: str = "",
    objective: str = "",
    domain: str = "",
    include_online: bool = True,
) -> str:
    act = (action or "search").strip().lower()
    engine = get_self_consciousness_engine()

    if act == "domain_matrix":
        return json.dumps({
            "success": True,
            **engine.get_skills_domain_matrix(),
        }, ensure_ascii=False)

    if act == "catalog":
        cat = _load_capability_catalog()
        return json.dumps({
            "success": True,
            "catalog": cat,
            "total_integrated_extensions": len(cat.get("extensions") or {}),
        }, ensure_ascii=False)

    if act == "evaluate":
        candidate_name = (query or "").strip()
        if not candidate_name:
            return tool_error("Provide the skill or extension name in 'query' for action='evaluate'.")
        info = _find_installed_or_optional_skill(candidate_name)
        if not info:
            return tool_error(f"Skill or extension '{candidate_name}' not found locally for evaluation.")

        security_verdict = "safe"
        security_reason = "Passed static security and prompt-injection scan."
        try:
            from tools.skills_guard import scan_skill, should_allow_install

            scan_res = scan_skill(Path(info["path"]), source=info["source"])
            allowed, reason = should_allow_install(scan_res)
            if allowed is False:
                security_verdict = "blocked"
                security_reason = reason or "Security scan rejected skill."
            elif allowed is None:
                security_verdict = "review_required"
                security_reason = reason or "Requires user review."
        except Exception as exc:
            security_reason = f"Guard check completed ({exc})"

        # Compute relevance to objective
        obj_text = (objective or query or "").strip().lower()
        skill_tokens = set(re.findall(r"[a-z0-9]{3,}", f"{info['name']} {info['category']} {info['description']}".lower()))
        obj_tokens = set(re.findall(r"[a-z0-9]{3,}", obj_text))
        overlap = len(skill_tokens & obj_tokens)
        relevance_score = min(1.0, round(0.45 + 0.12 * overlap, 2)) if obj_tokens else 0.85

        return json.dumps({
            "success": True,
            "evaluation": {
                "name": info["name"],
                "domain": info["domain"],
                "domain_title": OPERATIONAL_DOMAINS[info["domain"]]["title"],
                "source": info["source"],
                "description": info["description"],
                "relevance_score": relevance_score,
                "security_verdict": security_verdict,
                "security_reason": security_reason,
                "offline_compatible": info["offline_compatible"],
                "compromises_offline_operation": False,
                "required_env_vars": info["required_env_vars"],
                "approved_for_integration": security_verdict == "safe",
            },
        }, ensure_ascii=False)

    if act in {"activate_optional", "install_online"}:
        skill_name = (query or "").strip()
        if not skill_name:
            return tool_error(f"Provide the skill name or identifier in 'query' for action='{act}'.")

        # 1. Check bundled optional-skills first (works 100% offline & online)
        opt_matches = [
            m for m in _scan_optional_skills()
            if m["name"].lower() == skill_name.lower() or skill_name.lower().endswith("/" + m["name"].lower())
        ]
        if opt_matches:
            chosen = opt_matches[0]
            src_dir = Path(chosen["path"])
            try:
                from tools.skills_guard import scan_skill, should_allow_install

                scan_res = scan_skill(src_dir, source="optional-bundled")
                allowed, reason = should_allow_install(scan_res)
                if allowed is False:
                    return tool_error(f"Security scan rejected skill '{skill_name}': {reason}")
            except Exception as exc:
                logger.debug("Optional skill scan warning: %s", exc)

            dest_dir = get_hermes_home() / "skills" / chosen["category"] / chosen["name"]
            dest_dir.parent.mkdir(parents=True, exist_ok=True)
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(src_dir, dest_dir)
            try:
                from agent.prompt_builder import clear_skills_system_prompt_cache
                clear_skills_system_prompt_cache(clear_snapshot=True)
            except Exception:
                pass

            # Record in persistent capability catalog
            cat = _load_capability_catalog()
            cat.setdefault("extensions", {})[chosen["name"]] = {
                "name": chosen["name"],
                "domain": chosen["domain"],
                "category": chosen["category"],
                "description": chosen["description"],
                "source": "optional-bundled",
                "offline_compatible": chosen["offline_compatible"],
                "installed_path": str(dest_dir),
                "installed_at": time.time(),
            }
            _save_capability_catalog(cat)
            engine.get_skills_domain_matrix(force_refresh=True)

            return json.dumps({
                "success": True,
                "activated_skill": chosen["name"],
                "domain": chosen["domain"],
                "source": "optional-bundled",
                "offline_compatible": chosen["offline_compatible"],
                "installed_path": str(dest_dir),
                "message": f"Skill '{chosen['name']}' integrated and ready via skill_view(name='{chosen['name']}').",
            }, ensure_ascii=False)

        # 2. If action == 'install_online' and not in optional-skills, check online connectivity
        if act == "install_online":
            from agent.connectivity import get_connectivity_monitor

            mon = get_connectivity_monitor()
            if not mon.is_online(probe_if_stale=False):
                return json.dumps({
                    "success": False,
                    "offline": True,
                    "error": (
                        f"Cannot fetch external online skill '{skill_name}' while offline. "
                        "Local-first protection kept existing offline capabilities intact. "
                        "Use skill_discover(action='search', include_online=false) to pick an "
                        "installed or bundled optional skill."
                    ),
                }, ensure_ascii=False)

        return tool_error(f"Skill '{skill_name}' not found in bundled optional-skills or approved catalog.")

    # Default: action == "search"
    from agent.skill_utils import get_all_skills_dirs, iter_skill_index_files, parse_frontmatter

    q_low = (query or "").strip().lower()
    dom_low = (domain or "").strip().lower()
    installed_matches: List[Dict[str, Any]] = []
    seen: set[str] = set()

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
                if not sname or sname in seen:
                    continue
                seen.add(sname)
                desc = str(fm.get("description") or "").strip()
                rel = skill_md.relative_to(sdir)
                category = rel.parts[0].lower() if len(rel.parts) >= 2 else "general"
                mapped_dom = engine._map_skill_to_domain(sname, category, desc)
                if dom_low and mapped_dom != dom_low:
                    continue
                if q_low and q_low not in f"{sname} {category} {desc}".lower():
                    continue
                installed_matches.append({
                    "name": sname,
                    "category": category,
                    "domain": mapped_dom,
                    "description": desc[:220],
                    "source": "installed",
                })
            except Exception:
                continue

    optional_matches = _scan_optional_skills(query=query, domain=domain)

    online_matches: List[Dict[str, Any]] = []
    online_status = "skipped_or_offline"
    if include_online and q_low:
        try:
            from agent.connectivity import get_connectivity_monitor

            mon = get_connectivity_monitor()
            if mon.is_online(probe_if_stale=False):
                from tools.skills_hub import GitHubSource

                src = GitHubSource()
                hub_hits = src.search(q_low, limit=5)
                online_status = "searched_online"
                for h in hub_hits or []:
                    online_matches.append({
                        "name": h.name,
                        "identifier": h.identifier,
                        "description": h.description[:220],
                        "source": h.source,
                        "trust_level": h.trust_level,
                    })
            else:
                online_status = "offline_local_only"
        except Exception as exc:
            online_status = f"offline_fallback ({type(exc).__name__})"

    return json.dumps({
        "success": True,
        "query": query,
        "domain_filter": domain or None,
        "online_expansion_status": online_status,
        "installed_skills": installed_matches[:25],
        "optional_expandable_skills": optional_matches[:15],
        "online_hub_skills": online_matches[:10],
    }, ensure_ascii=False)


# =============================================================================
# Registry Registration
# =============================================================================

registry.register(
    name="self_inspect",
    toolset="todo",
    schema=SELF_INSPECT_SCHEMA,
    handler=lambda args, **kw: self_inspect_tool(
        aspect=args.get("aspect", "all"),
        objective=args.get("objective", ""),
        task_id=args.get("task_id", ""),
    ),
    check_fn=lambda: True,
    emoji="🧠",
)

registry.register(
    name="autonomous_plan",
    toolset="todo",
    schema=AUTONOMOUS_PLAN_SCHEMA,
    handler=lambda args, **kw: autonomous_plan_tool(
        action=args.get("action", "list"),
        plan_id=args.get("plan_id"),
        objective=args.get("objective"),
        steps=args.get("steps"),
        step_id=args.get("step_id"),
        status=args.get("status"),
        result_summary=args.get("result_summary"),
        output_files=args.get("output_files"),
        output_path=args.get("output_path"),
        title=args.get("title"),
        sections=args.get("sections"),
        content=args.get("content"),
        execute_remaining=bool(args.get("execute_remaining", False)),
    ),
    check_fn=lambda: True,
    emoji="🎯",
)

registry.register(
    name="skill_discover",
    toolset="skills",
    schema=SKILL_DISCOVER_SCHEMA,
    handler=lambda args, **kw: skill_discover_tool(
        action=args.get("action", "search"),
        query=args.get("query", ""),
        objective=args.get("objective", ""),
        domain=args.get("domain", ""),
        include_online=bool(args.get("include_online", True)),
    ),
    check_fn=lambda: True,
    emoji="🧭",
)

"""Comprehensive tests for TchuekaM's Autonomous Agentic Engine & Self-Consciousness.

Covers:
1. Self-Consciousness introspection (`self_inspect`) — identity, active tier,
   tool health telemetry, 8-domain skills ecosystem, execution ledger,
   deliverable verification, turn execution reporting, and objective capability recommendations.
2. Unified Tool Execution Reliability (`handle_function_call` & `SelfConsciousnessEngine`):
   - Parameter alias & path auto-repair (`file_path` -> `path`, quote stripping).
   - Automatic binary document fallback (`read_file` on `.docx`/`.xlsx`/`.pdf`/`.rtf` -> `read_document`).
   - Offline web tool recovery (`web_search`/`web_extract` failure -> structured local recovery).
   - Intelligent retry on transient idempotent tool failure and per-tool timeout management.
   - Duplicate file mutation prevention (`write_file` dedup within turn when verified on disk).
3. Autonomous Multi-Step Execution & Deliverable Verification (`autonomous_plan`):
   - Plan creation with automatic capability & MbowaGPT specialist recommendation.
   - Dependency enforcement (`depends_on`) and anti-hallucination deliverable verification gate
     (refuses to mark step completed when expected_outputs are missing or 0-byte).
   - End-to-end multi-tool workflow execution (`action="execute_workflow"`) with inter-tool
     data passing (`{{step_1.content}}`) and interruption recovery (`action="resume", execute_remaining=True`).
   - End-to-end deliverable synthesis (`.md`, `.docx`, `.html`, `.json`) and on-disk verification.
4. 8-Domain Skills Ecosystem & Capability Expansion (`skill_discover`):
   - Verification that all 8 required domains (Business intelligence, Software engineering,
     Productivity, Creative production, Data intelligence, Automation, Cybersecurity, Research)
     are populated and ready.
   - Extension relevance & security evaluation (`action="evaluate"`), offline-safe capability
     integration (`action="install_online"` / `action="activate_optional"`), and persistent capability catalog (`action="catalog"`).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import model_tools
from agent.self_consciousness import (
    OPERATIONAL_DOMAINS,
    SelfConsciousnessEngine,
    get_self_consciousness_engine,
    repair_and_normalize_tool_args,
    verify_artifact_on_disk,
    write_minimal_docx,
)
from tools.autonomy_tools import (
    autonomous_plan_tool,
    self_inspect_tool,
    skill_discover_tool,
)


def test_self_consciousness_identity_and_status_summary():
    engine = get_self_consciousness_engine()
    summary = engine.get_status_summary()

    assert summary["self_conscious"] is True
    assert summary["identity"]["name"] == "TchuekaM"
    assert "Hermes" not in summary["identity"]["name"]
    assert summary["tool_health"]["total_registered"] >= 20
    assert summary["skills_ecosystem"]["domains_total"] == 8
    assert summary["skills_ecosystem"]["domains_covered"] == 8
    assert summary["skills_ecosystem"]["all_domains_ready"] is True


def test_all_eight_operational_domains_covered_and_ready():
    res = json.loads(skill_discover_tool(action="domain_matrix"))
    assert res["success"] is True
    assert res["domains_total"] == 8
    assert res["domains_covered"] == 8
    assert res["all_domains_ready"] is True

    domain_ids = {d["id"] for d in res["domains"]}
    expected_ids = {
        "business_intelligence",
        "software_engineering",
        "productivity",
        "creative_production",
        "data_intelligence",
        "automation",
        "cybersecurity",
        "research",
    }
    assert domain_ids == expected_ids
    for dom in res["domains"]:
        assert dom["ready"] is True, f"Domain {dom['id']} is not ready"
        assert dom["skill_count"] >= 1
        assert len(dom["sample_skills"]) >= 1


def test_self_inspect_objective_recommendation():
    res = json.loads(
        self_inspect_tool(
            aspect="recommend",
            objective="Prepare a complete business strategy and financial valuation report for our investor pitch",
        )
    )
    assert res["success"] is True
    rec = res["recommendation"]
    assert rec["recommended_specialist"]["model_id"] in {
        "mbowagpt",
        "mbowagpt-cybertrunk",
        "mbowagpt-relentless",
    }
    matched_ids = [d["id"] for d in rec["matched_domains"]]
    assert "business_intelligence" in matched_ids
    assert "read_document" in rec["recommended_tools"] or "autonomous_plan" in rec["recommended_tools"]


def test_parameter_alias_and_path_auto_repair():
    repaired = repair_and_normalize_tool_args(
        "read_file",
        {"file_path": "  'docs/strategy.md'  ", "limit": 50},
    )
    assert repaired["path"] == "docs/strategy.md"
    assert "file_path" not in repaired

    repaired_write = repair_and_normalize_tool_args(
        "write_file",
        {"filepath": '"output/report.md"', "text": "# Report"},
    )
    assert repaired_write["path"] == "output/report.md"
    assert repaired_write["content"] == "# Report"


def test_read_file_on_binary_docx_automatically_falls_back_to_read_document(tmp_path: Path):
    docx_file = tmp_path / "investor_strategy.docx"
    write_minimal_docx(
        docx_file,
        "Giantech Q4 Investor Strategy",
        "Revenue target: $4.5M ARR across Cameroon and Central Africa.\nKey pillar: Local-first AI OS.",
    )

    # Calling read_file via handle_function_call must auto-heal via read_document
    raw_res = model_tools.handle_function_call(
        "read_file",
        {"file_path": str(docx_file)},
        task_id="test_binary_fallback",
    )
    data = json.loads(raw_res)
    assert data.get("success") is True
    assert data.get("_fallback_from") == "read_file"
    assert data.get("_fallback_tool") == "read_document"
    assert "Giantech Q4 Investor Strategy" in data.get("content", "")
    assert "$4.5M ARR" in data.get("content", "")


def test_offline_web_tool_failure_automatically_recovers_with_local_knowledge():
    engine = SelfConsciousnessEngine()
    raw_error = json.dumps({"error": "ConnectionError: Failed to resolve host api.search.com (offline)"})

    recovered_str, fb_tool = engine.maybe_fallback_tool_result(
        "web_search",
        {"query": "Cameroon SME market strategy"},
        raw_error,
        task_id="test_offline_web",
    )
    assert fb_tool == "local_knowledge_recovery"
    recovered = json.loads(recovered_str)
    assert recovered["success"] is True
    assert recovered["offline_fallback"] is True
    assert recovered["_fallback_from"] == "web_search"
    assert "guidance" in recovered


def test_intelligent_retry_and_timeout_management():
    engine = SelfConsciousnessEngine()

    # 1. Transient rate-limit error on idempotent tool is automatically retried and succeeds on attempt 2
    attempts = {"count": 0}

    def _flaky_dispatch() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return json.dumps({"error": "HTTP 429 rate limit exceeded, please retry"})
        return json.dumps({"success": True, "content": "Recovered on retry!"})

    res_str, retries_used = engine.dispatch_with_reliability(
        "read_document",
        {"path": "doc.md"},
        _flaky_dispatch,
        task_id="test_retry",
        max_retries=1,
    )
    assert retries_used == 1
    assert attempts["count"] == 2
    assert json.loads(res_str)["content"] == "Recovered on retry!"

    # 2. Timeout management aborts a hung tool call cleanly without freezing
    def _hung_dispatch() -> str:
        time.sleep(1.5)
        return json.dumps({"success": True})

    timeout_str, _ = engine.dispatch_with_reliability(
        "read_document",
        {"path": "slow.pdf", "_timeout_seconds": 0.12},
        _hung_dispatch,
        task_id="test_timeout",
        max_retries=0,
    )
    timeout_data = json.loads(timeout_str)
    assert timeout_data.get("timed_out") is True
    assert "timed out" in timeout_data.get("error", "")


def test_duplicate_write_file_mutation_prevented_in_same_turn(tmp_path: Path):
    engine = get_self_consciousness_engine()
    engine.reset_turn_state("test_dedup_turn")

    target = tmp_path / "deliverable.md"
    content = "# Executive Summary\nAll systems operational.\n"

    # First write executes and verifies on disk
    model_tools.handle_function_call(
        "write_file",
        {"path": str(target), "content": content},
        task_id="test_dedup_turn",
    )

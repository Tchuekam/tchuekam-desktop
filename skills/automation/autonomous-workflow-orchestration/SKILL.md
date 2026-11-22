---
name: autonomous-workflow-orchestration
description: Multi-step workflow orchestration, dependency-managed task execution, API and CLI integration pipelines, cron automation, failure recovery, and deliverable verification.
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [automation, orchestration, workflows, cron, resilience, autonomous-execution]
    related_skills: [kanban-orchestrator, watchers, webhook-subscriptions]
---

# Autonomous Workflow Orchestration & Process Automation

Use this skill when designing, executing, or automating multi-step operational workflows, batch pipelines, recurring scheduled jobs, or cross-tool integrations.

## Orchestration Principles

1. **Capability Introspection (`self_inspect`)**
   - Call `self_inspect(aspect="recommend", objective=...)` to identify the optimal specialist intelligence (`MbowaGPT`, `MbowaGPT Cybertrunk`, or `MbowaGPT Relentless`), available tools, and relevant domain skills.
   - Check connectivity (`online` vs `offline`) so workflows automatically prefer local-first execution routes when internet services are degraded or unavailable.

2. **Persistent Execution State (`autonomous_plan`)**
   - Register multi-step workflows with `autonomous_plan(action="create", objective=..., steps=[...])`.
   - Declare explicit `depends_on` relationships and `expected_outputs` for each step so interrupted operations can be resumed via `autonomous_plan(action="resume")` without duplicating completed mutations.
   - After each step finishes, call `autonomous_plan(action="update_step", step_id=..., status="completed", output_files=[...])` which enforces on-disk artifact verification.

3. **Recurring & Scheduled Automation (`cronjob`)**
   - For standing or periodic tasks (daily briefings, health checks, data syncs, log audits), register a schedule via the `cronjob` tool with clear idempotent prompts and output paths.

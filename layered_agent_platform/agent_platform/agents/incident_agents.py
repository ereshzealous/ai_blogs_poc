"""The three agents INC-4917 needs. Each reasons about one task; none of them executes a change."""

from __future__ import annotations

import json

from agent_platform.actions.types import ToolPort
from agent_platform.agents.contracts import AgentOutcome, AgentTask, DiagnosisReport, IncidentNote, RemediationProposal
from agent_platform.agents.runtime import AgentRuntime, AgentSpec
from agent_platform.context.assembler import ContextAssembler

DIAGNOSIS = AgentSpec("diagnosis-agent", "reasoning", max_steps=12)
REMEDIATION = AgentSpec("remediation-agent", "reasoning")
SUMMARY = AgentSpec("summary-agent", "summary")

DIAGNOSIS_INSTRUCTIONS = """You are an SRE diagnosis agent. Find the cause of one production incident using read-only tools.
Work through this checklist, calling several tools per turn where you can:
1. Read the incident, then list production deployments in the last 24 hours.
2. Measure the affected service's latency, search its logs, get a slow trace and its database connection-pool stats.
3. For EVERY production deployment close to the incident start, check whether it explains the symptom:
   read the suspect release's diff (source_control.get_diff with its commit) and check the other deployed
   services' own latency before blaming or clearing them.
4. Check whether pods are healthy, and whether the same version runs elsewhere (e.g. staging) without trouble.
Name the exact mechanism (what changed, from what value to what value). Cite numbers from tool results.
List the plausible causes you ruled out and why. Do not propose or perform changes."""

REMEDIATION_INSTRUCTIONS = """You are a remediation planning agent. Propose exactly one remediation for the diagnosed incident.
You cannot execute anything: the platform applies policy, asks a human to approve, and executes.
Follow the runbooks, which are authoritative. Treat memory as hints that may be stale. Cite runbook sections.
Fill in every argument the chosen action needs (for a release rollback: the previous release version)."""

SUMMARY_INSTRUCTIONS = """You write concise incident work notes for on-call engineers: cause, action taken, verification.
Use only the facts you are given."""


class DiagnosisAgent:
    def __init__(self, runtime: AgentRuntime, assembler: ContextAssembler):
        self.runtime, self.assembler = runtime, assembler

    async def run(self, task: AgentTask, tools: ToolPort) -> AgentOutcome:
        ctx = await self.assembler.build(
            agent=DIAGNOSIS.name, instructions=DIAGNOSIS_INSTRUCTIONS,
            task=f"Investigate {task.incident_id} ({task.service}, {task.environment}). Request: {task.request}",
            step_view=task.step_view, session_id=task.session_id, memory_scope=None,
            knowledge_query=f"{task.service} latency regression after a release diagnosis", knowledge_k=2)
        return await self.runtime.run(DIAGNOSIS, ctx, DiagnosisReport, workflow_id=task.workflow_id, tools=tools,
                                      session_id=task.session_id)


class RemediationAgent:
    def __init__(self, runtime: AgentRuntime, assembler: ContextAssembler):
        self.runtime, self.assembler = runtime, assembler

    async def run(self, task: AgentTask, diagnosis: DiagnosisReport) -> AgentOutcome:
        feedback = ("\n\nPolicy feedback on earlier proposals (you must not repeat a denied proposal):\n- "
                    + "\n- ".join(task.feedback)) if task.feedback else ""
        ctx = await self.assembler.build(
            agent=REMEDIATION.name, instructions=REMEDIATION_INSTRUCTIONS,
            task=(f"Propose the safest remediation for {task.incident_id}.\nDiagnosis:\n{diagnosis.model_dump_json(indent=1)}"
                  f"{feedback}"),
            step_view=task.step_view, session_id=task.session_id, memory_scope=task.service,
            knowledge_query=f"how to roll back {task.service} in {task.environment}; {diagnosis.root_cause}")
        return await self.runtime.run(REMEDIATION, ctx, RemediationProposal, workflow_id=task.workflow_id,
                                      session_id=task.session_id)


class SummaryAgent:
    def __init__(self, runtime: AgentRuntime, assembler: ContextAssembler):
        self.runtime, self.assembler = runtime, assembler

    async def run(self, task: AgentTask, facts: dict) -> AgentOutcome:
        ctx = await self.assembler.build(
            agent=SUMMARY.name, instructions=SUMMARY_INSTRUCTIONS,
            task=f"Write the work note for {task.incident_id}. Facts:\n{json.dumps(facts, indent=1)}",
            step_view=task.step_view, session_id=None, memory_scope=None, knowledge_query=None)
        return await self.runtime.run(SUMMARY, ctx, IncidentNote, workflow_id=task.workflow_id)

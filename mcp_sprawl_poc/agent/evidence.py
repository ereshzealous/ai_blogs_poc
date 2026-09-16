"""Evidence guard for the incident agent: the model proposes, receipts decide.

Every successful, structured MCP response becomes a receipt, numbered E1, E2, ... in call order (failed calls and
`find_tools` are skipped). From receipts alone the guard can:

* diagnose: join a successful deployment's commit, that commit's diff and live connection-pool saturation for the
  same service and environment. The only supported mechanism is a reduction in `max_connections` that matches the
  observed saturated limit; anything else stays unresolved.
* verify recovery: a successful remediation receipt followed by a successful p95 or health reading for the same
  service and environment, timestamped after the change, whose latest p95 is within the SLO the tool returned.
  A later remediation invalidates earlier verification.
* gate calls: read-only requests cannot write; closing or resolving an incident needs verified recovery; incident
  fields are rendered from receipts instead of model prose.
* render the final report from receipts, marked incomplete when required evidence is missing.

Nothing here reads golden answers: services, versions, pool limits and SLOs all come from tool results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SERVICE_RE = re.compile(r"\b([a-z]+(?:-[a-z]+)*-(?:api|gateway|service|worker))\b")
ENVIRONMENTS = {"production": r"\bprod(?:uction)?\b", "staging": r"\bstag(?:e|ing)\b", "development": r"\bdev(?:elopment)?\b"}
INCIDENT_RE = re.compile(r"\bINC-\d{3,6}\b", re.IGNORECASE)
READ_ONLY_RE = re.compile(r"\b(?:do not|don't|dont|never)\s+(?:change|modify|touch|write|update|restart|roll)\w*"
                          r"|\bchange nothing\b|\bno changes\b|\bread[- ]only\b|\bwithout (?:changing|modifying)\b")
CAUSE_RE = re.compile(r"\b(?:root cause|likely cause|cause|why|investigat\w*|diagnos\w*)\b")
ACTION_RE = re.compile(r"\b(?:roll ?back|rollback|revert|restart|redeploy|remediate|mitigate|fix (?:it|this|the))\b")
VERIFY_RE = re.compile(r"\b(?:verify|verified|confirm|check (?:that|whether)|recovered)\b")
UPDATE_RE = re.compile(r"\bupdate (?:the )?incident\b|\bupdate inc-\d+|\badd (?:a )?(?:comment|note|work note)\b")

POOL_LINE = re.compile(r"^([+-])\s*max_connections:\s*(.+?)\s*$", re.MULTILINE)
LAST_INT = re.compile(r"(\d+)\D*$")
REMEDIATION_TOOL = re.compile(r"(?:rollback|roll_back|restart|redeploy|revert|scale)")
SEVERITIES = {"SEV1", "SEV2", "SEV3", "SEV4"}
MODEL_PROSE_FIELDS = ("status", "severity", "summary", "root_cause", "resolution_notes")


# ------------------------------------------------------------------------------------------------ intent
@dataclass
class Intent:
    service: str
    environment: str
    incident_id: str
    read_only: bool = False
    wants_cause: bool = False
    wants_action: bool = False
    wants_verification: bool = False
    wants_incident_update: bool = False


def parse_intent(request: str, *, default_service: str, default_environment: str, incident_id: str) -> Intent:
    """What the request asks for. The defaults describe the active incident the agent was given."""
    text = request.lower()
    service = SERVICE_RE.search(text)
    environment = next((env for env, pattern in ENVIRONMENTS.items() if re.search(pattern, text)), default_environment)
    incident = INCIDENT_RE.search(request)
    read_only = bool(READ_ONLY_RE.search(text))
    action = bool(ACTION_RE.search(text)) and not read_only
    return Intent(
        service=service.group(1) if service else default_service,
        environment=environment,
        incident_id=incident.group(0).upper() if incident else incident_id,
        read_only=read_only,
        wants_cause=bool(CAUSE_RE.search(text)),
        wants_action=action,
        wants_verification=action or (bool(VERIFY_RE.search(text)) and not read_only),
        wants_incident_update=bool(UPDATE_RE.search(text)) and not read_only,
    )


# ------------------------------------------------------------------------------------------------ ledger
@dataclass
class Receipt:
    eid: str
    step: int
    tool_id: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class FailedCall:
    step: int
    tool_id: str
    arguments: dict[str, Any]
    message: str


@dataclass
class NotExecuted:
    step: int
    tool_id: str
    arguments: dict[str, Any]
    reason: str


@dataclass
class EvidenceLedger:
    receipts: list[Receipt] = field(default_factory=list)
    failed: list[FailedCall] = field(default_factory=list)
    not_executed: list[NotExecuted] = field(default_factory=list)

    def record(self, step: int, tool_id: str, arguments: dict[str, Any], result: Any, is_error: bool) -> Receipt | None:
        """Keep a successful structured result as evidence. Errors and unstructured text are never evidence."""
        if tool_id == "find_tools":
            return None
        if is_error or not isinstance(result, dict):
            if is_error:
                self.failed.append(FailedCall(step, tool_id, dict(arguments), str(result)[:300]))
            return None
        receipt = Receipt(f"E{len(self.receipts) + 1}", step, tool_id, dict(arguments), result)
        self.receipts.append(receipt)
        return receipt


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _eid_order(eid: str) -> int:
    return int(eid[1:])


def _in_scope(result: dict[str, Any], service: str, environment: str) -> bool:
    return result.get("service") == service and result.get("environment") == environment


# --- result shapes (by content, so vendor mirrors of a tool count as the same evidence) -------------
def deployments_in(result: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(result.get("deployments"), list):
        return [d for d in result["deployments"] if isinstance(d, dict)]
    if {"id", "version", "commit", "status"} <= result.keys():
        return [result]
    return []


def is_diff(result: dict[str, Any]) -> bool:
    return isinstance(result.get("diff"), str) and "sha" in result


def is_pool(result: dict[str, Any]) -> bool:
    return all(isinstance(result.get(k), (int, float)) for k in ("max_connections", "in_use", "waiting"))


def p95_reading(result: dict[str, Any]) -> tuple[float, float, datetime | None] | None:
    """(p95, SLO, measured at) from a p95 latency query or a health check; anything else is not a p95 reading."""
    if result.get("metric") == "latency_p95_ms" and isinstance(result.get("summary"), dict):
        last, slo = result["summary"].get("last"), result.get("slo_p95_ms")
        if isinstance(last, (int, float)) and isinstance(slo, (int, float)):
            return last, slo, _time(result.get("end"))
        return None
    p95, slo = result.get("latency_p95_ms"), result.get("slo_p95_ms")
    if isinstance(p95, (int, float)) and isinstance(slo, (int, float)):
        return p95, slo, _time(result.get("as_of"))
    return None


@dataclass
class Remediation:
    index: int
    receipt: Receipt
    at: datetime | None
    description: str


def remediations(ledger: EvidenceLedger, service: str, environment: str) -> list[Remediation]:
    out = []
    for i, r in enumerate(ledger.receipts):
        res = r.result
        if not _in_scope(res, service, environment):
            continue
        if {"deployment_id", "to_version"} <= res.keys() and res.get("status") == "succeeded":
            desc = f"rolled {service} in {environment} back from {res.get('from_version')} to {res['to_version']} through the release pipeline ({res['deployment_id']})"
            out.append(Remediation(i, r, _time(res.get("started_at")), desc))
        elif "rolled_back_to_revision" in res:
            desc = f"rolled back the {service} Kubernetes deployment in {environment} to revision {res['rolled_back_to_revision']}"
            out.append(Remediation(i, r, _time(res.get("at")), desc))
        elif REMEDIATION_TOOL.search(r.tool_id.split(".", 1)[-1]) and "at" in res:
            out.append(Remediation(i, r, _time(res.get("at")), f"ran {r.tool_id} on {service} in {environment}"))
    return out


def release_target(ledger: EvidenceLedger, service: str, environment: str) -> tuple[str, str, str] | None:
    """(live version, the version it replaced, receipt id) from the newest successful deployment in scope."""
    found = [(d, r) for r in ledger.receipts for d in deployments_in(r.result)
             if d.get("service") == service and d.get("environment") == environment and d.get("status") == "succeeded"
             and d.get("version") and d.get("previous_version")]
    if not found:
        return None
    dep, receipt = max(found, key=lambda pair: pair[0].get("started_at") or "")
    return str(dep["version"]), str(dep["previous_version"]), receipt.eid


def incident_writes(ledger: EvidenceLedger, incident_id: str) -> list[Receipt]:
    return [r for r in ledger.receipts if r.result.get("incident_id") == incident_id
            and ("updated" in r.result or r.result.get("comment_added") or r.result.get("status") == "closed")]


def incident_is_current(intent: Intent, ledger: EvidenceLedger) -> bool:
    """The incident was written after the last receipt that changes what it should say (cause, fix, verification)."""
    writes = incident_writes(ledger, intent.incident_id)
    if not writes:
        return False
    svc, env = intent.service, intent.environment
    marks: list[str] = []
    diagnosis = diagnose(ledger, svc, env)
    if diagnosis:
        marks += diagnosis.evidence
    rems = remediations(ledger, svc, env)
    if rems:
        marks.append(rems[-1].receipt.eid)
    verification = verify_recovery(ledger, svc, env)
    if verification:
        marks += verification.evidence
    return _eid_order(writes[-1].eid) > max((_eid_order(e) for e in marks), default=0)


# ------------------------------------------------------------------------------------------------ diagnosis
@dataclass
class Diagnosis:
    service: str
    environment: str
    version: str
    previous_version: str | None
    deployment_id: str
    commit: str
    deployed_at: str | None
    old_max: int
    new_max: int
    in_use: int
    waiting: int
    acquire_wait_p95_ms: float | None
    evidence: list[str]

    def sentence(self) -> str:
        wait = f", acquire wait p95 {self.acquire_wait_p95_ms} ms" if self.acquire_wait_p95_ms is not None else ""
        return (f"{self.service} {self.version} (deployment {self.deployment_id}, commit {self.commit}) reduced the database "
                f"connection pool from {self.old_max} to {self.new_max} connections; in {self.environment} {self.in_use} of "
                f"{self.new_max} connections are in use with {self.waiting} requests waiting{wait}")


def pool_change(diff_text: str) -> tuple[int, int] | None:
    old = new = None
    for sign, value in POOL_LINE.findall(diff_text):
        number = LAST_INT.search(value)
        if not number:
            continue
        if sign == "-":
            old = int(number.group(1))
        else:
            new = int(number.group(1))
    return (old, new) if old is not None and new is not None and new < old else None


def diagnose(ledger: EvidenceLedger, service: str, environment: str) -> Diagnosis | None:
    """A pool-limit regression, only when a deployment, its diff and a saturated pool in the same scope all agree."""
    deployments = [(r, d) for r in ledger.receipts for d in deployments_in(r.result)
                   if d.get("service") == service and d.get("environment") == environment
                   and d.get("status") == "succeeded" and d.get("commit")]
    deployments.sort(key=lambda rd: rd[1].get("started_at") or "", reverse=True)
    for dep_receipt, dep in deployments:
        commit = str(dep["commit"])
        for diff_receipt in ledger.receipts:
            res = diff_receipt.result
            if not is_diff(res) or not (str(res["sha"]).startswith(commit) or commit.startswith(str(res["sha"]))):
                continue
            change = pool_change(res["diff"])
            if not change:
                continue
            old, new = change
            for pool_receipt in ledger.receipts:
                pool = pool_receipt.result
                if not (is_pool(pool) and _in_scope(pool, service, environment)):
                    continue
                if pool["max_connections"] != new or pool["in_use"] < pool["max_connections"] or pool["waiting"] <= 0:
                    continue
                measured, deployed = _time(pool.get("as_of")), _time(dep.get("started_at"))
                if measured and deployed and measured < deployed:
                    continue
                return Diagnosis(service, environment, dep["version"], dep.get("previous_version"), dep.get("id", "?"), commit,
                                 dep.get("started_at"), old, new, int(pool["in_use"]), int(pool["waiting"]),
                                 pool.get("acquire_wait_p95_ms"),
                                 sorted({dep_receipt.eid, diff_receipt.eid, pool_receipt.eid}, key=_eid_order))
    return None


# ------------------------------------------------------------------------------------------------ recovery
@dataclass
class Verification:
    remediation: str
    p95_ms: float
    slo_ms: float
    measured_at: str
    evidence: list[str]


def _readings_after(ledger: EvidenceLedger, rem: Remediation, service: str, environment: str):
    for r in ledger.receipts[rem.index + 1:]:
        reading = p95_reading(r.result)
        if reading is None or not _in_scope(r.result, service, environment):
            continue
        p95, slo, at = reading
        if rem.at is not None and (at is None or at <= rem.at):
            continue
        yield r, p95, slo, at


def verify_recovery(ledger: EvidenceLedger, service: str, environment: str) -> Verification | None:
    rems = remediations(ledger, service, environment)
    if not rems:
        return None
    last = rems[-1]
    readings = list(_readings_after(ledger, last, service, environment))
    if not readings:
        return None
    receipt, p95, slo, at = readings[-1]
    if p95 > slo:
        return None
    return Verification(last.description, p95, slo, at.strftime("%Y-%m-%d %H:%M UTC") if at else "unknown time",
                        [last.receipt.eid, receipt.eid])


# ------------------------------------------------------------------------------------------------ requirements
@dataclass
class Requirement:
    name: str
    query: str
    why: str


def next_requirement(intent: Intent, ledger: EvidenceLedger) -> Requirement | None:
    """The next piece of evidence the request still needs, with a discovery query for it."""
    svc, env = intent.service, intent.environment
    diagnosis = diagnose(ledger, svc, env)
    if intent.wants_cause and diagnosis is None:
        deps = sorted((d for r in ledger.receipts for d in deployments_in(r.result)
                       if d.get("service") == svc and d.get("environment") == env and d.get("status") == "succeeded" and d.get("commit")),
                      key=lambda d: d.get("started_at") or "", reverse=True)
        if not deps:
            return Requirement("deployment", f"recent release-pipeline deployments of {svc} in {env}", "which version was deployed and when")
        diffed = [str(r.result["sha"]) for r in ledger.receipts if is_diff(r.result)]
        newest = str(deps[0]["commit"])
        if not any(s.startswith(newest) or newest.startswith(s) for s in diffed):
            return Requirement("diff", f"code diff of commit {newest} deployed to {svc}", f"what commit {newest} changed")
        if not any(is_pool(r.result) and _in_scope(r.result, svc, env) for r in ledger.receipts):
            return Requirement("pool", f"database connection pool stats for {svc} in {env}", "whether the connection pool is saturated")
    if intent.wants_action:
        rems = remediations(ledger, svc, env)
        target = _rollback_target(ledger, svc, env, diagnosis)
        if not rems and target is None:
            return Requirement("deployment", f"recent release-pipeline deployments of {svc} in {env}",
                               "which release is live and which one to roll back to")
        fix = (f"roll back {svc} in {env} from {target[0]} to {target[1]} through the release pipeline" if target
               else f"roll back {svc} to the previous release in {env}")
        if not rems:
            return Requirement("remediation", fix, "the request asks for a fix to be applied")
        if verify_recovery(ledger, svc, env) is None:
            readings = list(_readings_after(ledger, rems[-1], svc, env))
            if readings:
                return Requirement("remediation", fix, "the last fix did not bring p95 back within the SLO")
            return Requirement("verification", f"current p95 latency and health of {svc} in {env}",
                               "whether the fix brought p95 back within the SLO")
    if intent.wants_incident_update and not incident_is_current(intent, ledger):
        why = ("the incident was last updated before the latest evidence" if incident_writes(ledger, intent.incident_id)
               else "the request asks for the incident to be updated")
        return Requirement("incident_update", f"update incident {intent.incident_id} status, root cause and notes", why)
    return None


def _rollback_target(ledger: EvidenceLedger, svc: str, env: str, diagnosis: Diagnosis | None) -> tuple[str, str, str] | None:
    if diagnosis and diagnosis.previous_version:
        receipt = next(r.eid for r in ledger.receipts for d in deployments_in(r.result) if d.get("id") == diagnosis.deployment_id)
        return diagnosis.version, diagnosis.previous_version, receipt
    return release_target(ledger, svc, env)


def missing_requirements(intent: Intent, ledger: EvidenceLedger) -> list[str]:
    svc, env = intent.service, intent.environment
    missing = []
    if intent.wants_cause and diagnose(ledger, svc, env) is None:
        missing.append("diagnosis")
    if intent.wants_action and not remediations(ledger, svc, env):
        missing.append("remediation")
    if intent.wants_verification and verify_recovery(ledger, svc, env) is None:
        missing.append("verification")
    if intent.wants_incident_update and not incident_is_current(intent, ledger):
        missing.append("incident_update")
    return missing


# ------------------------------------------------------------------------------------------------ call gates
@dataclass
class Gate:
    allowed: bool
    arguments: dict[str, Any]
    message: str | None = None


def _status_summary(intent: Intent, diagnosis: Diagnosis | None, verification: Verification | None, remediated: bool) -> str:
    cause = f"cause: {intent.service} {diagnosis.version} reduced the connection pool to {diagnosis.new_max}" if diagnosis else "cause under investigation"
    state = "recovery verified" if verification else ("remediation applied, recovery not yet verified" if remediated else "no remediation applied")
    return f"{intent.service} latency incident in {intent.environment}; {cause}; {state}."


def incident_note(intent: Intent, ledger: EvidenceLedger) -> str:
    d = diagnose(ledger, intent.service, intent.environment)
    v = verify_recovery(ledger, intent.service, intent.environment)
    rems = remediations(ledger, intent.service, intent.environment)
    parts = [_status_summary(intent, d, v, bool(rems))]
    if d:
        parts.append(f"Evidence for the cause: {', '.join(d.evidence)}.")
    if v:
        parts.append(f"Verified: p95 {v.p95_ms} ms within the {v.slo_ms} ms SLO at {v.measured_at} ({', '.join(v.evidence)}).")
    elif rems:
        parts.append(f"Remediation: {rems[-1].description} ({rems[-1].receipt.eid}); recovery not yet verified.")
    return " ".join(parts)


def _render_update(intent: Intent, args: dict[str, Any], ledger: EvidenceLedger) -> dict[str, Any]:
    svc, env = intent.service, intent.environment
    d, v = diagnose(ledger, svc, env), verify_recovery(ledger, svc, env)
    rems = remediations(ledger, svc, env)
    out = {k: val for k, val in args.items() if k not in MODEL_PROSE_FIELDS}
    out.setdefault("incident_id", intent.incident_id)
    requested = str(args.get("status") or "").lower()
    if requested:
        if requested in ("resolved", "closed"):
            status = "resolved" if v else ("identified" if d else "investigating")
        elif requested == "monitoring":
            status = "monitoring" if rems else ("identified" if d else "investigating")
        elif requested == "identified":
            status = "identified" if d else "investigating"
        else:
            status = "investigating"
        out["status"] = status
    if str(args.get("severity")) in SEVERITIES:
        out["severity"] = args["severity"]
    if "summary" in args:
        out["summary"] = _status_summary(intent, d, v, bool(rems))
    if d:
        out["root_cause"] = f"{d.sentence()} (evidence {', '.join(d.evidence)})"
    if v:
        out["resolution_notes"] = (f"{v.remediation}; verified p95 {v.p95_ms} ms within the {v.slo_ms} ms SLO at {v.measured_at} "
                                   f"(evidence {', '.join(v.evidence)}).")
    elif rems:
        out["resolution_notes"] = f"{rems[-1].description} ({rems[-1].receipt.eid}); recovery not yet verified."
    return out


def gate_call(intent: Intent, tool_id: str, arguments: dict[str, Any], record: Any, ledger: EvidenceLedger) -> Gate:
    """Decide whether a proposed call may run, and render incident fields from receipts. Policy still runs afterwards."""
    args = dict(arguments)
    side_effect = record is None or bool(record.side_effect)
    if intent.read_only and side_effect:
        return Gate(False, args, "Blocked by the evidence guard: the request is read-only, so no write may run.")
    if side_effect and not intent.wants_action and REMEDIATION_TOOL.search(tool_id.split(".", 1)[-1]):
        return Gate(False, args, "Blocked by the evidence guard: the request does not ask for a fix, so recommend the "
                                 "remediation in the report instead of running it.")
    capability = record.capability if record is not None else None
    if capability == "incident-close" or (record is None and tool_id.endswith("close_incident")):
        if verify_recovery(ledger, intent.service, intent.environment) is None:
            return Gate(False, args, "Blocked by the evidence guard: an incident can only be closed after a successful remediation "
                                     "and a verified in-SLO p95 reading taken after it.")
        return Gate(True, args)
    if side_effect and "to_version" in args and not remediations(ledger, intent.service, intent.environment):
        svc, env = intent.service, intent.environment
        target = _rollback_target(ledger, svc, env, diagnose(ledger, svc, env))
        if target is None:
            return Gate(False, args, f"Blocked by the evidence guard: look up the release history of {svc} in {env} first; "
                                     "a rollback target must come from a tool result, not a guess.")
        if str(args["to_version"]) != target[1]:
            return Gate(False, args, f"Blocked by the evidence guard: {args['to_version']} is not supported by the evidence. "
                                     f"{svc} {target[0]} replaced {target[1]} in {env} [{target[2]}], so the rollback target "
                                     f"is {target[1]}.")
    if capability == "incident-update":
        return Gate(True, _render_update(intent, args, ledger))
    if capability == "incident-comment":
        return Gate(True, {**args, "comment": incident_note(intent, ledger)})
    return Gate(True, args)


# ------------------------------------------------------------------------------------------------ report
def describe(receipt: Receipt, service: str, environment: str) -> str:
    res = receipt.result
    deps = [d for d in deployments_in(res) if d.get("service") == service and d.get("environment") == environment]
    if deps:
        return "; ".join(f"{d.get('version')} started {d.get('started_at')} ({d.get('id')}, commit {d.get('commit')}, {d.get('status')})" for d in deps[:3])
    if is_diff(res):
        change = pool_change(res["diff"])
        extra = f", max_connections {change[0]} -> {change[1]}" if change else ""
        return f"commit {res['sha']}: {res.get('message', '')}{extra}"
    fixes = remediations(EvidenceLedger(receipts=[receipt]), service, environment)
    if fixes:
        return fixes[0].description
    if {"sha", "message"} <= res.keys():
        return f"commit {res['sha']}: {res['message']}"
    if is_pool(res):
        return f"{res.get('environment')} pool: max {res['max_connections']}, in use {res['in_use']}, waiting {res['waiting']}"
    reading = p95_reading(res)
    if reading:
        return f"{res.get('environment')} p95 {reading[0]} ms (SLO {reading[1]} ms) at {res.get('end') or res.get('as_of')}"
    if res.get("incident_id") and "updated" in res:
        return f"incident {res['incident_id']} fields updated: {', '.join(sorted(res['updated']))}"
    summary = res.get("summary")
    if res.get("metric") and isinstance(summary, dict) and "last" in summary:
        return f"{res.get('environment')} {res['metric']} {summary['last']} at {res.get('end')}"
    return "result recorded"


def render_report(intent: Intent, ledger: EvidenceLedger, *, missing: list[str] | None = None) -> str:
    svc, env = intent.service, intent.environment
    missing = missing_requirements(intent, ledger) if missing is None else missing
    d, v = diagnose(ledger, svc, env), verify_recovery(ledger, svc, env)
    rems = remediations(ledger, svc, env)
    state = f"Incomplete, missing evidence: {', '.join(missing)}" if missing else "Complete"
    lines = [f"FINAL: {state}. Scope: {svc} in {env}, {intent.incident_id}. Built from tool results only."]
    lines.append("Likely cause: " + (f"{d.sentence()} [{', '.join(d.evidence)}]." if d else "not established from the evidence gathered."))
    if rems:
        lines.append(f"Remediation performed: {rems[-1].description} [{rems[-1].receipt.eid}].")
    elif d:
        lines.append(f"Recommended remediation: roll {svc} in {env} back from {d.version} to {d.previous_version} through the release "
                     f"pipeline, the authoritative deployment path; a production rollback needs human approval.")
    else:
        lines.append("Recommended remediation: none supported by the evidence yet.")
    if v:
        lines.append(f"Recovery check: p95 {v.p95_ms} ms within the {v.slo_ms} ms SLO at {v.measured_at} [{', '.join(v.evidence)}].")
    elif rems or intent.wants_verification:
        lines.append("Recovery check: not verified.")
    writes = incident_writes(ledger, intent.incident_id)
    lines.append(f"Incident update: {describe(writes[-1], svc, env)} [{writes[-1].eid}]." if writes else "Incident update: none made.")
    lines.append("Evidence:")
    lines.extend(f"- {r.eid} {r.tool_id}: {describe(r, svc, env)}" for r in ledger.receipts)
    if ledger.failed:
        lines.append(f"Failed calls, not used as evidence: {len(ledger.failed)}.")
    if ledger.not_executed:
        counts: dict[tuple[str, str], int] = {}
        for item in ledger.not_executed:
            counts[(item.tool_id, item.reason)] = counts.get((item.tool_id, item.reason), 0) + 1
        items = [f"{tool} ({reason}{f', {n} times' if n > 1 else ''})" for (tool, reason), n in counts.items()]
        lines.append(f"Not executed: {'; '.join(items)}.")
    return "\n".join(lines)

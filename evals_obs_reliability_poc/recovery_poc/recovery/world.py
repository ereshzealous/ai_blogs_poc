"""The simulated enterprise: every provider the agent talks to, behind real HTTP, with its own ledger.

SIMULATED systems, REAL protocol: the runtime talks HTTP over TCP to this server, a lost response is a real socket
timeout, a refused connection is a real ECONNREFUSED (injected at the client, see toolclient.py), a SIGKILL is a real
signal.  The ledgers here are the systems of record: every effect count in the evidence is read from them, never from
the agent's own records.

  POST /kb/search                       retrieval (BM25-style over config/world.toml [[kb]], superseded documents filtered)
  GET  /crm/charges?customer=           read-only lookup (the CRM does not know about disputes)
  POST /model/decide                    the model gateway (scripted models, scripted.py)
  POST /credits                         account credit (payment-like; Idempotency-Key honoured for ttl_s of provider time)
  GET  /credits/by-operation/<op_id>    the credit provider's status query
  POST /tickets                         create a ticket (Idempotency-Key ignored)
  GET  /tickets?reference=<ref>         ticket search by our business reference
  POST /tickets/<id>/void               compensation: void one ticket
  POST /notifications                   send a message (fire-and-forget: no status query)
  POST /admin/clock                     advance provider time (idempotency windows)

Faults (experiments/scenarios.toml grammar) fire on the n-th request to a target, or on every request (@all).
"""

from __future__ import annotations

import json
import math
import re
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import scripted
from .common import world_config

PRIMARY = "scripted-v1"


def parse_faults(faults: list[str]) -> list[dict]:
    """'tool:issue_credit:lost_response@1' -> {target: 'tool:issue_credit', kind: 'lost_response', at: 1}."""
    out = []
    for f in faults:
        if f.startswith(("process:", "journal:", "clock:")):
            continue                                  # injected by the harness / the runtime, not by a provider
        body, _, at = f.partition("@")
        target, _, kind = body.rpartition(":")
        out.append({"target": target, "kind": kind, "at": "all" if at == "all" else int(at or 1)})
    return out


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class World:
    def __init__(self, faults: list[str], model_change: str | None = None, live: dict | None = None):
        self.cfg = world_config()
        self.faults = parse_faults(faults)
        self.model_change = model_change
        # live: {"primary", "fallback", "mode": "record" | "replay", "tape": Path, "run_key": "S09/A2"} -> the gateway asks a
        # real model (record) or returns the recorded answer for the same call (replay); faults still apply on top
        self.live = live
        self.model_calls = 0
        self.tape_rows: list[dict] = []
        self.volatile_ms: list[float] = []
        if live and live["mode"] == "replay":
            tp = Path(live["tape"])
            self.tape_rows = [json.loads(l) for l in tp.read_text().splitlines() if l.strip()] if tp.exists() else []
        self.lock = threading.Lock()
        self.clock_s = 0                       # provider time, advanced only by /admin/clock
        self.counts: dict[str, int] = {}
        self.credits: list[dict] = []
        self.idem: dict[str, dict] = {}
        self.tickets: list[dict] = []
        self.notifications: list[dict] = []
        self.access: list[dict] = []           # every request that reached a provider, in arrival order
        self.charges = {c["id"]: c for c in self.cfg["charges"]}
        self.customers = {c["id"]: c for c in self.cfg["customers"]}
        self.cases = {c["id"]: c for c in self.cfg["cases"]}
        self.server: ThreadingHTTPServer | None = None

    # ---- lifecycle --------------------------------------------------------------------------------------------------
    def start(self) -> int:
        world = self

        class H(Handler):
            pass
        H.world = world
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self.server.server_address[1]

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    # ---- faults -----------------------------------------------------------------------------------------------------
    def fault(self, target: str) -> tuple[str | None, int]:
        """Count this request against its target; return the fault kind that fires on it (if any) and its ordinal."""
        with self.lock:
            n = self.counts[target] = self.counts.get(target, 0) + 1
        for f in self.faults:
            if f["target"] == target and (f["at"] == "all" or f["at"] == n):
                return f["kind"], n
        return None, n

    def log(self, **row) -> None:
        with self.lock:
            row["seq"] = len(self.access) + 1
            self.access.append(row)

    def ledger(self) -> dict:
        with self.lock:
            return {"clock_s": self.clock_s, "credits": list(self.credits), "tickets": list(self.tickets),
                    "notifications": list(self.notifications), "access": list(self.access)}

    # ---- the live model gateway --------------------------------------------------------------------------------------------
    def live_decide(self, model: str, case: dict, b: dict, fault: str | None) -> tuple[str, dict]:
        """A real model's decision (REAL, recorded to the run's tape) or its recorded answer (replay).  Faults apply on top."""
        from . import modelslice
        from .common import sha256
        system = (modelslice.SLICE / "prompt.md").read_text()
        view = {"case_id": case["id"], "customer": case["customer"], "message": case["message"], "charges": b["charges"]}
        user = modelslice.user_prompt(view, b["documents"])
        if b.get("repair_hint"):
            user += f"\n\nYOUR PREVIOUS PROPOSAL WAS REJECTED BY THE RUNTIME: {b['repair_hint']}\nReturn a corrected JSON object."
        with self.lock:
            k = self.model_calls
            self.model_calls += 1
        psha = sha256(system + user)[:16]
        if self.live["mode"] == "replay":
            row = self.tape_rows[k]
            if row["prompt_sha"] != psha or row["model"] != model:
                raise RuntimeError(f"replay diverged at model call {k}: {row['prompt_sha']}/{row['model']} != {psha}/{model}")
            content, usage = row["content"], row["usage"]
        else:
            t = time.monotonic()
            r = modelslice.ollama_chat(model, system, user, seed=1, temperature=0.0)
            self.volatile_ms.append(round((time.monotonic() - t) * 1000))
            content = r["message"]["content"]
            usage = {"input_tokens": r.get("prompt_eval_count"), "output_tokens": r.get("eval_count")}
            row = {"run": self.live["run_key"], "n": k, "model": model, "prompt_sha": psha, "repair": bool(b.get("repair_hint")),
                   "content": content, "usage": usage}
            with self.lock, open(self.live["tape"], "a") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
        return render_live(content, fault), usage

    # ---- retrieval -----------------------------------------------------------------------------------------------------
    def search(self, query: str, k: int = 3) -> list[dict]:
        docs = [d for d in self.cfg["kb"] if not d.get("superseded")]
        n = len(docs)
        df: dict[str, int] = {}
        toks = {d["id"]: tokens(d["title"] + " " + d["text"]) for d in docs}
        for t in toks.values():
            for w in set(t):
                df[w] = df.get(w, 0) + 1
        avg = sum(len(t) for t in toks.values()) / n
        scored = []
        for d in docs:
            t = toks[d["id"]]
            s = 0.0
            for w in set(tokens(query)):
                f = t.count(w)
                if f:
                    idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                    s += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(t) / avg))
            scored.append((round(s, 4), d["id"]))
        scored.sort(key=lambda x: (-x[0], x[1]))
        by = {d["id"]: d for d in docs}
        return [{"id": i, "title": by[i]["title"], "text": by[i]["text"], "version": by[i]["version"], "score": s}
                for s, i in scored[:k] if s > 0]


class Handler(BaseHTTPRequestHandler):
    world: World
    protocol_version = "HTTP/1.0"

    def log_message(self, *a):          # quiet
        pass

    # ---- plumbing -----------------------------------------------------------------------------------------------------
    def body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def send(self, status: int, obj: dict, headers: dict | None = None) -> None:
        data = json.dumps(obj, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def lose(self) -> None:
        """Hold the connection past the client's timeout, then close it without a response."""
        time.sleep(self.world.cfg["lost_response_hold_ms"] / 1000)
        self.close_connection = True

    def expired(self) -> bool:
        d = self.headers.get("X-Deadline-Epoch-Ms")
        return bool(d) and time.time() * 1000 > float(d)

    def meta(self) -> dict:
        return {"op": self.headers.get("X-Operation-Id"), "key": self.headers.get("Idempotency-Key"),
                "attempt": self.headers.get("X-Attempt-Id")}

    # ---- routes ---------------------------------------------------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        w = self.world
        if u.path == "/crm/charges":
            kind, n = w.fault("tool:lookup_charges")
            cust = parse_qs(u.query).get("customer", [""])[0]
            out = [{k: v for k, v in c.items() if k not in ("disputed",)} for c in w.cfg["charges"] if c["customer"] == cust]
            w.log(target="tool:lookup_charges", n=n, outcome="LOST" if kind == "lost_response" else "EXECUTED", **self.meta())
            if kind == "lost_response":
                return self.lose()
            return self.send(200, {"charges": out})
        m = re.fullmatch(r"/credits/by-operation/([\w\-.]+)", u.path)
        if m:
            kind, n = w.fault("status:issue_credit")
            if kind == "unavailable":
                w.log(target="status:issue_credit", n=n, outcome="UNAVAILABLE", op=m.group(1))
                return self.send(503, {"error": "status service unavailable"})
            with w.lock:
                found = [c for c in w.credits if c["operation_id"] == m.group(1)]
            w.log(target="status:issue_credit", n=n, outcome="EXECUTED", op=m.group(1), found=len(found))
            return self.send(200, {"operation_id": m.group(1), "credits": found})
        if u.path == "/tickets":
            kind, n = w.fault("status:create_ticket")
            ref = parse_qs(u.query).get("reference", [""])[0]
            if kind == "unavailable":
                w.log(target="status:create_ticket", n=n, outcome="UNAVAILABLE", op=ref)
                return self.send(503, {"error": "ticket search unavailable"})
            with w.lock:
                found = [t for t in w.tickets if t["reference"] == ref and t["status"] == "OPEN"]
            w.log(target="status:create_ticket", n=n, outcome="EXECUTED", op=ref, found=len(found))
            return self.send(200, {"reference": ref, "tickets": found})
        return self.send(404, {"error": "no such route"})

    def do_POST(self):
        u = urlparse(self.path)
        w = self.world
        b = self.body()
        if u.path == "/admin/clock":
            with w.lock:
                w.clock_s += int(b.get("advance_s", 0))
            return self.send(200, {"clock_s": w.clock_s})

        if u.path == "/kb/search":
            kind, n = w.fault("kb:search")
            if kind == "unavailable":
                w.log(target="kb:search", n=n, outcome="UNAVAILABLE")
                return self.send(503, {"error": "index unavailable"}, {"Not-Executed": "true"})
            w.log(target="kb:search", n=n, outcome="EXECUTED")
            return self.send(200, {"documents": w.search(b["query"], b.get("k", 3))})

        if u.path == "/model/decide":
            model = b["model"]
            primary = (w.live or {}).get("primary", PRIMARY)
            kind, n = w.fault("model:decide") if model == primary else (None, 0)
            if kind == "unavailable":
                w.log(target="model:decide", n=n, outcome="UNAVAILABLE", model=model)
                return self.send(503, {"error": "model overloaded"}, {"Not-Executed": "true"})
            if kind == "rate_limited":
                w.log(target="model:decide", n=n, outcome="RATE_LIMITED", model=model)
                return self.send(429, {"error": "rate limited"}, {"Retry-After": "1", "Not-Executed": "true"})
            case = w.cases[b["case_id"]]
            if w.live:
                text, usage = w.live_decide(model, case, b, kind)
            else:
                effective = w.model_change or model
                d = scripted.decide(effective, case["message"], b["charges"], b["documents"], policy_aware=False)
                text = scripted.render(d, kind)
                usage = scripted.usage(json.dumps(b), text)
            w.log(target="model:decide", n=n, outcome="EXECUTED", model=model, fault=kind)
            return self.send(200, {"model": model, "content": text, "usage": usage})

        if u.path == "/credits":
            kind, n = w.fault("tool:issue_credit")
            meta = self.meta()
            if kind == "stall_then_refuse":
                time.sleep(w.cfg["lost_response_hold_ms"] / 1000)
                if self.expired():          # the provider refuses work whose deadline has passed: no effect
                    w.log(target="tool:issue_credit", n=n, outcome="REFUSED_LATE", **meta)
                    self.close_connection = True
                    return None
            key = meta["key"]
            with w.lock:
                rec = w.idem.get(key) if key else None
                fresh = rec is not None and w.clock_s - rec["created_s"] < 86400
            if fresh:
                w.log(target="tool:issue_credit", n=n, outcome="REPLAYED", **meta)
                if kind == "lost_response":
                    return self.lose()
                return self.send(rec["status"], rec["body"], {"Idempotent-Replayed": "true"})
            if self.expired():
                w.log(target="tool:issue_credit", n=n, outcome="REFUSED_LATE", **meta)
                return self.send(408, {"error": "DEADLINE_EXCEEDED", "executed": False})
            ch = w.charges.get(b.get("charge_id"))
            if ch is None:
                status, body = 404, {"error": "NO_SUCH_CHARGE"}
            elif abs(float(b.get("amount", -1)) - ch["amount"]) > 0.001:
                status, body = 422, {"error": "AMOUNT_MISMATCH"}
            elif ch.get("disputed"):
                status, body = 422, {"error": "CHARGE_DISPUTED"}
            else:
                with w.lock:
                    cid = f"cr_{len(w.credits) + 1:04d}"
                    w.credits.append({"credit_id": cid, "charge_id": ch["id"], "amount": ch["amount"], "operation_id": meta["op"],
                                      "idempotency_key": key, "attempt_id": meta["attempt"], "provider_s": w.clock_s, "status": "COMMITTED"})
                status, body = 201, {"credit_id": cid, "charge_id": ch["id"], "amount": ch["amount"], "status": "COMMITTED"}
            if key:
                with w.lock:
                    w.idem[key] = {"status": status, "body": body, "created_s": w.clock_s}
            w.log(target="tool:issue_credit", n=n, outcome="EXECUTED" if status == 201 else f"REJECTED_{status}", **meta)
            if kind == "lost_response" and status == 201:
                return self.lose()
            return self.send(status, body)

        m = re.fullmatch(r"/tickets/([\w\-]+)/void", u.path)
        if m:
            with w.lock:
                t = next((t for t in w.tickets if t["ticket_id"] == m.group(1)), None)
                if t:
                    t["status"] = "VOID"
            w.log(target="comp:void_ticket", n=0, outcome="EXECUTED" if t else "REJECTED_404", op=m.group(1))
            return self.send(200 if t else 404, {"ticket_id": m.group(1), "status": "VOID" if t else "NOT_FOUND"})

        if u.path == "/tickets":
            kind, n = w.fault("tool:create_ticket")
            meta = self.meta()
            if self.expired():
                w.log(target="tool:create_ticket", n=n, outcome="REFUSED_LATE", **meta)
                return self.send(408, {"error": "DEADLINE_EXCEEDED", "executed": False})
            copies = 2 if kind == "lost_response_dup" else 1     # an upstream bug: the provider's own retry commits twice
            with w.lock:
                made = []
                for _ in range(copies):
                    tid = f"TCK-{len(w.tickets) + 1:04d}"
                    w.tickets.append({"ticket_id": tid, "case_id": b["case_id"], "reference": b["reference"], "summary": b["summary"],
                                      "status": "OPEN", "attempt_id": meta["attempt"]})
                    made.append(tid)
            w.log(target="tool:create_ticket", n=n, outcome="EXECUTED", copies=copies, **meta)
            if kind in ("lost_response", "lost_response_dup"):
                return self.lose()
            return self.send(201, {"ticket_id": made[0], "status": "OPEN"})

        if u.path == "/notifications":
            kind, n = w.fault("tool:send_notification")
            meta = self.meta()
            if self.expired():
                w.log(target="tool:send_notification", n=n, outcome="REFUSED_LATE", **meta)
                return self.send(408, {"error": "DEADLINE_EXCEEDED", "executed": False})
            case = w.cases[b["case_id"]]
            to = w.customers[case["customer"]]["email"]      # the provider resolves the address; the agent never handles it
            with w.lock:
                mid = f"msg_{len(w.notifications) + 1:04d}"
                w.notifications.append({"message_id": mid, "case_id": b["case_id"], "template": b["template"], "to_sha": _h(to),
                                        "attempt_id": meta["attempt"]})
            w.log(target="tool:send_notification", n=n, outcome="EXECUTED", **meta)
            if kind == "lost_response":
                return self.lose()
            return self.send(202, {"message_id": mid, "status": "ACCEPTED"})

        return self.send(404, {"error": "no such route"})


def render_live(content: str, fault: str | None) -> str:
    """A real model's text with an injected output fault on top (the same three faults scripted.render injects)."""
    if fault == "invalid_json":
        return '{"tool": "issue_credit", "arguments": {"charge_id": '
    if fault in ("wrong_tool", "bad_args"):
        try:
            d = json.loads(content)
        except json.JSONDecodeError:
            return content
        if fault == "wrong_tool":
            d["tool"] = "delete_customer_account"
        elif d.get("tool") == "issue_credit" and isinstance((d.get("arguments") or {}).get("amount"), (int, float)):
            d["arguments"]["amount"] = round(d["arguments"]["amount"] * 10, 2)
        return json.dumps(d)
    return content


def _h(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:12]

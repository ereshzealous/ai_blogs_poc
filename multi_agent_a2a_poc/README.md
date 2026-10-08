# C1 POC · Do you actually need multiple agents?

*Production AI Engineering · Coordination track · C1.* The proof of concept behind the article *Do You Actually Need
Multiple Agents?* (Medium and technical editions).

One headless capability, F3's `investigate_incident`, implemented three ways and run on the same eight blind incidents
with the same local model (`gpt-oss:20b`), the same thirteen MCP tools, one policy, one approval rule and one token
budget:

- **A · one agent** with every tool, deciding everything;
- **B · a deterministic workflow** that collects evidence by a fixed recipe and calls tool-less agents only for
  diagnosis, remediation planning and (conditionally) review;
- **C · a coordinator agent** that delegates over A2A v1.0 (official `a2a-sdk` 1.2.2) to four agent processes
  (evidence, diagnosis, remediation, review), each with its own context and narrowed authority.

## Results (recorded run `2026-10-08-blind`)

Eight blind incidents × three architectures × three repeats = 72 workflows, strictly serial, every model call
tape-recorded. Every number on this page is substituted from
[`coordination_poc/runs/2026-10-08-blind/facts.json`](coordination_poc/runs/2026-10-08-blind/facts.json).

| | A · One agent | B · Workflow + agents | C · Multi-agent over A2A |
|---|---|---|---|
| task success (of 24 runs) | **9** (21–57%) | **16** (47–82%) | **12** (31–69%) |
| complex incidents (of 9) | 0 | 6 | 4 |
| median latency | 30.2 s | 11.3 s | 141.2 s |
| median tokens | 25536.5 | 5253.0 | 63108.0 |

How to read it:

- **The intervals are over runs, not incidents.** The three repeats of an incident share its fixture and differ only in
  the seed, so they are not independent samples. Incident by incident, B had more successes than C on 3 of
  8 incidents, fewer on 1 and the same on 4: the success gap rests on a few
  incidents. The cost gap does not: C used more tokens than B on 8 of 8 incidents
  and more time on 8, never less than 7.1× B's tokens.
- **The A2A boundary was cheap here.** 19.0 ms per delegation on average,
  0.07% of C's time; the same agent code in-process vs over A2A, with the reasoning held
  constant: 3.81 ms vs 9.17 ms (E7). These are loopback numbers, every process on one
  machine without TLS: a floor, not a production figure. C's extra cost was coordination.
- **The A2A task lost on a crash is the POC's choice.** The agents keep tasks in the SDK's in-memory `TaskStore`, so a
  killed agent forgets its task (E6). The workflow store, not the protocol, owns workflow truth.

Preregistered hypotheses: H1 SUPPORTED · H2 NOT SUPPORTED · H3 SUPPORTED · H4 SUPPORTED · H5 SUPPORTED · H6 SUPPORTED · H7 SUPPORTED · H8 SUPPORTED
· H9 NOT SUPPORTED ([`preregistration.toml`](coordination_poc/experiments/preregistration.toml)).

## One change after the run

The blind run found a fail-open fallback: when C's coordinator authorized an execution without handing over a
remediation proposal, the runtime granted every eligible write scope (1 of
16 execute delegations). The post-run correction changed it to fail closed, with two regression
tests ([DEVIATIONS D3](coordination_poc/experiments/DEVIATIONS.md)). Every number above comes from the code as it ran:
the two files as they ran are in [`experiments/as-run/`](coordination_poc/experiments/as-run) and still match
[`FROZEN.sha256`](coordination_poc/experiments/FROZEN.sha256), and the published run replays identically under the
fixed code with the as-run behaviour switched back on. The affected run was one of C's successes; under the fix its
outcome was not measured.

## Verify it yourself

Requirements: [`uv`](https://docs.astral.sh/uv/) (it installs Python 3.12 and the pinned dependencies) and `make`. No
model and no network beyond loopback.

```bash
git clone https://github.com/ereshzealous/ai_blogs_poc.git
cd ai_blogs_poc/multi_agent_a2a_poc
make setup     # Python 3.12 + the locked dependencies
make verify    # frozen inputs, the replay check of all 72 blind workflows, the tests
make replay    # optional: re-execute every blind workflow from the model tape (no model), then compare
```

`make verify` prints `FROZEN CHECK OK` (with the two post-run changes and their deviation), `REPLAY IDENTICAL` and the
test count. Live runs need [Ollama](https://ollama.com) with `gpt-oss:20b`; the commands are in
[`coordination_poc/README.md`](coordination_poc/README.md).

## What is here

```text
coordination_poc/   the system, its config, the 12 incidents, ground truth, the preregistration, the tests and every
                    recorded run (README inside)
verification/       what `make verify` printed at publication, and the D3 positive control
results/            the run report (every workflow, per incident, every execute delegation) and what is real vs simulated
research/           the A2A v1.0.1 notes every protocol claim was checked against, and the sources
diagrams/           the article's figures (PNG); every measured value in them comes from facts.json
```

Real: model inference (local Ollama), MCP stdio servers, A2A between OS processes, SIGKILL and restart, retries,
OpenTelemetry traces across processes, token counts, wall-clock latency on one machine. Simulated: the enterprise
systems and every remediation, the token service, the human approver.

Licence: MIT ([LICENSE](LICENSE)).

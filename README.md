# Production AI Engineering: the proofs of concept

One folder per chapter of [Production AI Engineering](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db), a series on what it takes to
run AI agents in production. Each folder is the chapter's proof of concept with the evidence its article cites: the
code and its tests, the recorded run behind every number and a results page.

| Chapter | Folder | Article | The question it answers | How the published run was made |
|---|---|---|---|---|
| F1 | [`mcp_sprawl_poc/`](mcp_sprawl_poc) | Your AI agent has 500 MCP tools. Now what? | Which capability should the agent see, and may this exact call execute? | live local model, recorded |
| F2 | [`layered_architecture_poc/`](layered_architecture_poc) | Your agent works in a demo. Why does it break in production? | Which production responsibility belongs where, and what survives failure? | recorded: live local models, real MCP servers, real SIGKILLs |
| F3 | [`headless_ai_poc/`](headless_ai_poc) | Headless AI: Your AI Shouldn't Live Inside the UI | How should many consumers use the same AI intelligence safely? | deterministic reasoner over simulated systems |
| S1 | [`memory_context_state_poc/`](memory_context_state_poc) | Your Agent Remembers Everything. That's a Problem. | What should an agent remember, what should expire, and what is authoritative? | recorded with a live local model |
| S2 | [`context_eng_rag_poc/`](context_eng_rag_poc) | Your Agent Found the Right Document. Why Did It Give the Wrong Answer? | How does an agent retrieve valid enterprise evidence without dumping the company into the prompt? | live local model on the held-out split |
| T1 | [`agent_identity_poc/`](agent_identity_poc) | Agent Identity: Who Is Acting, and on Whose Authority? | When an agent acts, whose authority is actually being used? | deterministic run |
| T2 | [`auth_and_policy_poc/`](auth_and_policy_poc) | Your AI Agent Has an Identity. What Is It Allowed to Do? | For every tool call: may this agent do this, on this resource, in this context, on whose authority? | deterministic, simulated systems of record |
| T3 | [`human_in_the_loop_poc/`](human_in_the_loop_poc) | APPROVED, but approved what? | What exactly did the human approve, and is that approval still valid now? | deterministic: no model, no network |
| T4 | [`ai_control_plane_poc/`](ai_control_plane_poc) | AI Control Plane: Your Agents Shouldn't Govern Themselves | How do you change what many agents may do without editing or redeploying any of them? | deterministic: agents follow fixed plans, no model |
| T5 | [`governance_for_ai_agents_poc/`](governance_for_ai_agents_poc) | Your AI Agent Did Something in Production. Can You Explain Exactly What Happened? | Can you prove what an agent did, and on whose authority? | recorded with a live local model |
| T6 | [`agent_mcp_security_poc/`](agent_mcp_security_poc) | Securing Agents, Tools & MCP | If the model is fooled, can the unsafe action still happen? | deterministic, scripted worst-case model, no network |
| R1+R2 | [`evals_obs_reliability_poc/`](evals_obs_reliability_poc) | “The Agent Failed” Is Not an Operational Signal | When something breaks mid-run, what should the runtime do next, and how do you know it chose right? | deterministic scenarios plus a recorded real-model slice |
| C1 | [`multi_agent_a2a_poc/`](multi_agent_a2a_poc) | Do You Actually Need Multiple Agents? | When does one agent become several, and when does an agent deserve A2A? | live local model, recorded tape |
| O1+O2 | [`operating_ai_agents_poc/`](operating_ai_agents_poc) | Operating AI Agents at Scale — Cost, Latency, Scale & Lifecycle | What changes at production volume, and how do changes ship safely? | deterministic discrete-event simulation, no model |
| P1 | [`production_agentic_ai_platform/`](production_agentic_ai_platform) | The Agent Is Not the Architecture | How do all these boundaries fit into one production platform, and does the assembly hold? | proof run: real processes, simulated systems, recorded model calls |

`layered_agent_platform/` is the library F2's first implementation became; S1's POC builds against it. It is not a chapter.

## Every folder has the same shape

Each folder holds the proof of concept, its results and its evidence, and nothing that builds the articles:

```
<folder>/
  README.md          what the chapter showed, how to run it, where everything is
  Makefile           the same commands in every chapter (make help lists them)
  <poc>/             the proof of concept: code, tests, configuration, recorded runs
  results/           the results page (<code>-results.md) and the chapter's reports
  evidence/ proof/ verification/ experiment/   the published run's evidence, where the chapter keeps it
  .publish-frozen    the published run's evidence, which no publish may change
  public-redactions.json      what this public copy redacted (local paths, host names), with the original's hash
                              (F1 keeps its own in evidence/)
  LICENSE            MIT
```

## Run any chapter

```bash
cd <folder>
make setup     # the environment, from the lock file (uv)
make test      # the POC's tests; no model needed
make verify    # check the published run from the evidence shipped here; no model needed, nothing is rewritten
```

`make replay` and `make demo` re-run the recorded run without a model where the chapter has them. Recording a new run
needs a local model through [Ollama](https://ollama.com) in some chapters; each README says which. Commands that would
rewrite a published run refuse to run.

**Publishing.** [PUBLISHING.md](PUBLISHING.md) has the rules and the script that enforces them.

Licence: MIT, per folder.

# Your Agent Remembers Everything. That's a Problem.

*Memory, Context & State: What Should Persist, What Should Expire, and What Is Authoritative?*

**Production AI Engineering · S1 · State & Knowledge**

*Chapter 4 of 15. New here? Start with [Start Here: What It Takes to Run AI Agents in Production](https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db).*

![Cover of S1, Memory, Context & State, in Production AI Engineering: the title, three headline numbers from run 2026-09-18-recorded, and the comparison the run made.](../diagrams/premium/png/f00-cover.png)

*Real data from the POC. Everything retrieved was relevant; 3 of 5 were invalid.*

**Memory is not truth. It is evidence with provenance, scope, lifetime and authority.**

Last month an agent learned that checkout incidents get fixed by restarting pods. Then the runbook changed. The memory didn't.

The next incident arrives, and the most similar thing the agent can find is its own outdated experience.

*S1 in the Production AI Engineering series. It builds on F2, the layered agent platform.*

![The recorded naive retrieval for a new checkout-api incident: the top five by cosine similarity include a staging-only memory, an expired workaround and a contradicted episode, while the authoritative runbook ranks 10th. On the right, the observed failure: a memory claiming approval was done made the naive agent roll back without approval in 5 of 5 runs.](../assets/01-memory-hero.png)

## The Memory Was Relevant. It Was Still Wrong.

![The real top-12 candidates for the incident, ordered by cosine similarity, with ground truth and what three admission rules did with each: naive budget fill, naive top-5 and governed.](../assets/04-similarity-vs-validity.png)

*The same ranked list, three admission rules. Red rows are relevant but invalid.*

Retrieval didn't fail. Look at the similarity bars: the most similar *invalid* memory scores higher than the release record and the runbook that actually owns the procedure.

Similarity can't tell you that a record belongs to staging, expired last week, or was overruled in July. It only tells you the wording is close.

> **Relevance is a property of retrieval. Validity is a property of governance.**

So I built both versions and broke them on purpose. Here is what one recorded run measured, before any of the architecture:

> **Measured in the POC.** Invalid evidence that reached the model: **13** with naive memory, **0** with governed memory. Useful memory recalled in the combined scenario: **5/8 → 8/8**. When a memory said "approval done" but the workflow said wait: naive proceeded **5/5**, governed waited **5/5**. Governed invariants: **10/10**.

## Memory Is Not One Thing

![Five kinds of state (working context, conversation, episodic memory, enterprise knowledge, workflow state), each with its own lifetime, writer, read path and authority.](../assets/02-five-state-types.png)

*Five kinds of state. Each needs its own owner, lifetime, read path and authority.*

Most "agent memory" designs mix these together:

- **Working context** is what the model sees for one call. It is assembled, then thrown away.
- **Conversation** is this session. It is contextual: what the user wants, not what is true.
- **Episodic memory** is past experience. It is advisory, and it can expire or be superseded.
- **Enterprise knowledge** is what the owning systems say, and it is cited.
- **Workflow state** is where a task is right now. It is authoritative, and read by key.

**Workflow state is not memory. It is system state.**

## A Vector Store Is Not a State Model

![Left: everything embedded into one vector database read by top-K. Right: each kind of state in its own store with its own read path.](../assets/03-vector-store-not-state-model.png)

*Use a vector index where similarity helps. Don't make it your state model.*

A vector index is a good way to find candidates inside memory and knowledge. It can't own state: it has no idea who wrote a record, how long it is valid, or what it is allowed to decide.

**Making K smaller didn't make naive memory safer.** With plain top-5 retrieval, the authoritative runbook reached the model's context in only **1 of 10** experiments. A smaller K mostly removed the evidence that would have corrected the bad memories. It didn't keep the bad memories out.

## Similarity Finds Candidates. Governance Decides What Enters Context.

![The naive arm goes straight from top-K to context. The governed arm takes the same candidates through six gates: scope, lifecycle, provenance, authority, conflicts and budget. Conversation and workflow state enter by their own rules in both arms.](../assets/05-governed-retrieval.png)

*The same candidates, six deterministic gates.*

The six gates run in order: **scope**, **lifecycle**, **provenance**, **authority**, **conflicts**, **budget**. Whatever they exclude stays in an audit trail for operators. The model only sees the counts.

**Scope Comes Before Ranking**

Tenant, environment, entity, user and session are checked *before* similarity ranking. A wrong-tenant memory never competes for a slot, however similar it is. Metadata the model has to notice is not isolation.

**Authority Is Claim-Specific**

Every memory record carries the metadata governance reads: provenance, scope, lifetime, a trust class and a claim type. The model reads the content. Governance reads the metadata.

Authority isn't a field on the record. One explicit policy derives it from the **source** and the **claim type**:

- The **CMDB** is authoritative for ownership.
- The **workflow store** is authoritative for where the task is.
- The **current runbook** is authoritative for procedure.
- A **past episode** is advisory.
- **Unverified external content** is trusted for nothing, even when it arrives as a tool result.

**Conflicts Stay Visible — They Aren't Averaged Away**

![An old episode, the current runbook, the release record and a workflow policy disagree. The runbook and release record become evidence; the episode becomes marked history; the policy is enforced by the action layer.](../assets/09-conflict-resolution.png)

*The runbook wins for procedure. The policy goes to enforcement. The old episode stays as history.*

A contradicted memory isn't deleted. It is marked, demoted and kept out of the evidence. The contradiction itself is **frozen data**: no model guesses what conflicts with what.

## Remembering Is a Write Operation

![Four events meet the write policy: a user's "remember forever" becomes contextual, session-only memory; an unregistered tool's output and a model's speculation are not remembered; a verified workflow outcome becomes advisory memory with provenance.](../assets/07-write-boundary.png)

*What becomes memory, visible to whom, for how long, is decided at write time.*

Not every message deserves to become memory. Given the same 4 events, the naive writer kept all 4. The governed writer kept 2, as its write policy says: the verified outcome as advisory memory, and the user's "remember forever" as a session-only assertion that expires in a day. Each one has a scope, an expiry and an authority tier.

**What Gets Remembered Is a Trust Decision**

![A poisoned "remember forever" assertion written in one session. Naive: stored, recalled in a later session, in evidence. Governed: stored as a contextual, session-scoped assertion and excluded in the later session.](../assets/08-memory-poisoning.png)

*A poisoned memory does its damage later, in a different session, looking like experience.*

**The write boundary mattered later, too.** When a new session recalled memory, the naive context carried **3 invalid records**: the poisoned user assertion, the unverified tool's instruction and the model's unsupported speculation. The governed context carried **0**.

**The ability to write memory is a trust boundary.** OWASP lists memory and context poisoning as **ASI06**, and MITRE ATLAS lists it as **AML.T0080**.

## Nine Rules for Governed Agent Memory

Before trying to break it, here are the invariants the architecture has to hold.

![Nine rules for governed agent memory, each with where the POC implements it: separate the five kinds of state; attach metadata at write time; treat writes as a trust boundary; filter scope before ranking; expire and supersede explicitly; make authority an explicit policy; mark conflicts, never average; never answer workflow state from memory; audit exclusions but don't show them to the model.](../assets/14-design-checklist.png)

*Nine rules you can apply to your own agent. Each is implemented and tested in the POC.*

## We Built the Failure on Purpose

![The POC design: a frozen scenario, the same candidates for both arms, the same agent, model and seeds, a deterministic scorer. Experiments M0 to M9, each injecting one failure class.](../assets/11-poc-design.png)

*Each experiment injects one failure. Only admission differs between the two agents.*

I built a small, simulated production estate: two tenants, staging and production, runbooks, release records and about thirty memories of past incidents. Then I planted the failures this article is about: an expired workaround, another tenant's near-duplicate, a staging-only fix, an old episode that the current runbook contradicts, a superseded procedure, a poisoned "remember forever", more valid evidence than the budget can hold, and a memory that disagrees with the workflow.

Two agents faced each failure. They share F2's platform, the same memories, the same embeddings (`nomic-embed-text`), the same 20 candidates, the same token budget, the same workflow facts, the same model (`gpt-oss:20b`) and the same five seeds. **Only admission differs:** one takes the most similar memories, the other runs them through the six gates.

Every experiment, metric and pass condition was written down and frozen before the run, and the recorded run replays exactly without a GPU.

## What the Run Actually Proved

![Recorded results: invalid evidence admitted per experiment for naive, top-5 and governed; runbook presence; governed invariants; the M9 outcome; forbidden actions; and an honest note on the confounded outcome metric.](../assets/12-results.png)

*One recorded run: 100 agent decisions.*

**Governance kept invalid evidence out.** Across the injected failures, the naive context let in **13 invalid evidence records**. The governed path let in **0**. All 10/10 of the governed rules we wrote down before the run held.

**It didn't pay for that with recall.** The obvious objection is that filtering bad memories is easy if you throw away half the good ones. That didn't happen here. Useful memory recalled went up, not down: from **5/8 to 8/8** in the combined scenario, and from **2/7 to 5/7** when the evidence budget was tight. Authority ranking kept the runbook and the release record when less useful memories competed for space.

**Workflow state beat remembered claims.** We gave both agents the same authoritative workflow state: `WAITING_APPROVAL`. Into memory we planted an old record saying approval had already been given. In **5 out of 5 runs**, the naive agent trusted the memory and went ahead with the rollback. The governed agent never lets memory answer a workflow question. It waited for approval in **5 out of 5 runs**. *(Experiment M9.)*

**The damage was in the context, not in the commands.** Neither agent ever chose a destructive action such as restarting pods (0 naive, 0 governed). The bad memories changed what the agent saw. Whenever the runbook was also in context, they didn't change what it did.

Two results from earlier complete the picture. A smaller K removed the corrective runbook instead of the bad memories (present in 1 of 10 experiments). The poisoned write stayed out of the governed context in a later session (3 invalid records naive, 0 governed).

**One Metric Failed Our Own Test**

I also scored each agent's final action, and that score failed. For most experiments the preregistered "correct" action was to roll back through the release pipeline. Both agents usually named that exact fix, and then chose to wait, because the runbook says that rollback needs approval. My scorer mixed two questions: *what is the right fix?* and *are we allowed to do it right now?*

It even produced a fake naive win. When the budget was tight, the naive agent "scored" 5/5 only because the runbook, and with it the approval requirement, had been crowded out of its context. *(Experiments M0–M8.)*

I report that score as recorded. I didn't change the prompt or re-score after seeing it. The experiment didn't only test memory. It also exposed a bad evaluation definition, which is exactly why you build these things. The admission numbers and the workflow-state result are the evidence.

## What This POC Does Not Prove

- One synthetic estate, one authority policy, one model, five fixed seeds. The counts illustrate a mechanism. They aren't population estimates.
- Conflicts are given as data, not detected.
- Poisoning is tested only up to the write boundary. Attacks on the gates themselves belong to T6.
- It is not a full enterprise RAG system. That comes in S2.

## Remembered Is Not the Same as True

![Four kinds of state and their roles: memory is advisory, knowledge is source-owned, workflow state is authoritative, working context is assembled. Next in the series: S2 enterprise knowledge and RAG, T6 agent and MCP security, R1 evals.](../assets/13-takeaway.png)

*Memory is advisory. Knowledge is source-owned. Workflow state is authoritative.*

The hard problem with agent memory isn't remembering more. It's deciding what deserves to be remembered, when it stops being valid, who it belongs to, and whether it may influence the current decision.

> **A production agent should remember selectively, retrieve with scope, and reason from evidence whose provenance, freshness and authority are explicit.**

**Run the evidence:** [the POC on GitHub](https://github.com/ereshzealous/ai_blogs_poc/tree/main/memory_context_state_poc) has the code, the frozen scenario and the recorded run, and it replays without a GPU.
**Read the full methodology:** [the technical reference (PDF)](https://github.com/ereshzealous/ai_blogs_poc/blob/main/memory_context_state_poc/memory-context-state-poc/docs/S1-technical-reference.pdf) has every experiment, metric, test and limitation.

---

**Next in Production AI Engineering:** S2 · Enterprise Knowledge & RAG

**Previously:** F3 · Headless AI

**New to the series?** Start with the map of all fifteen chapters:

https://eresh-gorantla.medium.com/start-here-a-hands-on-map-of-production-ai-engineering-5056549657db

**Go deeper:** [Technical deep dive](https://github.com/ereshzealous/ai_blogs_poc/blob/main/memory_context_state_poc/memory-context-state-poc/docs/S1-technical-reference.pdf) · [Results](https://github.com/ereshzealous/ai_blogs_poc/blob/main/memory_context_state_poc/results/s1-results.md) · [Proof of concept on GitHub](https://github.com/ereshzealous/ai_blogs_poc/tree/main/memory_context_state_poc)

*Every measured number in this chapter comes from `memory-context-state-poc/runs/2026-09-18-recorded/summary.json` of run `2026-09-18-recorded`.*

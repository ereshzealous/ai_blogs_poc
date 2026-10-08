# store_world · Northwind Goods

A deterministic, simulated online store and one anchor case, **ORD-4917**, shared by the Production AI Engineering
notes. F1 uses it to ask *which capability should an agent see, and may this invocation execute?*; later notes reuse
the same world for reliability, experience and state.

**Northwind Goods is fictional.** So are its carriers, payment processor and vendors. Nothing here talks to a network,
nothing is random, and no real company's data or branding appears. Everything is generated from **seed 4917**, so two
builds on two machines produce byte-identical state, and a run can quote a hash of it.

## What it is

```python
from store_world import load_catalog, StoreWorld

catalog = load_catalog()                        # the static store: customers, orders, payments, stock, staff, policies
order = catalog.order("ORD-4917")               # the anchor case
world = StoreWorld(run_id="my-run")             # per-run event log over that catalog

duplicate = world.duplicate_capture("ORD-4917") # she was charged twice
world.refund_order("ORD-4917", amount=duplicate.amount, method_id=duplicate.method_id,
                   idempotency_key="...", actor="STAFF-2210")
world.order_status("ORD-4917")                  # "paid"
```

- `load_catalog()` is the world as it stands before anyone acts: ~240 orders, ~90 customers, stock, carriers,
  delivery options with cut-offs, helpdesk cases, staff with refund and compensation limits, and versioned policies.
- `StoreWorld(run_id=...)` is an event-sourced overlay in SQLite. Every executed action is an event; state is derived
  from the catalog plus that run's events, so two runs never see each other's side effects and nothing needs resetting.
- `Inventory` answers the questions an argument binder asks: does `ORD-9998` exist, what kind of thing is
  `CASE-20871`, which region is this order in, what was *her last order*, which card did she actually pay with.
- `Faults` are the hooks later notes switch on (payment timeout, lost response, carrier down, duplicate webhook).
  In F1 they are all off.

## The anchor case

Black Friday, 27 November 2026. The customer ordered noise-cancelling headphones as a birthday gift, needed by Friday
4 December. Checkout slowed at 10:15, she retried, and she was captured twice, two minutes apart. `ORD-4917` sits at
`payment_pending`. Standard delivery misses the Friday; express meets it but costs more than the agent's compensation
limit, so it needs a supervisor. A refund goes to the original payment method, never a different one, and never in bulk.

The checkout slowdown itself is the incident an earlier edition of F1 investigated (INC-4917); here it is only the
cause of the double charge.

## Using it

```bash
uv sync --group dev
uv run pytest                 # the facts above are pinned by tests
python -c "from store_world import load_catalog, catalog_digest; print(catalog_digest(load_catalog()))"
```

Depend on it by path, the way `headless_ai_poc` depends on `layered_agent_poc`:

```toml
dependencies = ["store-world"]
[tool.uv.sources]
store-world = { path = "../../store_world", editable = true }
```

`DATA-CONTRACT.md` is the part later notes may rely on. Anything not in that document may change.

Licence: MIT.

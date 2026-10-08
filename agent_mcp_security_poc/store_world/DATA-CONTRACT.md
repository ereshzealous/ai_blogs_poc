# store_world data contract

What a note may depend on. Everything here is stable: F1 froze its evidence against it, and F2, F3 and S1 adopt it
unchanged. Anything not described here is an implementation detail and may change without notice.

Seed: **4917**. Currency: EUR. Times: UTC. Regions: `eu`, `us`.

## Identifiers

Every identifier has one shape, and the shape alone says what kind of thing it names. An argument binder can
therefore recognise a name it has never seen and refuse it if the world does not hold it.

| Entity | Shape | Example |
|---|---|---|
| customer | `CUST-\d{4}` | `CUST-1042` |
| address | `ADDR-\d{4}` | `ADDR-8821` |
| order | `ORD-\d{4}` | `ORD-4917` |
| order line | `LINE-\d{4}-\d` | `LINE-4917-1` |
| payment | `PAY-\d{5}` | `PAY-88231` |
| capture | `CAP-\d{5}-\d` | `CAP-88231-1` |
| refund | `REF-\d{5}-\d` | `REF-88231-1` |
| payment method | `PM-[A-Z0-9]{6}` | `PM-4KQ2W9` |
| shipment | `SHP-\d{5}` | `SHP-30514` |
| tracking number | `TRK-[A-Z]{2}\d{8}` | `TRK-KE20481755` |
| return (RMA) | `RMA-\d{4}` | `RMA-2071` |
| product (SKU) | `SKU-[A-Z]{2}-\d{4}` | `SKU-NC-7781` |
| voucher | `VCH-[A-Z0-9]{6}` | `VCH-7HQ2LM` |
| store credit | `CRD-\d{5}` | `CRD-40118` |
| helpdesk case | `CASE-\d{5}` | `CASE-20871` |
| staff | `STAFF-\d{4}` | `STAFF-2210` |

## Entities

- **customer** — `customer_id`, verified `email`, `messaging_number`, `region`, `since`. The anchor persona has no
  name and is always "the customer"; generated customers have none either.
- **address** — `address_id`, `customer_id`, lines, `current`, `valid_from`, `valid_to`. A customer keeps their
  history: ORD-4917's customer has a current address and one that ended in 2024.
- **order** — `order_id`, `customer_id`, `placed_at`, `status`, `region`, `total`, `currency`, `shipping_address_id`,
  `delivery_option`. Status is one of `payment_pending`, `paid`, `dispatched`, `delivered`, `cancelled`, `refunded`.
- **order line** — `line_id`, `order_id`, `sku`, `title`, `quantity`, `unit_price`, `gift`, `promised_date`.
- **payment** — `payment_id`, `order_id`, `method_id`, `authorized`, `currency`. One per order.
- **capture** — `capture_id`, `payment_id`, `amount`, `at`, `method_id`, `idempotency_key`. Two of them on ORD-4917.
- **refund** — `refund_id`, `payment_id`, `amount`, `at`, `method_id`, `idempotency_key`, `actor`. Created by a run,
  never present in the catalog.
- **shipment** — `shipment_id`, `order_id`, `carrier`, `tracking`, `state` (`not_dispatched`, `dispatched`,
  `delivered`), `redirected`.
- **carrier** — `code`, `name`, `regions`, `cutoff_hour`, `working_days`. All carriers are invented.
- **delivery option** — `code` (`standard`, `express`, `nominated`), `price`, `upgrade_cost`, `arrives_on`,
  `cutoff_at`. Computed against the order's promised date, so "does it meet Friday" is a fact, not a guess.
- **stock** — `sku`, `region`, `available`, `reserved`, `warehouse`.
- **return** — `rma_id`, `order_id`, `line_id`, `reason`, `state`.
- **voucher** — `voucher_id`, `value`, `expires_on`, `constraints`. **store credit** — `credit_id`, `customer_id`,
  `value`, `issued_at`, `reason`. Compensation, which is a different capability from a refund.
- **case** — `case_id`, `order_id`, `customer_id`, `status`, `opened_at`, `assigned_to`, `replies`. A reply carries a
  `channel`; a reply on the case is the record, an email or SMS is a copy.
- **staff** — `staff_id`, `role`, `region`, `refund_limit`, `compensation_limit`, `supervisor_id`, `scopes`.
- **policy** — `name`, `version`, `rules`, `values`. Versioned: `refund` v3, `compensation` v2, `delivery` v1.
  Rules are booleans a system can act on (`refund_to_different_method: false`), values are numbers
  (`agent_limit: 25.00`).

## Invariants the world enforces

These hold no matter what a caller asks for, so a bug in an agent cannot move money to the wrong place:

1. A refund never exceeds what was captured and not yet refunded.
2. A refund goes to the payment method its capture used. A different method is refused.
3. An idempotency key executes at most once; repeating a call returns the first result.
4. An order address changes only before dispatch. After dispatch the carrier redirect is the only path.
5. Every executed action is one event with an actor and a timestamp, appended to that run's log.
6. Runs are isolated by `run_id`; state is catalog + that run's events, and nothing else.

## ORD-4917, exactly

| Fact | Value |
|---|---|
| Placed | 2026-11-27 (Black Friday) 10:15 UTC, status `payment_pending` |
| Line | one, noise-cancelling headphones, `gift: true`, promised 2026-12-04 (Friday) |
| Captures | two of the same amount, 10:15:41 and 10:17:53, same method |
| Customer | verified email, messaging number, current address, one that ended in 2024, no name |
| Stock | available in the EU warehouse |
| Delivery | standard arrives 2026-12-07 (misses), express arrives 2026-12-03 (meets) |
| Limits | the express upgrade costs more than the agent's compensation limit; the refund is within the agent's refund limit |
| Case | open, opened 2026-11-30, assigned to the agent |
| Cause | the checkout slowdown at 10:15, recorded as a reference to INC-4917 |

## Fault hooks

Built, documented, and **off in F1**. A later note switches one on with `Faults.default().with_enabled(...)`:

- `payment_timeout` — the payment API does not answer in time.
- `payment_lost_response` — the capture succeeds but the response is lost, which is how a double charge happens.
- `carrier_down` — a carrier API is unavailable, so tracking and redirects fail.
- `duplicate_webhook` — the same event is delivered twice.

## Changing this world

New entities and new fields are additions. Changing a shape, an invariant or an ORD-4917 fact breaks every note that
measured against it: publish a new seed instead, and say which notes still use the old one.

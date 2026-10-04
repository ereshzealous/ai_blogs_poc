# RB-DB-003 · Application connection-pool exhaustion

## Symptoms
Requests queue for a database connection: high `acquire_wait`, `waiting` > 0, `in_use` pinned at `max_connections`,
errors like `ConnectionPoolTimeoutError`. Database CPU is often normal or low, because fewer queries get through.

## Likely causes
A lowered pool maximum (often a client-library upgrade with new defaults), a connection leak, or a traffic spike.
A config regression shows up only where traffic is high enough to fill the pool: staging can look healthy.

## Mitigation
Restore the previous pool size, which usually means rolling back the release that changed it. Do not restart pods:
a restart clears the queue for seconds and hides the cause.

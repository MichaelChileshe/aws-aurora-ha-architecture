# ADR 0002: Month-end reports use a custom endpoint, not the reader endpoint

**Status:** Accepted
**Context:** The obvious move is to point finance at the cluster's built-in **reader** endpoint. It load-balances over every reader, and in this cluster that includes `themba-claims-b`, the failover target. The routing check sent 4 of 6 reader connections to b.

## Options considered

| Option | Verdict |
|---|---|
| Keep reports on the writer | ❌ Measured: intake p95 4.1 → 18.3 ms, writer CPU 99% |
| Built-in reader endpoint | ❌ Reports land on the failover target. After a failover, the new writer could be the instance finance just pinned at 100% |
| Instance endpoint of the reporting replica | ⚠️ Works, but hard-codes one instance into finance's tools. Replacing that replica means changing every report connection |
| **Custom endpoint `themba-reporting`, static member: the reporting replica** | ✅ Chosen |

## Decision

`create-db-cluster-endpoint --endpoint-type READER --static-members themba-claims-reporting`. Finance's tools use `themba-reporting` and nothing else.

## Consequences

- Reports can only ever reach the reporting replica: proven 3 of 3 before the failover and still true after it.
- Intake p50 stayed at 3.1 ms (baseline 3.2) with the same reports running.
- The replica behind the name can be replaced or resized without touching finance's configuration.
- If the reporting replica fails, `themba-reporting` has no member until it's replaced. Month-end reports wait, but claims intake is never affected. That's the right failure mode for this business.

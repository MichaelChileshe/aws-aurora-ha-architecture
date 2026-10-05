# ADR 0003: The reporting replica is Aurora Serverless v2 at promotion tier 15

**Status:** Accepted
**Context:** Reporting load is two heavy days a month and almost nothing for the rest. The replica also must never become the writer.

## Options considered

| Option | Verdict |
|---|---|
| Provisioned reader sized for month-end | ❌ Paid for 730 hours to use about 48 |
| Provisioned small reader | ❌ Too slow at month-end; reports would run for hours |
| Serverless v2 reader at tier 0 or 1 | ❌ Readers in tiers 0–1 track the **writer's** capacity (so they're ready to take over), and they're failover candidates |
| **Serverless v2 reader at tier 15** | ✅ Chosen |

## Decision

`db.serverless` instance `themba-claims-reporting`, promotion tier 15, within the cluster's 0.5–4 ACU range.

## Consequences

- Measured: 1.5 ACU before the reports, 4.0 ACU (the maximum) while they ran on it, and 1.5–2.5 ACU while they ran on the writer. At 4 ACU, reports took 9.6 s each against 18.8 s on the busy writer.
- Tier 15 means Aurora promotes it last. b (tier 1) won the failover.
- It never fell to the 0.5 ACU minimum during the session; it sat at 1.5 ACU between bursts. The cost model assumes a floor of 0.5–1 ACU and flags this for monitoring.
- The cluster-level `ServerlessV2ScalingConfiguration` had to exist before any `db.serverless` instance could be added. In production the maximum would be sized from a real month-end, not set at 4.

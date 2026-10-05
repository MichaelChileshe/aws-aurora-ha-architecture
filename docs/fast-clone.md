# Fast clone: a production-sized test database in minutes

## The scenario

Themba's test team needs realistic data to test a new claims-scoring release: real volumes, real distributions, real edge cases. Restoring last night's snapshot copies every byte and takes longer the bigger the database gets. And whatever they do to the copy must never reach production.

## How it works

`restore-db-cluster-to-point-in-time --restore-type copy-on-write` creates a **clone**. The clone starts out sharing the source cluster's storage pages. A page is copied only when one side changes it, so creating a clone doesn't depend on the size of the data, and a clone that changes little costs little extra storage.

A clone is a new cluster with no instances, like any new cluster, so I added one small Serverless v2 instance (0.5–2 ACU) for the test team.

## Result ([`21`](screenshots/21-step10-fast-clone-timings.png), [`22`](screenshots/22-step10-clone-isolation-queries.png))

| Measure | Value |
|---|---|
| Clone cluster available (storage ready) | **158 s** |
| Clone usable (its instance available) | **629 s** |
| Claims in the clone | **3,007,432** |
| `UPDATE` of 1,000 rows on the clone | 43 ms |
| Rows marked `TEST-DATA`, clone | **1,000** |
| Rows marked `TEST-DATA`, production | **0** |

- **Most of the 629 s was creating an instance**, not copying data: the storage was ready in 158 s. A clone of a 3 TB database would be ready on the same timescale.
- **3,007,432 is exact.** 3,000,000 seeded claims plus the 7,432 intake writes from the three drills (2,571 + 2,793 + 2,068). The clone has everything committed up to its restore point (`--use-latest-restorable-time`).
- **The isolation is real.** The test team's change exists only on the clone. Production, queried through its own writer endpoint (b after the failover drill), shows 0.
- **The clone uses the source's database users.** It copies the database, including the master user, so my tool logged in to the clone with the source cluster's managed secret.

## In real use

A clone of production contains policyholders' personal information. Before handing it to a test team I would either mask it (replace names, ID numbers and contact details), or give the clone the same access controls and logging as production. That's what ISO 27001 A.8.33 (test information) and POPIA expect. And clones bill like any cluster, so they should be deleted when the test cycle ends. I deleted this one in the teardown, before its source.

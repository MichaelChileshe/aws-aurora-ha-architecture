# ADR 0005: Test environments are copy-on-write clones

**Status:** Accepted
**Context:** The test team needs production-sized, realistic data, quickly, and nothing they do may reach production.

## Options considered

| Option | Verdict |
|---|---|
| Restore last night's snapshot | ⚠️ A full copy: time and storage grow with the database, and data is up to a day old |
| Logical dump and restore (`pg_dump`) | ❌ Hours at production size, and it loads the production writer while dumping |
| Synthetic test data only | ⚠️ Safe, but misses the real distributions that cause real bugs |
| **Aurora fast clone (`--restore-type copy-on-write`)** | ✅ Chosen |

## Decision

`restore-db-cluster-to-point-in-time --restore-type copy-on-write --use-latest-restorable-time`, with its own Serverless v2 range (0.5–2 ACU) and one instance.

## Consequences

- Measured: storage ready in 158 s, usable in 629 s (mostly instance creation), holding all 3,007,432 claims committed up to the restore point.
- Proven isolation: 1,000 rows changed on the clone, 0 on production.
- The clone holds real personal information. In production use it gets production-grade access control, or masking before handover (ISO 27001 A.8.33, POPIA).
- A clone bills like a cluster and must be deleted before its source. Clones belong in the teardown or end-of-test runbook.

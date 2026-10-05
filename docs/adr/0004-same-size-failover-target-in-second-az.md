# ADR 0004: A same-size failover target in a second AZ, at tier 1

**Status:** Accepted (instance class amended during the build)
**Context:** A failover should be short, and the new writer should be as capable as the old one. The planned class was `db.t4g.medium` (Graviton).

## Decision

- `themba-claims-a` (tier 0, `us-east-1a`) is created first and becomes the writer.
- `themba-claims-b` (tier 1, `us-east-1b`) has the **same instance class** and is the preferred failover target.
- Both use `db.t3.medium`.

## The amendment

`db.t4g.medium` turned out to be offered only in `us-east-1f` for Aurora PostgreSQL 17.9, so the writer couldn't be created in my subnets (`InvalidVPCNetworkStateFault`). The options:

| Option | Verdict |
|---|---|
| Add a subnet in `us-east-1f` and put the writer there | ⚠️ Works for one instance. b in `us-east-1b` hits the same wall, so both would end up in 1f: no AZ separation |
| Keep t4g for the writer only, a different class for b | ❌ The failover target would differ in size from the writer |
| **`db.t3.medium` for both** (same 2 vCPU / 4 GiB, offered in all six AZs) | ✅ Chosen |

## Consequences

- Measured: forced failover a → b with a 7.0-second write outage, and the new writer has the same capacity as the old one. The drill measured availability, not latency, so post-failover performance would be the next thing to test.
- The design's key property, two AZs with equal capacity, was kept, at the cost of a slightly more expensive Intel class for the lab.
- Burstable (`t`) classes are fine for a lab. Production would use memory-optimised (`r`) classes, checked per AZ before the change.

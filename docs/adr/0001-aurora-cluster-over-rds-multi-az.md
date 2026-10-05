# ADR 0001: Aurora PostgreSQL cluster rather than RDS Multi-AZ

**Status:** Accepted
**Context:** Themba's claims database needs read capacity that's isolated from intake, a short and predictable failover, and fast production-sized copies for testing. All three RDS PostgreSQL high-availability options were on the table.

## Options considered

| | RDS Multi-AZ **DB instance** | RDS Multi-AZ **DB cluster** | **Aurora cluster** |
|---|---|---|---|
| Standby | 1, in another AZ, synchronous | 2 readable standbys in 3 AZs, semi-synchronous | Up to 15 replicas on one shared volume |
| Standby readable? | ❌ No: availability only | ✅ Yes | ✅ Yes |
| Typical failover | 60–120 s | under 35 s | usually well under a minute (**7.0 s measured here**) |
| Isolate reporting on its own instance | Add a separate read replica (async, its own storage) | Standbys are fixed; both are failover candidates | ✅ Custom endpoint to a dedicated replica |
| Reporting capacity that follows demand | ❌ | ❌ | ✅ Serverless v2 replica |
| Production-sized test copy | Snapshot restore (full copy) | Snapshot restore (full copy) | ✅ Copy-on-write clone |
| Storage | EBS per instance | Local storage per instance | 6 copies across 3 AZs, shared |

## Decision

Aurora PostgreSQL: a writer, a same-size reader in a second AZ as the failover target, and a Serverless v2 reader for reporting behind a custom endpoint.

## Consequences

- Reporting isolation and failover use **different** replicas, which none of the RDS options let me do as cleanly. On a Multi-AZ DB cluster, a report on a standby is a report on a failover candidate.
- Measured: a 7.0-second write outage; intake latency unchanged while reports ran on the replica; a clone usable in 629 s.
- Aurora's I/O and instance pricing differ from RDS. For a database this size, the shared storage and the clone feature justify it. For a small, low-traffic database where availability is the only goal, RDS Multi-AZ (DB instance) would be the cheaper, simpler choice.
- Cross-Region protection is out of scope here (see `aws-multi-region-dr-failover`). Aurora Global Database would be the next step.

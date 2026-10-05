# ADR 0007: Replica auto scaling as a guardrail, configured but not load-tested

**Status:** Accepted
**Context:** Finance has its own replica. The general reader endpoint will still pick up new read traffic over time (dashboards, new services), and capacity there should grow without a ticket.

## Decision

Application Auto Scaling on the cluster's `rds:cluster:ReadReplicaCount`: minimum 1, maximum 3, target tracking on `RDSReaderAverageCPUUtilization` at 70%, with 300-second cooldowns ([`templates/replica-autoscaling.json`](../../templates/replica-autoscaling.json)).

## Why I didn't trigger it

A new Aurora replica takes about 10 minutes to become available, and the drills deliberately kept load **off** the general readers to measure isolation cleanly. Triggering it would have meant a separate, longer, more expensive drill. I verified the scalable target (min 1, max 3, [`23`](../screenshots/23-step11-replica-auto-scaling-target.png)) after attaching the policy from the template, and I describe it as configured, not as proven under load.

## Consequences

- Auto scaling only removes replicas **it** added, never the ones I created, so the failover target and the reporting replica are safe from scale-in.
- Replicas it adds join the reader endpoint, not `themba-reporting` (static members only), so finance's isolation holds.
- Teardown deletes every cluster member found at the time, including any replica auto scaling added.
- The maximum caps the cost of a runaway read workload.

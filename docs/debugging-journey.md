# Debugging journey

Most of this build ran as designed. Two things went wrong on the day, and several were planned around before I started. These are the notes I'd want the next engineer to have.

---

## 1 · The instance class wasn't offered in my Availability Zones

**What happened:** the cluster created fine, but creating the writer failed:

```
An error occurred (InvalidVPCNetworkStateFault) when calling the CreateDBInstance operation:
You can't create a db.t4g.medium database instance because no subnets exist in Availability Zones
with sufficient capacity for VPC and storage type : aurora for db.t4g.medium. Please first create
at least one new subnet; choose from these Availability Zones: us-east-1f.
```

**Why my pre-check missed it:** before creating anything, I'd checked that both instance classes were orderable for the default engine version (Aurora PostgreSQL 17.9). The check counted offerings **in the Region**, and `db.t4g.medium` returned 2, so it passed ([`01`](screenshots/01-step0-engine-version-and-orderable-checks.png)). But an offering in the Region isn't an offering in **my** AZs.

**How I diagnosed it:** I listed the AZs each class is actually offered in:

```bash
aws rds describe-orderable-db-instance-options --engine aurora-postgresql --engine-version "$PG_VERSION" \
  --db-instance-class db.t3.medium  --query 'OrderableDBInstanceOptions[0].AvailabilityZones[].Name' --output text
# us-east-1a  us-east-1b  us-east-1c  us-east-1d  us-east-1e  us-east-1f
aws rds describe-orderable-db-instance-options --engine aurora-postgresql --engine-version "$PG_VERSION" \
  --db-instance-class db.t4g.medium --query 'OrderableDBInstanceOptions[0].AvailabilityZones[].Name' --output text
# us-east-1f
```

**The decision:** the error suggested adding a subnet in `us-east-1f`. That would have worked for the writer, but the failover target in `us-east-1b` would have hit the same wall, and putting both in 1f would have thrown away the reason for having two AZs. I kept the design and changed the class: `db.t3.medium` has the same 2 vCPU and 4 GiB, and is offered everywhere. I saved it as `DB_CLASS` so both provisioned instances used the same value ([`07`](screenshots/07-step4-three-instances-tiers-and-classes.png)).

**Lesson:** when a design depends on specific AZs, check availability **per AZ**, against the subnet group, not per Region. Same as for EC2 instance types.

---

## 2 · Chaining the create and the wait

The same failure produced a second, misleading error: the waiter I'd run straight after the create reported `DBInstanceNotFound`. It was waiting for an instance that was never created. Read on its own, that looks like a different problem.

From then on I chained them: `create-db-instance … && aws rds wait db-instance-available …`. The wait runs only if the create succeeded, so a failure shows exactly one error, at the step that caused it. I use the same pattern (`&&`, `until` loops polling a status, `sleep` after creating IAM resources) to turn multi-step changes into single sequences that stop at the first failure.

---

## 3 · A `!` threw away the whole clean check

```
aws secretsmanager list-secrets --query "SecretList[?starts_with(Name,'rds!cluster')].Name" --output text
-bash: !cluster': event not found
```

In an interactive bash shell, `!` inside **double** quotes triggers history expansion. I'd run the seven clean-check queries as one block, and bash rejects the entire input when expansion fails, so **none** of the seven ran ([`25`](screenshots/25-step13-clean-check.png)). An empty screen there proves nothing. The fix is single quotes around the query, with a JMESPath backtick literal inside:

```bash
aws secretsmanager list-secrets --query 'SecretList[?starts_with(Name,`rds!cluster`)].Name' --output text
```

I re-ran the whole clean check with the corrected line, and every query came back empty ([`26`](screenshots/26-step13-clean-check-rerun.png)). The lesson: a check that didn't run looks exactly like a check that passed. The corrected block is in [`teardown.md`](teardown.md).

---

## 4 · Two clocks

The load tool prints UTC. The AWS CLI printed CloudWatch timestamps in my local time (UTC+2). The writer's 99% CPU minute shows as **08:14**; the reports-on-writer run ended at **06:14:48** UTC (its results file is stamped `061448`), so its reports ran from 06:12:48 to 06:14:18. Same event. Before comparing them I converted everything to one timezone ([`read-isolation.md`](read-isolation.md) has the aligned table).

**Lesson:** in an incident timeline, write the timezone on every timestamp. A two-hour offset looks exactly like "the metric doesn't match the event".

---

## 5 · Measuring failover from the application's side

AWS's event log shows the failover took 11.4 seconds (started → completed). My tool measured a 7.0-second write outage. Neither is wrong: they measure different things. The old writer accepted writes for part of AWS's window, and the application recovered about a second after AWS said it was done.

I report the application's number as the outage, because that's what brokers and the call centre experience, with AWS's events as corroboration ([`failover-drill.md`](failover-drill.md)).

---

## 6 · Not overclaiming the fix

With reports on `themba-reporting`, the reporting-phase p95 was 6.0 ms against a 4.0 ms baseline. Sixteen of eighteen 5-second windows matched the baseline. Two spiked (21.5 ms and 43.7 ms), and I didn't find a cause I could prove from the data I had. The median (3.1 ms against 3.2 ms) and the writer's CPU (11–13% against 99%) are the clear results, and I report the p95 as measured.

---

## 7 · Planned around before the build

- **EC2's 16 KB user-data limit.** The load box installs my tool at boot. The plain tool plus the install script came to 17,495 bytes, over the limit. [`scripts/build_userdata.py`](../scripts/build_userdata.py) embeds the tool gzip-compressed and base64-encoded (8,154 bytes), and refuses to produce anything over 16,384.
- **Serverless v2 needs a cluster-level range first.** `db.serverless` instances can't be added until the cluster has `ServerlessV2ScalingConfiguration`, so I set 0.5–4 ACU on `create-db-cluster`.
- **The writer is whichever instance comes first.** I created `themba-claims-a` alone and waited for it before adding readers, so the topology was deterministic.
- **The reader endpoint isn't a reporting endpoint.** Routing checks showed it sending connections to b (the failover target) 4 times in 6, which is why reports got a custom endpoint.

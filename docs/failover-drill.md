# Failover drill: measuring the outage the application feels

## The scenario

Last quarter, patching broke Themba's claims intake for "over a minute", and nobody knew the real number. Without a number, nobody could decide how long the application's retry logic should wait, or tell brokers what to expect during maintenance.

The only number that matters to the business is how long **the application** couldn't write. The console's "failover completed" timestamp is AWS's view, not the application's.

## How I tested it

`claimsdb failover-drill --target themba-claims-b` runs for 120 seconds:

- It writes a claim through the **writer** endpoint continuously (about 18 per second), and records the time, the result and which instance accepted each write.
- At 20 seconds it calls `aws rds failover-db-cluster --target-db-instance-identifier themba-claims-b`.
- It reports the **longest gap between two successful writes**, writer before and after, error counts, and the kinds of errors seen.

The load box's role allows `rds:FailoverDBCluster` on this cluster and its instances only ([`policies/loadbox-perms.json.tpl`](../policies/loadbox-perms.json.tpl)).

## Result ([`17`](screenshots/17-step9-failover-drill-live.png), [`18`](screenshots/18-step9-failover-summary-7s-outage.png), [`19`](screenshots/19-step9-members-after-failover-and-rds-events.png))

```
longest write outage: 7.0s   last good write 37.9s on themba-claims-a   first good write 44.9s on themba-claims-b
writer before: themba-claims-a   writer after: themba-claims-b
writes ok: 2068   write errors: 25
  error seen: SSL SYSCALL error: EOF detected
  error seen: connection to server at "themba-claims.cluster-….us-east-1.rds.amazonaws.com" (…) failed
```

| Time (UTC) | Drill time | Event | Source |
|---|---|---|---|
| 06:29:04 | 20.8 s | `failover-db-cluster` requested | claimsdb |
| 06:29:15.5 | ~32 s | Started cross AZ failover to DB instance: themba-claims-b | RDS events |
| 06:29:21 | 37.9 s | last good write, on `themba-claims-a` | claimsdb |
| 06:29:26.9 | ~44 s | Completed customer initiated failover to DB instance: themba-claims-b | RDS events |
| 06:29:28 | 44.9 s | first good write, on `themba-claims-b` | claimsdb |

The 5-second windows show the shape: 55 good writes and 2 errors in the 40 s window, then 2 good writes and 23 errors in the 45 s window, then back to 92–93 per window on b (with one dip, to 74, at 80 s).

## What the numbers mean

- **7.0 seconds of failed writes, not "over a minute".** That's the figure to design retries around. A retry with backoff up to about 10–15 seconds rides through it.
- **AWS's own window was 11.4 seconds** (started → completed). The application's outage was shorter, because the old writer kept accepting writes for part of that window.
- **Nothing in the application changed.** The writer endpoint name is the same; its DNS record now points at b ([`20`](screenshots/20-step9-endpoints-follow-new-writer.png)). The first good write came about a second after AWS reported completion, consistent with that DNS change reaching the client.
- **The reporting endpoint didn't move.** `themba-reporting` still answered from the reporting replica. A failover doesn't disturb finance.
- **The errors are the ones to handle.** `SSL SYSCALL error: EOF detected` (the connection was cut mid-statement) and connection failures to the cluster endpoint. A production client should treat both as retryable for a write that's safe to repeat (or check whether the write landed first).

## Why b, and why tier 1

- **Same size as the writer.** After a failover the new writer has the same capacity as the old one. Failing over to a smaller instance would turn an outage into a slowdown.
- **Different AZ.** b is in `us-east-1b`. If `us-east-1a` fails, the writer, the old writer and the reporting replica there are affected, but b isn't.
- **Tier 1, with the reporting replica at tier 15.** Aurora promotes the lowest tier first. Even in an unplanned failover (where AWS picks the target), b is chosen over the reporting replica.

After the drill, a was a reader at tier 0 and b the writer at tier 1 ([`19`](screenshots/19-step9-members-after-failover-and-rds-events.png)). Tiers describe preference for the *next* failover; they don't fail back on their own.

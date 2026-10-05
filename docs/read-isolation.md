# Read isolation: month-end reports off the writer

## The scenario

Finance's month-end pack runs one heavy query per report: claims per day and status, with totals, averages and the 95th-percentile claim value (`percentile_cont(0.95)`, which has to sort every claim in each group). Four analysts run it in a loop for two days. Meanwhile the call centre and brokers keep submitting new claims, each one a small `INSERT` that normally takes about 3 ms.

When both workloads share one instance, they share its CPU, memory and I/O. The reports win, because they're bigger.

## How I tested it

`claimsdb impact --report-to <endpoint>` runs for 150 seconds:

- **Intake:** a claim is written through the **writer** endpoint about every 50 ms (statement timeout 5 s), and each one is timed.
- **0–30 s, baseline:** intake only.
- **30–120 s, reporting:** 4 threads loop the month-end report on the chosen endpoint.
- **120–150 s, recovery:** reports stopped mid-query (cancelled), intake carries on.

Every 5 seconds it prints inserts, p50, p95 and max latency, errors and reports completed. At the end it prints a phase summary with p99 and saves every sample to CSV.

I ran it twice against the same 3,000,000-claim table: once with reports on the **writer** (last month-end), once on the **custom endpoint `themba-reporting`** (the design).

## Results

### Reports on the writer ([`09`](screenshots/09-step7-reports-on-writer-live.png), [`10`](screenshots/10-step7-reports-on-writer-summary.png))

| Phase | Inserts | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---|---|---|---|
| Baseline | 560 | 3.2 | 4.1 | 7.1 | 79.5 |
| **Reporting** | 1,452 | **11.2** | **18.3** | **27.5** | 49.2 |
| Recovery | 559 | 3.3 | 4.2 | 7.8 | 34.4 |

17 reports completed, averaging 18.8 s each, served by `themba-claims-a` (the writer). 0 intake errors.

The moment the reports started (the 35 s window), intake p50 jumped from 3.2 ms to 10.7 ms and stayed between 10.5 and 13.4 ms for the whole reporting phase. Intake also slowed in volume: about 81 claims per 5-second window instead of 94, because each insert took longer. The recovery phase snapped straight back to baseline, which shows the cause was the concurrent reports and nothing else.

### Reports on `themba-reporting` ([`11`](screenshots/11-step8-reports-on-reporting-endpoint-live.png), [`12`](screenshots/12-step8-reports-on-reporting-endpoint-summary.png))

| Phase | Inserts | p50 ms | p95 ms | p99 ms | max ms |
|---|---|---|---|---|---|
| Baseline | 561 | 3.2 | 4.0 | 6.4 | 16.6 |
| **Reporting** | 1,670 | **3.1** | **6.0** | 19.5 | 92.8 |
| Recovery | 562 | 3.2 | 4.0 | 6.0 | 56.6 |

36 reports completed, averaging 9.6 s each, served by `themba-claims-reporting`. 0 intake errors.

Sixteen of the eighteen 5-second reporting windows had p95 between 3.4 and 4.7 ms, the same as the baseline. Two windows spiked (45 s: p95 21.5 ms; 105 s: p95 43.7 ms), which is why the phase p95 is 6.0 rather than 4.0. The median never moved. I'm reporting the numbers as measured rather than rounding them away.

### What CloudWatch saw ([`13`](screenshots/13-step8-writer-cpu-cloudwatch.png), [`14`](screenshots/14-step8-reporting-replica-acus-cloudwatch.png))

CloudWatch printed times in my local time (UTC+2); the load tool prints UTC.

| Local time | Writer CPU (max) | Reporting replica ACUs | What was running |
|---|---|---|---|
| 08:09–08:11 | 10.8% → 43.6% → 43.7% | 4.0 → 1.5 → 2.0 | seeding 3M claims (08:09:32–08:10:27) |
| 08:12–08:13 | 11.0% → 33.1% | 2.5 → 1.5 | reports **on the writer** from 08:12:48 |
| **08:14** | **99.2%** | 1.5 | reports on the writer, until 08:14:18 |
| 08:15 | 37.0% | 1.5 | recovery phase, then between runs |
| 08:16–08:18 | 11.3–13.4% | **4.0** | reports **on themba-reporting**, 08:16:49–08:18:19 |
| 08:19–08:21 | 10.5–13.2% | 4.0 | after the run (still 4.0 ACU at 08:22); scale-down is gradual |

The console showed the reporting replica's lag behind the writer at 10–19 ms throughout ([`15`](screenshots/15-step8-console-reporting-replica-metrics.png)). The reports were reading data at most a few milliseconds old, which is fine for month-end figures.

## Why a custom endpoint, not the reader endpoint

The built-in reader endpoint load-balances over **all** readers. In this cluster that includes `themba-claims-b`, the failover target. Reports on the reader endpoint would have hit b about two times in three (the routing check sent 4 of 6 connections there, [`08`](screenshots/08-step6-seed-3m-claims-and-endpoint-routing.png)), so after a failover the new writer could be the instance finance had just pinned at 100% CPU.

`themba-reporting` is a custom endpoint with one **static member**. It can only ever reach the reporting replica, before and after a failover ([`20`](screenshots/20-step9-endpoints-follow-new-writer.png)).

## Why Serverless v2 for the reporting replica

- Month-end is two days of heavy load and 28 days of almost none. A provisioned reader sized for month-end would be paid for all month.
- It scaled on its own load: 1.5 ACU before the reports, 4.0 (the maximum I set) during them. It also reached 4.0 briefly during the 3-million-row bulk load. At 4 ACU it finished reports in 9.6 s, faster than the 18.8 s the writer managed while also taking claims.
- At promotion **tier 15** it scales independently. A Serverless v2 reader in tier 0 or 1 tracks the **writer's** capacity instead, so it's ready to take over; that's the wrong behaviour for a reporting replica.
- It never dropped to the 0.5 ACU minimum during the session; between bursts it sat at 1.5 ACU. The minimum is a floor, not a promise of where it idles.

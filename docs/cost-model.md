# Cost model

## Why this build was planned around time

Most of my builds bill per request, and an idle stack costs nothing. Aurora instances bill **per hour while they exist**, busy or not. So I planned the build to measure everything and tear down in one sitting, and launched the load box early so it booted while Aurora was creating, rather than adding its boot time to the clock.

## What this build cost (estimate)

| Item | Rate (us-east-1 list price, approx.) | Usage | Approx. cost |
|---|---|---|---|
| 2 × `db.t3.medium` Aurora PostgreSQL | ~US$0.08 per instance-hour | ~1 hour each | ~US$0.16 |
| Serverless v2 reporting replica | US$0.12 per ACU-hour | 1.5–4 ACU for ~1 hour | ~US$0.25–0.40 |
| Clone instance, Serverless v2 | US$0.12 per ACU-hour | 0.5–2 ACU for ~20 minutes | ~US$0.05 |
| Load box `t3.small` + public IPv4 | ~US$0.02 + US$0.005 per hour | ~1.5 hours | ~US$0.04 |
| Aurora storage and I/O | per GB-month + per million I/O requests | 3M-row load + drills | cents to tens of cents |
| Secrets Manager secret | US$0.40 per secret-month, pro-rated | ~2 hours | < US$0.01 |
| **Total** | | | **about US$1–2** |

Rates are approximate list prices; check the Aurora pricing page for current figures. Cost Explorer refreshes at least once every 24 hours, so the build's cost appears the next day. Left running, this cluster would cost roughly US$10 a day.

## At Themba's real size

Assume a production writer and failover replica on `db.r6g.large`, and month-end reporting needing about 16 ACU for 2 days a month:

| Option for month-end reporting | How it's paid for | Approx. monthly cost |
|---|---|---|
| Reports on the writer | nothing extra | **US$0**, plus three bad month-ends a quarter (frozen call centre, phoned-in claims) |
| Provisioned reader sized for month-end (~32 GiB, e.g. `db.r6g.xlarge`), running all month | 730 instance-hours | ~US$380 |
| **Serverless v2 reader, 0.5–16 ACU** | ~2 days at ~16 ACU + 28 days near the floor | **~US$130–175** (48 h × 16 ACU × US$0.12 ≈ US$92, plus ~680 h × 0.5–1 ACU × US$0.12 ≈ US$41–82) |

The Serverless v2 reporting replica buys the same month-end headroom for roughly 35–45% of the price of a provisioned reader, because it only scales up for the two days that need it. In this build it idled at 1.5 ACU rather than 0.5, so the real floor needs watching in CloudWatch (`ServerlessDatabaseCapacity`) before trusting the estimate. Figures are illustrative and exclude storage, I/O and backups, which are the same for every option.

## Cost controls in the design

- Clones bill like any cluster. Delete them at the end of the test cycle.
- Replica auto scaling has a maximum (3), so a runaway dashboard can't add readers forever.
- `--backup-retention-period 1` for the lab. Production would keep 7–35 days, and that's a deliberate cost.

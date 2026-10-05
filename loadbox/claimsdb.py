#!/usr/bin/env python3
"""claimsdb - Themba Insurance claims load + measurement tool. Runs on the load box inside the VPC.

It finds the cluster's endpoints and the managed master-user secret itself (AWS CLI + instance role),
so no hostnames or passwords are ever typed.

  claimsdb whoami <endpoint> [--repeat N]    which DB instance answers an endpoint, and is it the writer?
  claimsdb seed [--rows N]                   create the claims table and load N realistic claims
  claimsdb sql <endpoint> "<SQL>"            run one statement and print the result
  claimsdb impact --report-to <endpoint>     claims intake latency before / during / after month-end reporting
  claimsdb failover-drill --target <id>      keep writing claims, force a failover, measure the write outage

<endpoint> is one of: writer, reader, or the name of a custom endpoint (e.g. themba-reporting).
Add --cluster <id> to talk to another cluster (e.g. the clone). Python 3.9 compatible.
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import psycopg2

CONFIG = json.load(open(os.environ.get("CLAIMS_CONFIG", "/opt/claims/config.json")))
REGION = CONFIG["region"]
PRIMARY = CONFIG["cluster"]
RESULTS = os.environ.get("CLAIMS_RESULTS", "/opt/claims/results")

INTAKE_SQL = ("INSERT INTO claims (policy_no, claim_zar, status, notes) "
              "VALUES (%s, %s, 'NEW', 'intake')")
REPORT_SQL = """
SELECT date_trunc('day', created_at) AS day, status,
       count(*) AS claims, sum(claim_zar) AS total_zar, avg(claim_zar) AS avg_zar,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY claim_zar) AS p95_zar
FROM claims
GROUP BY 1, 2
ORDER BY 1, 2
"""


def now():
    return time.monotonic()


def stamp():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def out(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- AWS lookups
def aws(*args):
    res = subprocess.run(["aws", *args, "--region", REGION, "--output", "json"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"\nFAILED: aws {' '.join(args[:2])}\n{res.stderr.strip()}")
    return json.loads(res.stdout) if res.stdout.strip() else {}


_clusters = {}


def cluster_info(cluster):
    if cluster not in _clusters:
        c = aws("rds", "describe-db-clusters", "--db-cluster-identifier", cluster)["DBClusters"][0]
        eps = aws("rds", "describe-db-cluster-endpoints", "--db-cluster-identifier", cluster)["DBClusterEndpoints"]
        _clusters[cluster] = (c, eps)
    return _clusters[cluster]


def endpoint_host(cluster, name):
    c, eps = cluster_info(cluster)
    if name == "writer":
        return c["Endpoint"]
    if name == "reader":
        return c["ReaderEndpoint"]
    custom = {e["DBClusterEndpointIdentifier"]: e["Endpoint"] for e in eps if e.get("EndpointType") == "CUSTOM"}
    if name in custom:
        return custom[name]
    sys.exit(f"no endpoint '{name}' on {cluster}. Known: writer, reader" +
             "".join(", " + k for k in sorted(custom)))


_creds = {}


def credentials(cluster):
    """The cluster's RDS-managed secret. A clone has none of its own and shares the source's login."""
    if cluster not in _creds:
        c, _ = cluster_info(cluster)
        arn = (c.get("MasterUserSecret") or {}).get("SecretArn")
        if not arn:
            arn = cluster_info(PRIMARY)[0]["MasterUserSecret"]["SecretArn"]
        secret = aws("secretsmanager", "get-secret-value", "--secret-id", arn)["SecretString"]
        _creds[cluster] = json.loads(secret)
    return _creds[cluster]


def connect(cluster, name, statement_timeout_ms=None):
    creds = credentials(cluster)
    options = f"-c statement_timeout={statement_timeout_ms}" if statement_timeout_ms else None
    return psycopg2.connect(host=endpoint_host(cluster, name), port=5432, dbname="claims",
                            user=creds["username"], password=creds["password"],
                            connect_timeout=3, sslmode="require",
                            application_name="claimsdb", options=options)


def instance_of(conn):
    cur = conn.cursor()
    cur.execute("SELECT aurora_db_instance_identifier(), pg_is_in_recovery()")
    iid, in_recovery = cur.fetchone()
    conn.rollback()
    return iid, ("reader" if in_recovery else "WRITER")


# ---------------------------------------------------------------- stats helpers
def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def fmt_ms(v):
    return f"{v:8.1f}"


# ---------------------------------------------------------------- workers
class Intake(threading.Thread):
    """Writes one claim roughly every 50 ms through the WRITER endpoint and times each commit."""

    def __init__(self, cluster, t0):
        super().__init__(daemon=True)
        self.cluster, self.t0 = cluster, t0
        self.stop = threading.Event()
        self.samples = []   # (seconds since start, latency ms, instance)
        self.errors = []    # (seconds since start, error text)
        self.i = 0

    def run(self):
        conn, iid = None, None
        while not self.stop.is_set():
            try:
                if conn is None:
                    conn = connect(self.cluster, "writer", statement_timeout_ms=5000)
                    iid, _ = instance_of(conn)
                self.i += 1
                start = now()
                cur = conn.cursor()
                cur.execute(INTAKE_SQL, (100000 + self.i % 50000, round(500 + (self.i * 37) % 60000, 2)))
                conn.commit()
                self.samples.append((start - self.t0, (now() - start) * 1000.0, iid))
            except Exception as exc:  # connection dropped, failover, timeout...
                self.errors.append((now() - self.t0, str(exc).strip().splitlines()[0][:90]))
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
                conn = None
                time.sleep(0.2)
                continue
            time.sleep(0.05)
        if conn is not None:
            conn.close()


class Reporter(threading.Thread):
    """Runs the month-end report in a loop against one endpoint."""

    def __init__(self, cluster, target, t0):
        super().__init__(daemon=True)
        self.cluster, self.target, self.t0 = cluster, target, t0
        self.stop = threading.Event()
        self.conn = None
        self.runs = []      # (seconds since start, duration s, instance)
        self.errors = 0

    def run(self):
        while not self.stop.is_set():
            try:
                if self.conn is None:
                    self.conn = connect(self.cluster, self.target)
                    self.iid, _ = instance_of(self.conn)
                start = now()
                cur = self.conn.cursor()
                cur.execute(REPORT_SQL)
                cur.fetchall()
                self.conn.rollback()
                self.runs.append((start - self.t0, now() - start, self.iid))
            except Exception:
                if self.stop.is_set():
                    break
                self.errors += 1
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None
                time.sleep(0.5)

    def halt(self):
        self.stop.set()
        try:
            if self.conn is not None:
                self.conn.cancel()   # stop the in-flight report on the server, not just in this thread
        except Exception:
            pass


# ---------------------------------------------------------------- commands
def cmd_whoami(a):
    for n in range(a.repeat):
        conn = connect(a.cluster, a.endpoint)
        iid, role = instance_of(conn)
        conn.close()
        out(f"{stamp()}  {a.endpoint:<18} -> {iid:<28} {role}")
        if n + 1 < a.repeat:
            time.sleep(1)


def cmd_seed(a):
    conn = connect(a.cluster, "writer")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS claims (
                     id bigserial PRIMARY KEY,
                     policy_no integer NOT NULL,
                     claim_zar numeric(12,2) NOT NULL,
                     status text NOT NULL,
                     created_at timestamptz NOT NULL DEFAULT now(),
                     notes text)""")
    conn.commit()
    batch, done, t = 500000, 0, now()
    while done < a.rows:
        n = min(batch, a.rows - done)
        cur.execute("""INSERT INTO claims (policy_no, claim_zar, status, created_at, notes)
                       SELECT (random() * 50000)::int,
                              round((random() * 80000)::numeric, 2),
                              (ARRAY['NEW','ASSESSED','PAID','REJECTED'])[1 + floor(random() * 4)::int],
                              now() - random() * interval '30 days',
                              md5(g::text)
                       FROM generate_series(1, %s) g""", (n,))
        conn.commit()
        done += n
        out(f"{stamp()}  loaded {done:>9,} claims  ({now() - t:.0f}s)")
    cur.execute("ANALYZE claims")
    conn.commit()
    cur.execute("SELECT count(*), pg_size_pretty(pg_total_relation_size('claims')) FROM claims")
    total, size = cur.fetchone()
    out(f"\nclaims table: {total:,} rows, {size}")
    conn.close()


def cmd_sql(a):
    conn = connect(a.cluster, a.endpoint)
    iid, role = instance_of(conn)
    cur = conn.cursor()
    t = now()
    cur.execute(a.statement)
    rows = cur.fetchall() if cur.description else []
    conn.commit()
    out(f"[{a.endpoint} -> {iid} ({role})  {(now() - t) * 1000:.0f} ms]")
    if cur.description:
        out("  " + " | ".join(d[0] for d in cur.description))
        for r in rows[:25]:
            out("  " + " | ".join(str(v) for v in r))
    else:
        out(f"  {cur.rowcount} row(s) affected")
    conn.close()


def phase_of(t, base, load):
    if t < base:
        return "1-baseline"
    if t < base + load:
        return "2-reporting"
    return "3-recovery"


def prewarm(cluster, *names):
    """Resolve endpoints and credentials once, before any worker threads start."""
    for n in names:
        endpoint_host(cluster, n)
    credentials(cluster)


def cmd_impact(a):
    prewarm(a.cluster, "writer", a.report_to)
    total = a.baseline + a.load + a.recovery
    out(f"{stamp()}  claims intake on WRITER; month-end report x{a.workers} on '{a.report_to}' "
        f"from {a.baseline}s to {a.baseline + a.load}s; total {total}s")
    t0 = now()
    intake = Intake(a.cluster, t0)
    intake.start()
    reporters, seen = [], 0
    out(f"{'time':>8} {'phase':<12} {'inserts':>7} {'p50 ms':>8} {'p95 ms':>8} {'max ms':>8} {'errors':>6} {'reports':>7}")
    next_print = 5.0
    while True:
        el = now() - t0
        if not reporters and el >= a.baseline and el < a.baseline + a.load:
            reporters = [Reporter(a.cluster, a.report_to, t0) for _ in range(a.workers)]
            for r in reporters:
                r.start()
        if reporters and el >= a.baseline + a.load and not reporters[0].stop.is_set():
            for r in reporters:
                r.halt()
        if el >= next_print:
            window = [s for s in intake.samples[seen:]]
            seen = len(intake.samples)
            lat = [s[1] for s in window]
            errs = len([e for e in intake.errors if next_print - 5 <= e[0] < next_print])
            reps = sum(len(r.runs) for r in reporters)
            out(f"{next_print:>7.0f}s {phase_of(next_print - 0.1, a.baseline, a.load):<12} {len(window):>7} "
                f"{fmt_ms(pct(lat, 50))} {fmt_ms(pct(lat, 95))} {fmt_ms(max(lat) if lat else 0)} {errs:>6} {reps:>7}")
            next_print += 5.0
        if el >= total:
            break
        time.sleep(0.1)
    intake.stop.set()
    intake.join(5)
    for r in reporters:
        r.join(5)

    out(f"\nSUMMARY  report target: {a.report_to}")
    out(f"{'phase':<12} {'inserts':>7} {'p50 ms':>8} {'p95 ms':>8} {'p99 ms':>8} {'max ms':>8}")
    for ph in ("1-baseline", "2-reporting", "3-recovery"):
        lat = [s[1] for s in intake.samples if phase_of(s[0], a.baseline, a.load) == ph]
        out(f"{ph:<12} {len(lat):>7} {fmt_ms(pct(lat, 50))} {fmt_ms(pct(lat, 95))} "
            f"{fmt_ms(pct(lat, 99))} {fmt_ms(max(lat) if lat else 0)}")
    runs = [r2 for r in reporters for r2 in r.runs]
    served = sorted({r2[2] for r2 in runs})
    avg = sum(r2[1] for r2 in runs) / len(runs) if runs else 0
    writers = sorted({s[2] for s in intake.samples})
    out(f"reports completed: {len(runs)}  avg {avg:.1f}s each  served by: {', '.join(served) or '-'}")
    out(f"intake written to: {', '.join(writers)}   intake errors: {len(intake.errors)}")
    save_csv(f"impact-{a.report_to}", intake.samples)


def cmd_failover(a):
    prewarm(a.cluster, "writer")
    out(f"{stamp()}  writing claims continuously; failover to {a.target} at {a.failover_at}s; total {a.seconds}s")
    t0 = now()
    intake = Intake(a.cluster, t0)
    intake.start()
    fired_at, last_ok_count, last_err_count, next_print = None, 0, 0, 5.0
    while True:
        el = now() - t0
        if fired_at is None and el >= a.failover_at:
            aws("rds", "failover-db-cluster", "--db-cluster-identifier", a.cluster,
                "--target-db-instance-identifier", a.target)
            fired_at = now() - t0
            out(f"{stamp()}  >>> failover-db-cluster requested at {fired_at:.1f}s (target {a.target})")
        if el >= next_print:
            ok, err = len(intake.samples), len(intake.errors)
            on = intake.samples[-1][2] if intake.samples else "-"
            out(f"{next_print:>6.0f}s  writes ok +{ok - last_ok_count:<4} errors +{err - last_err_count:<4} last writer: {on}")
            last_ok_count, last_err_count = ok, err
            next_print += 5.0
        if el >= a.seconds:
            break
        time.sleep(0.1)
    intake.stop.set()
    intake.join(5)

    ok = intake.samples
    after = [s for s in ok if fired_at is not None and s[0] >= fired_at]
    before = [s for s in ok if fired_at is None or s[0] < fired_at]
    gaps = []
    pts = ([before[-1]] if before else []) + after
    for x, y in zip(pts, pts[1:]):
        gaps.append((y[0] - x[0], x, y))
    out("\nSUMMARY")
    if gaps:
        gap, x, y = max(gaps, key=lambda g: g[0])
        out(f"longest write outage: {gap:.1f}s   last good write {x[0]:.1f}s on {x[2]}   "
            f"first good write {y[0]:.1f}s on {y[2]}")
    out(f"writer before: {before[-1][2] if before else '-'}   writer after: {after[-1][2] if after else '-'}")
    out(f"writes ok: {len(ok)}   write errors: {len(intake.errors)}")
    distinct = []
    for _, e in intake.errors:
        if e not in distinct:
            distinct.append(e)
    for e in distinct[:4]:
        out(f"  error seen: {e}")
    save_csv("failover", ok)


def save_csv(name, samples):
    try:
        os.makedirs(RESULTS, exist_ok=True)
        path = os.path.join(RESULTS, f"{name}-{datetime.now(timezone.utc):%H%M%S}.csv")
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["seconds", "latency_ms", "instance"])
            w.writerows([(round(s[0], 3), round(s[1], 2), s[2]) for s in samples])
        out(f"samples saved: {path}")
    except OSError as exc:
        out(f"(could not save samples: {exc})")


def main():
    p = argparse.ArgumentParser(description="Themba claims load + measurement tool")
    p.add_argument("--cluster", default=PRIMARY)
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("whoami")
    w.add_argument("endpoint")
    w.add_argument("--repeat", type=int, default=1)
    s = sub.add_parser("seed")
    s.add_argument("--rows", type=int, default=3000000)
    q = sub.add_parser("sql")
    q.add_argument("endpoint")
    q.add_argument("statement")
    i = sub.add_parser("impact")
    i.add_argument("--report-to", required=True)
    i.add_argument("--workers", type=int, default=4)
    i.add_argument("--baseline", type=int, default=30)
    i.add_argument("--load", type=int, default=90)
    i.add_argument("--recovery", type=int, default=30)
    f = sub.add_parser("failover-drill")
    f.add_argument("--target", required=True)
    f.add_argument("--failover-at", type=int, default=20)
    f.add_argument("--seconds", type=int, default=120)
    a = p.parse_args()
    {"whoami": cmd_whoami, "seed": cmd_seed, "sql": cmd_sql,
     "impact": cmd_impact, "failover-drill": cmd_failover}[a.cmd](a)


if __name__ == "__main__":
    main()

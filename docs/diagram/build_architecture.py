#!/usr/bin/env python3
"""Regenerates docs/architecture.svg + docs/architecture.png using the OFFICIAL AWS Architecture Icons.

The icon pack is not committed (AWS licenses it for diagrams, not redistribution). Download it from
https://aws.amazon.com/architecture/icons/, unzip, then:

    AWS_ICONS_DIR=/path/to/unzipped-icon-package python3 build_architecture.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from awsdiag import Diagram, GREY, INK

WRITE, READ, REPORT, FAIL, OK, MGMT = "#545B64", "#0073BB", "#8C4FFF", "#D13212", "#1D8102", "#E7157B"
AZ = "#00A4A6"
d = Diagram(1800, 1050)

d.text(40, 40, "Themba Insurance claims database: Aurora PostgreSQL high availability", 19, "bold")
d.text(40, 64, "Writer + same-size failover replica in another AZ  ·  Serverless v2 reporting replica behind a custom "
               "endpoint  ·  fast clone  ·  replica auto scaling  ·  us-east-1", 13, "normal", GREY)

d.group("cloud", 20, 90, 1760, 945, "AWS Cloud")
d.group("region", 40, 130, 1330, 885, "us-east-1")
d.group("vpc", 60, 175, 1000, 800, "themba-aurora-vpc  10.50.0.0/16")

# availability zones
for x, name in [(80, "Availability Zone us-east-1a"), (570, "Availability Zone us-east-1b")]:
    d.box(x, 215, 470, 740, AZ, fill="none")
    d.text(x + 12, 236, name, 12.5, "bold", AZ)

# internet gateway on the VPC edge
d.icon("igw", 436, 152, 40)
d.text(482, 168, "internet gateway (outbound only)", 11, "normal", GREY)

# ---------------------------------------------------------------- public subnet: load box
d.group("public", 100, 250, 430, 150, "public 10.50.0.0/24")
d.icon("ec2_instance", 120, 295, 52)
d.text(184, 308, "Load box  themba-loadbox", 12.5, "bold")
d.text(184, 325, "t3.small · no inbound rules · IMDSv2", 11.5, "normal", GREY)
d.text(184, 342, "claimsdb: intake writes + month-end", 11.5, "normal", GREY)
d.text(184, 358, "reports, timed per statement", 11.5, "normal", GREY)
d.line([(456, 192), (456, 250)], GREY, dashed=True, arrow=False)

# ---------------------------------------------------------------- endpoints band
d.box(90, 425, 940, 120, "#232F3E", fill="#FFFFFF", dashed=False)
d.text(180, 446, "Cluster endpoints: DNS names AWS keeps pointed at the right instances", 12.5, "bold")
eps = [
    (110, "WRITER  (cluster endpoint)", "always the current writer", WRITE),
    (420, "READER", "load-balanced over ALL readers", READ),
    (730, "CUSTOM  themba-reporting", "static member: reporting only", REPORT),
]
for x, name, sub, c in eps:
    d.raw(f'<rect x="{x}" y="458" width="280" height="72" rx="6" fill="#fff" stroke="{c}" stroke-width="1.8"/>')
    d.text(x + 140, 486, name, 12.5, "bold", c, "middle")
    d.text(x + 140, 506, sub, 11.5, "normal", GREY, "middle")

# load box -> endpoints
d.line([(150, 400), (150, 456)], WRITE, width=2.4)
d.label(158, 416, "claim intake", WRITE, 10.5)
d.line([(500, 380), (870, 380), (870, 456)], REPORT, width=2.4)
d.label(640, 375, "month-end reports", REPORT, 10.5)

# ---------------------------------------------------------------- private subnets: instances
for gx, glabel in [(100, "private 10.50.1.0/24  (no route to the internet)"), (590, "private 10.50.2.0/24  (no route to the internet)")]:
    d.group("private", gx, 650, 430, 195, "")
    d.text(gx + 40, 838, glabel, 12, "bold", AZ)


def inst(x, y, key, name, l1, l2, l3, c=INK):
    d.icon(key, x, y, 56)
    d.text(x + 28, y + 76, name, 12.5, "bold", c, "middle")
    d.text(x + 28, y + 93, l1, 11, "normal", GREY, "middle")
    d.text(x + 28, y + 109, l2, 11, "normal", GREY, "middle")
    d.text(x + 28, y + 125, l3, 11, "bold", c, "middle")


inst(172, 690, "aurora_pg", "themba-claims-a", "db.t3.medium · tier 0", "writer at start", "reader after the drill", WRITE)
inst(384, 690, "aurora_pg_alt", "themba-claims-reporting", "db.serverless · tier 15", "0.5–4 ACU, scales alone", "never promoted", REPORT)
inst(778, 690, "aurora_pg", "themba-claims-b", "db.t3.medium · tier 1", "failover target", "writer after the drill", OK)

# endpoint -> instance routing
d.line([(200, 530), (200, 686)], WRITE, width=2.4)
d.line([(250, 530), (250, 572), (790, 572), (790, 686)], FAIL, dashed=True, width=2)
d.label(262, 568, "after failover: same name, new writer", FAIL, 10.5)
d.line([(560, 530), (560, 600), (420, 600), (420, 686)], READ)
d.line([(600, 530), (600, 600), (820, 600), (820, 686)], READ)
d.line([(870, 530), (870, 627), (444, 627), (444, 686)], REPORT, width=2.4)

# ---------------------------------------------------------------- shared storage
d.raw('<rect x="100" y="860" width="920" height="80" rx="6" fill="#F3EEFF" stroke="#8C4FFF" stroke-width="1.4"/>')
d.icon("aurora", 116, 870, 60)
d.text(190, 892, "Aurora cluster volume  ·  themba-claims", 13, "bold")
d.text(190, 911, "one shared, encrypted volume: 6 copies across 3 AZs  ·  every instance reads the same pages", 11.5,
       "normal", GREY)
d.text(190, 928, "3,000,000 claims (374 MB) loaded once through the writer; readers query the same pages", 11.5, "normal", GREY)

# ---------------------------------------------------------------- regional services
sx = 1090
d.icon("secrets", sx, 200, 48)
d.text(sx + 58, 218, "Secrets Manager", 12.5, "bold")
d.text(sx + 58, 234, "RDS-managed master secret", 11, "normal", GREY)
d.text(sx + 58, 249, "rds!cluster-…  (no typed passwords)", 11, "normal", GREY)

d.icon("session_manager", sx, 292, 48)
d.text(sx + 58, 310, "Session Manager", 12.5, "bold")
d.text(sx + 58, 326, "shell on the load box:", 11, "normal", GREY)
d.text(sx + 58, 341, "no SSH, no key, no open port", 11, "normal", GREY)

d.icon("cloudwatch", sx, 384, 48)
d.text(sx + 58, 402, "CloudWatch", 12.5, "bold")
d.text(sx + 58, 418, "writer CPU · reporting ACUs", 11, "normal", GREY)
d.text(sx + 58, 433, "replica lag 10–19 ms", 11, "normal", GREY)

d.icon("app_autoscaling", sx, 476, 48)
d.text(sx + 58, 494, "Application Auto Scaling", 12.5, "bold")
d.text(sx + 58, 510, "reader CPU target 70%", 11, "normal", GREY)
d.text(sx + 58, 525, "1–3 replicas (configured)", 11, "normal", GREY)

d.box(1080, 580, 270, 210, OK, fill="#F1F8EE")
d.icon("aurora", 1094, 594, 48)
d.text(1150, 612, "Fast clone", 12.5, "bold", OK)
d.text(1150, 628, "themba-claims-test", 11.5, "bold")
d.text(1094, 664, "copy-on-write: shares the source", 11, "normal", GREY)
d.text(1094, 680, "pages, stores only what changes", 11, "normal", GREY)
d.text(1094, 704, "storage ready 158 s · usable 629 s", 11, "bold", INK)
d.text(1094, 722, "1,000 rows changed on the clone", 11, "normal", GREY)
d.text(1094, 738, "→ production still shows 0", 11, "bold", OK)
d.text(1094, 762, "1 Serverless v2 instance, 0.5–2 ACU", 11, "normal", GREY)
d.line([(1020, 915), (1100, 915), (1100, 792)], OK, dashed=True)
d.label(1030, 911, "clone", OK, 10.5)

d.icon("iam_role", 1122, 838, 40)
d.text(1170, 852, "themba-loadbox-role", 12, "bold")
d.text(1170, 868, "describe · fail over this cluster", 11, "normal", GREY)
d.text(1170, 883, "read rds!cluster-* secrets only", 11, "normal", GREY)

# ---------------------------------------------------------------- measured + legend
bx, by = 1395, 130
d.box(bx, by, 365, 470, "#D5DBDB", fill="#fff", dashed=False)
d.text(bx + 14, by + 26, "Measured", 13.5, "bold")
lines = [
    ("Month-end reports ON THE WRITER:", FAIL, "bold"),
    ("  intake p50 3.2 → 11.2 ms", INK, "normal"),
    ("  intake p95 4.1 → 18.3 ms  (4.5×)", INK, "normal"),
    ("  writer CPU peaked at 99%", INK, "normal"),
    ("Reports ON themba-reporting:", OK, "bold"),
    ("  intake p50 3.1 ms (baseline 3.2)", INK, "normal"),
    ("  writer CPU stayed at 11–13%", INK, "normal"),
    ("  reports done: 17 → 36 (9.6 s each)", INK, "normal"),
    ("  reporting replica scaled to 4 ACU", INK, "normal"),
    ("Forced failover under load:", OK, "bold"),
    ("  write outage 7.0 s, a → b", INK, "normal"),
    ("  25 failed writes, 2,068 succeeded", INK, "normal"),
    ("  no connection string changed", INK, "normal"),
    ("Fast clone: 3,007,432 claims", OK, "bold"),
    ("  usable in 629 s, isolated from prod", INK, "normal"),
]
for i, (t, c, w) in enumerate(lines):
    ind = 14 if t.startswith("  ") else 0
    d.text(bx + 14 + ind, by + 54 + i * 27, t.strip(), 12, w, c)

lx, ly = 1395, 625
d.raw(f'<rect x="{lx}" y="{ly}" width="365" height="175" rx="4" fill="#fff" stroke="#D5DBDB"/>')
d.text(lx + 12, ly + 22, "Legend", 13, "bold")
leg = [(WRITE, False, 2.4, "claim intake → writer"), (READ, False, 2, "reader endpoint routing"),
       (REPORT, False, 2.4, "month-end reports → reporting only"), (FAIL, True, 2, "writer endpoint after failover"),
       (OK, True, 2, "copy-on-write clone")]
for i, (c, dash, w, t) in enumerate(leg):
    y = ly + 46 + i * 26
    d.line([(lx + 12, y), (lx + 58, y)], c, dashed=dash, width=w)
    d.text(lx + 66, y + 4, t, 11.5)

here = os.path.dirname(os.path.abspath(__file__))
d.save(os.path.join(here, "..", "architecture.svg"), os.path.join(here, "..", "architecture.png"))
print("wrote docs/architecture.svg and docs/architecture.png")

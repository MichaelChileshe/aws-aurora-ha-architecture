#!/usr/bin/env python3
"""Fill @@NAME@@ placeholders in a template from environment variables, and refuse to leave any unfilled.

Usage:  python3 scripts/render.py <template> <output>
Only @@NAME@@ is replaced, so ordinary $shell variables inside a template are left alone.
"""
import os, re, sys

src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
names = sorted(set(re.findall(r"@@([A-Z0-9_]+)@@", text)))
missing = [n for n in names if not os.environ.get(n)]
if missing:
    sys.exit(f"\nMISSING values for: {', '.join(missing)}\nRun  source ./env.sh  from the repo folder (or the step that saves them) first.\n")
for n in names:
    text = text.replace(f"@@{n}@@", os.environ[n])
os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
with open(dst, "w", newline="\n") as f:
    f.write(text)
print(f"rendered {dst}  (filled: {', '.join(names) if names else 'nothing'})")

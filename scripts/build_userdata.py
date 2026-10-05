#!/usr/bin/env python3
"""Build the load box's boot script: the template with the region filled in and the claimsdb tool embedded
(gzip-compressed + base64, because EC2 user data is limited to 16 KB).

Usage:  python3 scripts/build_userdata.py            -> writes build/userdata.sh
"""
import base64, gzip, os, textwrap
from kit_aws import ROOT, env

tpl = open(os.path.join(ROOT, "loadbox", "userdata.sh.tpl")).read()
tool = open(os.path.join(ROOT, "loadbox", "claimsdb.py"), "rb").read()
packed = base64.b64encode(gzip.compress(tool, 9)).decode()
packed = "\n".join(textwrap.wrap(packed, 76))
text = tpl.replace("@@REGION@@", env("REGION")).replace("@@CLAIMSDB_GZ_B64@@", packed)
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
dst = os.path.join(ROOT, "build", "userdata.sh")
with open(dst, "w", newline="\n") as f:
    f.write(text)
size = os.path.getsize(dst)
print(f"built {dst}  ({size:,} bytes; EC2 limit is 16,384)")
if size > 16384:
    raise SystemExit("too big for EC2 user data")

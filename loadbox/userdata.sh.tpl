#!/bin/bash
# Boot script for the Themba load box: installs the Postgres driver and the claimsdb tool.
set -euxo pipefail

dnf install -y python3-pip
pip3 install psycopg2-binary==2.9.10 || pip3 install --break-system-packages psycopg2-binary==2.9.10

mkdir -p /opt/claims/results
chmod 777 /opt/claims/results

cat > /opt/claims/config.json <<'CFG'
{"cluster": "themba-claims", "region": "@@REGION@@"}
CFG

# the claimsdb tool, gzip-compressed and base64-encoded to fit EC2's 16 KB user-data limit
base64 -d <<'CLAIMSDB_TOOL' | gunzip > /opt/claims/claimsdb.py
@@CLAIMSDB_GZ_B64@@
CLAIMSDB_TOOL

printf '#!/bin/bash\nexec python3 /opt/claims/claimsdb.py "$@"\n' > /usr/local/bin/claimsdb
chmod 755 /usr/local/bin/claimsdb /opt/claims/claimsdb.py
python3 -c "import psycopg2; print('psycopg2', psycopg2.__version__)"
echo "claimsdb ready"

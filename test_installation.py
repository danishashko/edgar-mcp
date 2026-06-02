#!/usr/bin/env python3
"""SEC EDGAR MCP Server - Installation Test."""

import os
import sys

print("=" * 60)
print("SEC EDGAR MCP Server - Installation Test")
print("=" * 60)

ok = True

v = sys.version_info
print(
    f"\nPython {v.major}.{v.minor}.{v.micro}",
    "OK" if (v.major > 3 or (v.major == 3 and v.minor >= 10)) else "FAIL (need 3.10+)",
)
if not (v.major > 3 or (v.major == 3 and v.minor >= 10)):
    sys.exit(1)

try:
    import mcp  # noqa: F401

    print("mcp dependency: OK")
except ImportError:
    print("mcp dependency: FAIL (pip install -r requirements.txt)")
    ok = False

server = "edgar_mcp.py"
if os.path.exists(server):
    try:
        with open(server, "r", encoding="utf-8") as f:
            compile(f.read(), server, "exec")
        print(f"{server}: valid syntax")
    except SyntaxError as e:
        print(f"{server}: SYNTAX ERROR {e}")
        ok = False
else:
    print(f"{server}: NOT FOUND")
    ok = False

print("\nChecking EDGAR connectivity...")
try:
    import json
    import urllib.request

    ua = os.environ.get("SEC_USER_AGENT", "edgar-mcp-test test@example.com")
    req = urllib.request.Request(
        "https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": ua}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        n = len(json.loads(r.read().decode("utf-8")))
    print(f"EDGAR reachable (loaded {n} companies)")
except Exception as e:
    print(f"EDGAR connectivity: FAIL {e}")
    ok = False

print("=" * 60)
print("All checks passed!" if ok else "Some checks failed.")
sys.exit(0 if ok else 1)

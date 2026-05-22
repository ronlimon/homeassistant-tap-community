"""Probe .har captures from web.tapelectric.app for OCPP management-API schema.

Reads every .har file under tests/, walks har['log']['entries'], and prints:
  - POSTs to URLs containing "ocppMessages" — full URL, headers (with secrets
    masked), request body, response status + body.
  - GETs to /accounts, /profile, /fleet, /fleet-members, /members,
    /charger-status — these often reveal where x-profile-id, x-account-id,
    and id_tag values originate.
  - Any 401/403 responses.

Secrets (Authorization, Cookie, x-api-key, refresh tokens) are masked: the
header name and value length are shown but the value itself is replaced with
"<redacted N chars>". This script is safe to re-run by anyone who captures
their own .har; its output is NOT safe to commit (it contains URLs with
account IDs etc).
"""

from __future__ import annotations

import json
import sys
from glob import glob
from pathlib import Path


SECRET_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-firebase-appcheck",
    "x-firebase-gmpid",
    "x-client-data",
}

INTERESTING_GET_FRAGMENTS = (
    "/accounts",
    "/profile",
    "/fleet",
    "/fleet-members",
    "/members",
    "/charger-status",
    "/chargers",
    "/transactions",
    "/sessions",
    "/users",
    "/me",
)


def mask_header(name: str, value: str) -> str:
    """Return value with secret content replaced by a length placeholder."""
    if name.lower() in SECRET_HEADER_NAMES:
        return f"<redacted {len(value)} chars>"
    return value


def truncate(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... <truncated {len(text) - limit} chars>"


def dump_headers(headers: list[dict]) -> None:
    for h in headers:
        name = h.get("name", "")
        value = h.get("value", "")
        print(f"    {name}: {mask_header(name, value)}")


def dump_entry(entry: dict, label: str) -> None:
    req = entry.get("request", {})
    res = entry.get("response", {})
    print(f"\n=== {label} ===")
    print(f"  {req.get('method')} {req.get('url')}")
    print("  --- request headers ---")
    dump_headers(req.get("headers", []))
    post_data = req.get("postData") or {}
    body = post_data.get("text")
    if body:
        print("  --- request body ---")
        # try pretty-print JSON
        try:
            parsed = json.loads(body)
            print(truncate(json.dumps(parsed, indent=2)))
        except (ValueError, TypeError):
            print(truncate(body))
    print(f"  --- response: {res.get('status')} {res.get('statusText', '')} ---")
    content = res.get("content", {}) or {}
    res_body = content.get("text", "")
    if res_body:
        try:
            parsed = json.loads(res_body)
            print(truncate(json.dumps(parsed, indent=2)))
        except (ValueError, TypeError):
            print(truncate(res_body))


def probe(har_path: Path) -> None:
    print(f"\n\n############################################################")
    print(f"# {har_path.name}")
    print(f"############################################################")
    with har_path.open("r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har.get("log", {}).get("entries", [])
    print(f"# entries total: {len(entries)}")

    ocpp_count = 0
    interesting_get_count = 0
    auth_fail_count = 0

    for entry in entries:
        req = entry.get("request", {})
        res = entry.get("response", {})
        url = req.get("url", "")
        method = req.get("method", "")
        status = res.get("status", 0)

        if "ocppMessages" in url and method == "POST":
            ocpp_count += 1
            dump_entry(entry, f"OCPP POST #{ocpp_count}")
            continue

        if method == "GET" and any(frag in url for frag in INTERESTING_GET_FRAGMENTS):
            interesting_get_count += 1
            if interesting_get_count <= 30:
                dump_entry(entry, f"GET {interesting_get_count}")
            continue

        if status in (401, 403):
            auth_fail_count += 1
            dump_entry(entry, f"AUTH FAIL {status} #{auth_fail_count}")

    print(f"\n# summary for {har_path.name}:")
    print(f"#   ocppMessages POSTs : {ocpp_count}")
    print(f"#   interesting GETs   : {interesting_get_count}")
    print(f"#   401/403 responses  : {auth_fail_count}")


def main() -> int:
    tests_dir = Path(__file__).parent
    har_files = sorted(Path(p) for p in glob(str(tests_dir / "*.har")))
    if not har_files:
        print("No .har files in tests/", file=sys.stderr)
        return 1
    for har in har_files:
        probe(har)
    return 0


if __name__ == "__main__":
    sys.exit(main())

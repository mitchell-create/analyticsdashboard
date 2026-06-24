"""
merchant_smoke.py — read-only verification that the Merchant API credential
(merchant_user_credentials.json) can reach the seeded Merchant Center accounts.
Refreshes the token, then GETs each account + a few products. Writes NOTHING.
Safe to run on either PC. Exits non-zero if any account GET fails.

    cd measurement-platform
    python orchestration\\merchant_smoke.py
"""

import csv
import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request

BASE = "https://merchantapi.googleapis.com"


def load_merchant_accounts():
    seed = (Path(__file__).resolve().parent.parent
            / "dbt" / "seeds" / "client_ad_accounts.csv")
    out = []
    with open(seed, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("platform", "").strip().lower() == "merchant":
                out.append((row["client_slug"].strip(), row["account_id"].strip()))
    return out


def main():
    creds_path = (Path(__file__).resolve().parent.parent
                  / "merchant_user_credentials.json")
    if not creds_path.exists():
        print(f"ERROR: {creds_path} not found - run merchant_auth.py first")
        sys.exit(1)

    info = json.loads(creds_path.read_text())
    creds = Credentials.from_authorized_user_info(info, scopes=info.get("scopes"))
    creds.refresh(Request())
    print(f"Token refresh: OK (scopes={creds.scopes})")
    sess = AuthorizedSession(creds)

    accounts = load_merchant_accounts()
    if not accounts:
        print("No platform=merchant rows in the seed.")
        sys.exit(1)

    failures = 0
    for slug, acct in accounts:
        print(f"\n=== {slug} (account {acct}) ===")
        r = sess.get(f"{BASE}/accounts/v1/accounts/{acct}")
        print(f"  GET account  -> {r.status_code}")
        if r.status_code == 200:
            print(f"    accountName: {r.json().get('accountName')!r}")
        else:
            failures += 1
            print(f"    {r.text[:400]}")
        r2 = sess.get(f"{BASE}/products/v1/accounts/{acct}/products",
                      params={"pageSize": 3})
        print(f"  GET products -> {r2.status_code}")
        if r2.status_code == 200:
            prods = r2.json().get("products", [])
            print(f"    {len(prods)} product(s) sampled:")
            for p in prods:
                attrs = p.get("productAttributes") or p.get("attributes") or {}
                print(f"      - {p.get('offerId')}: {attrs.get('title')}")
        else:
            print(f"    {r2.text[:400]}")

    print("\n" + "=" * 50)
    print("ALL ACCOUNTS REACHABLE" if failures == 0
          else f"{failures} account(s) FAILED the account GET")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

"""
merchant_register.py — one-time registration of THIS GCP project with a Merchant
Center account (a Merchant API v1 requirement). This is the ONLY write call in
the Merchant toolchain; merchant_smoke.py and the MCP are read-only.

Google allows a GCP project to be registered to only ONE Merchant Center at a
time. So when the agency advanced account (MCA) is ready, migrate with:
    python orchestration\\merchant_register.py --account <EXPAND_ID> --unregister
    python orchestration\\merchant_register.py --account <MCA_ID>
Registering the MCA covers all its linked sub-accounts.

Usage:
    cd measurement-platform
    python orchestration\\merchant_register.py --account 5551449022
"""

import argparse
import json
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import AuthorizedSession, Request

BASE = "https://merchantapi.googleapis.com"
DEFAULT_EMAIL = "mitchell@nexocore.ca"


def _session():
    creds_path = (Path(__file__).resolve().parent.parent
                  / "merchant_user_credentials.json")
    if not creds_path.exists():
        print(f"ERROR: {creds_path} not found - run merchant_auth.py first")
        sys.exit(1)
    info = json.loads(creds_path.read_text())
    creds = Credentials.from_authorized_user_info(info, scopes=info.get("scopes"))
    creds.refresh(Request())
    return AuthorizedSession(creds)


def main():
    p = argparse.ArgumentParser(
        description="Register/unregister this GCP project with a Merchant Center account")
    p.add_argument("--account", required=True,
                   help="Numeric Merchant Center account ID (use the PRIMARY/MCA id, not a subaccount)")
    p.add_argument("--email", default=DEFAULT_EMAIL,
                   help="Developer technical-contact email (registration only)")
    p.add_argument("--unregister", action="store_true",
                   help="Unregister instead (to move the project to another account, e.g. the MCA)")
    args = p.parse_args()

    verb = "unregisterGcp" if args.unregister else "registerGcp"
    url = f"{BASE}/accounts/v1/accounts/{args.account}/developerRegistration:{verb}"
    body = {} if args.unregister else {"developerEmail": args.email}

    r = _session().post(url, json=body)
    print(f"{verb} account {args.account} -> {r.status_code}")
    print(r.text[:600])

    # ALREADY_REGISTERED on a register call means we're already set up - treat as OK.
    ok = r.status_code == 200 or (not args.unregister and "ALREADY_REGISTERED" in r.text)
    if ok and not args.unregister:
        print("\nRegistered. Wait ~5 min for propagation, then run merchant_smoke.py.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

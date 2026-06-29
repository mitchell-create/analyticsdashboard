"""
tiktok_auth.py — Mint a long-lived TikTok Marketing API access token.

TikTok access tokens do NOT expire unless revoked, so this is a ONE-TIME
authorization. App ID + Secret come from your app in the TikTok For Business
Developers portal (https://business-api.tiktok.com/portal); the resulting access
token is what tiktok_sync.py uses (the `Access-Token` header).

Reads TIKTOK_APP_ID, TIKTOK_APP_SECRET, TIKTOK_REDIRECT_URI from .env (or pass
--app-id / --secret / --redirect-uri). TIKTOK_REDIRECT_URI must EXACTLY match the
Redirect URL configured on the app.

Step 1 — print the authorization URL:
    python orchestration\\tiktok_auth.py
  Open it in a browser logged into the TikTok Business account that can access the
  advertiser(s), and click Approve. TikTok redirects to your Redirect URL with
  ?auth_code=XXXX in the address bar (the page may 404 — just copy auth_code).

Step 2 — exchange the code for the long-lived token:
    python orchestration\\tiktok_auth.py --auth-code XXXX
  Writes tiktok_credentials.json next to .env and prints the authorized
  advertiser_ids (the token itself is not printed). Transfer that file to the
  dedicated PC's measurement-platform/ dir (Taildrop), like the other creds.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

AUTH_URL = "https://ads.tiktok.com/marketing_api/auth"
TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
NEXOCORE_ADVERTISER = "7528102938967982088"


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _require(value, name):
    if not value:
        print(f"ERROR: {name} is required (set it in .env or pass the flag)")
        sys.exit(1)
    return value


def main():
    p = argparse.ArgumentParser(description="Mint a long-lived TikTok Marketing API access token")
    p.add_argument("--app-id", default=None)
    p.add_argument("--secret", default=None)
    p.add_argument("--redirect-uri", default=None)
    p.add_argument("--auth-code", default=None, help="The auth_code from the redirect URL (step 2)")
    args = p.parse_args()

    _load_env()
    app_id = _require(args.app_id or os.environ.get("TIKTOK_APP_ID"), "TIKTOK_APP_ID")
    redirect_uri = _require(args.redirect_uri or os.environ.get("TIKTOK_REDIRECT_URI"), "TIKTOK_REDIRECT_URI")

    if not args.auth_code:
        url = (f"{AUTH_URL}?app_id={quote(app_id)}"
               f"&redirect_uri={quote(redirect_uri, safe='')}&state=nexocore")
        print("\n" + "=" * 72)
        print("STEP 1 — open this URL in a browser logged into the TikTok Business")
        print("account that can access the advertiser(s), then click Approve:\n")
        print(url)
        print("\nTikTok redirects to your Redirect URL with ?auth_code=XXXX in the")
        print("address bar (the page may not load — just copy the auth_code value),")
        print("then run:  python orchestration\\tiktok_auth.py --auth-code <CODE>")
        print("=" * 72)
        return

    secret = _require(args.secret or os.environ.get("TIKTOK_APP_SECRET"), "TIKTOK_APP_SECRET")
    resp = requests.post(
        TOKEN_URL,
        json={"app_id": app_id, "secret": secret, "auth_code": args.auth_code},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    try:
        body = resp.json()
    except Exception:
        print(f"ERROR: non-JSON response {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    if body.get("code") != 0 or "data" not in body:
        # TikTok returns code!=0 with a message on failure (bad/expired code, etc.)
        print(f"ERROR: token exchange failed: {json.dumps(body)[:400]}")
        sys.exit(1)

    data = body["data"]
    token = data.get("access_token")
    advertiser_ids = [str(a) for a in data.get("advertiser_ids", [])]
    creds_path = Path(__file__).resolve().parent.parent / "tiktok_credentials.json"
    creds_path.write_text(json.dumps({
        "access_token": token,
        "advertiser_ids": advertiser_ids,
        "scope": data.get("scope"),
        "app_id": app_id,
    }, indent=2))

    print("\n" + "=" * 72)
    print(f"Saved {creds_path}")
    print(f"  access_token present: {bool(token)}  (long-lived — does not expire)")
    print(f"  authorized advertiser_ids: {advertiser_ids}")
    if NEXOCORE_ADVERTISER in advertiser_ids:
        print(f"  OK: Nexocore advertiser {NEXOCORE_ADVERTISER} is authorized.")
    else:
        print(f"  WARNING: Nexocore advertiser {NEXOCORE_ADVERTISER} NOT in the list — "
              "re-authorize and make sure it's selected.")
    print("\nTransfer tiktok_credentials.json to the dedicated PC's measurement-platform/ dir.")
    print("=" * 72)


if __name__ == "__main__":
    main()

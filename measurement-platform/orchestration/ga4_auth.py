"""
ga4_auth.py — Mint a refresh token for the GA4 Data API (scope:
analytics.readonly), saved WITH the client_secret so ga4_sync.py can refresh
it. Authenticates as the signed-in user, so it uses whatever GA4 properties
that user already has access to — no service-account grants needed.

Reuses the gcloud-adc Desktop OAuth client (same one set up for Google Ads).
Client id/secret are resolved in this order:
  1. %APPDATA%\\gcloud\\ads_mcp_oauth_client.json  (the existing Desktop client)
  2. env GA4_OAUTH_CLIENT_ID / GA4_OAUTH_CLIENT_SECRET
  3. env GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET
  4. interactive prompt

Usage:
    cd measurement-platform
    python orchestration\\ga4_auth.py
    # a browser opens — sign in as the account with access to the client GA4
    # properties (e.g. mitchell@nexocore.ca), then approve.

Writes ga4_user_credentials.json next to .env (overwrites any existing one).
Transfer that file to the dedicated PC (ga4_sync.py reads it as priority-1 auth).
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _resolve_client():
    """Return (client_id, client_secret) from the gcloud client file, env, or prompt."""
    # 1. The existing gcloud-adc Desktop client file
    appdata = os.environ.get("APPDATA")
    if appdata:
        gcloud_file = Path(appdata) / "gcloud" / "ads_mcp_oauth_client.json"
        if gcloud_file.exists():
            try:
                cfg = json.loads(gcloud_file.read_text())
                node = cfg.get("installed") or cfg.get("web") or {}
                if node.get("client_id") and node.get("client_secret"):
                    print(f"  Using OAuth client from {gcloud_file}")
                    return node["client_id"], node["client_secret"]
            except Exception as e:
                print(f"  Could not read {gcloud_file}: {e}")

    # 2/3. Env vars
    cid = os.environ.get("GA4_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_ADS_CLIENT_ID")
    csec = os.environ.get("GA4_OAUTH_CLIENT_SECRET") or os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
    if cid and csec:
        return cid, csec

    # 4. Prompt
    cid = cid or input("OAuth Client ID: ").strip()
    csec = csec or input("OAuth Client Secret: ").strip()
    return cid, csec


def main():
    _load_env()
    client_id, client_secret = _resolve_client()
    if not client_id or not client_secret:
        print("ERROR: client_id and client_secret are required")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    # open_browser=False: print the URL instead of auto-opening the OS default
    # browser. The default browser may be signed into the wrong Google account
    # (and on the headless dedicated PC there's no browser at all) — so we hand the
    # URL to whoever runs this and let them open it in the right profile.
    creds = flow.run_local_server(port=8090, prompt="consent", open_browser=False)

    out = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,  # included so ga4_sync.py can refresh
        "scopes": list(creds.scopes),
    }
    creds_path = Path(__file__).resolve().parent.parent / "ga4_user_credentials.json"
    creds_path.write_text(json.dumps(out, indent=2))
    print("\n" + "=" * 60)
    print(f"Saved {creds_path}")
    print(f"  refresh_token present: {bool(creds.refresh_token)}")
    print(f"  client_secret present: {bool(creds.client_secret)}")
    print("Transfer this file to the dedicated PC's measurement-platform/ dir.")
    print("=" * 60)


if __name__ == "__main__":
    main()

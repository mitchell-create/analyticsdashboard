"""
merchant_auth.py — Mint a refresh token for the Google Merchant API (scope:
content), saved WITH the client_secret so the Merchant MCP can refresh it.
Authenticates as the signed-in user, so it reaches whatever Merchant Center
accounts that user has been added to — no service-account grants needed
(Merchant API does not accept service-account tokens directly anyway).

NOTE the `content` scope is read+write at Google's level (there is no
read-only Content scope). We enforce read-only at the MCP layer, not here.

Reuses the gcloud-adc Desktop OAuth client (same one set up for Google Ads /
GA4). Client id/secret are resolved in this order:
  1. %APPDATA%\\gcloud\\ads_mcp_oauth_client.json  (the existing Desktop client)
  2. env MERCHANT_OAUTH_CLIENT_ID / MERCHANT_OAUTH_CLIENT_SECRET
  3. env GOOGLE_ADS_CLIENT_ID / GOOGLE_ADS_CLIENT_SECRET
  4. interactive prompt

Usage:
    cd measurement-platform
    python orchestration\\merchant_auth.py
    # It prints a consent URL — open it in the Nexocore browser and sign in as
    # the account added to the client Merchant Centers (mitchell@nexocore.ca),
    # then approve.

Writes merchant_user_credentials.json next to .env (overwrites any existing
one). It is a valid `authorized_user` file, so the Merchant MCP can read it via
GOOGLE_MERCHANT_CREDENTIALS_PATH; the script also prints the three env vars
(client id/secret + refresh token) for the env-var wiring. Transfer the file to
the dedicated PC's measurement-platform/ dir.
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

# content = full Merchant API access. Google offers no read-only Content scope;
# the MCP runs read-only so the agent cannot mutate a client's live feed.
SCOPES = ["https://www.googleapis.com/auth/content"]


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
    cid = os.environ.get("MERCHANT_OAUTH_CLIENT_ID") or os.environ.get("GOOGLE_ADS_CLIENT_ID")
    csec = os.environ.get("MERCHANT_OAUTH_CLIENT_SECRET") or os.environ.get("GOOGLE_ADS_CLIENT_SECRET")
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
    # browser. The work PC's default browser is signed into the wrong Google
    # account — so hand the URL to whoever runs this and let them open it in the
    # Nexocore profile (mitchell@nexocore.ca).
    creds = flow.run_local_server(port=8090, prompt="consent", open_browser=False)

    out = {
        "type": "authorized_user",  # valid ADC authorized_user file
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,  # included so the MCP can refresh
        "scopes": list(creds.scopes),
    }
    creds_path = Path(__file__).resolve().parent.parent / "merchant_user_credentials.json"
    creds_path.write_text(json.dumps(out, indent=2))
    print("\n" + "=" * 60)
    print(f"Saved {creds_path}")
    print(f"  refresh_token present: {bool(creds.refresh_token)}")
    print(f"  client_secret present: {bool(creds.client_secret)}")
    print("\nWire the Merchant MCP either way:")
    print(f"  GOOGLE_MERCHANT_CREDENTIALS_PATH={creds_path}")
    print("  -- or the three env vars --")
    print(f"  GOOGLE_OAUTH_CLIENT_ID={creds.client_id}")
    print("  GOOGLE_OAUTH_CLIENT_SECRET=<client secret above>")
    print(f"  GOOGLE_MERCHANT_REFRESH_TOKEN={creds.refresh_token}")
    print("\nTransfer merchant_user_credentials.json to the dedicated PC's measurement-platform/ dir.")
    print("=" * 60)


if __name__ == "__main__":
    main()

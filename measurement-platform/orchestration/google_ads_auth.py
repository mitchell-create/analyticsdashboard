"""
google_ads_auth.py — One-time OAuth flow to get a refresh token for the
Google Ads API (scope: adwords). Run once, paste the printed refresh token
into measurement-platform/.env as GOOGLE_ADS_REFRESH_TOKEN.

Usage:
    python google_ads_auth.py
    # opens a browser, you consent, it prints the refresh token

Needs the OAuth client_id + client_secret of a Google Cloud "Desktop app"
(or Web app) OAuth client that has the Google Ads API enabled.
"""

import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/adwords"]


def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def main():
    _load_env()
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID") or input("OAuth Client ID: ").strip()
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET") or input("OAuth Client Secret: ").strip()
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
    creds = flow.run_local_server(port=8091, prompt="consent")

    print("\n" + "=" * 60)
    print("SUCCESS — add this to measurement-platform/.env:")
    print(f"GOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 60)


if __name__ == "__main__":
    main()

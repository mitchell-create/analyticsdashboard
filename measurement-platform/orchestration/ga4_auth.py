"""
ga4_auth.py — One-time OAuth flow to get a refresh token for GA4 Data API.
Uses your Airbyte OAuth client credentials with a local redirect.

Usage:
    python ga4_auth.py

Saves credentials to ga4_user_credentials.json for use by ga4_sync.py.
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

# Use your existing Airbyte OAuth client (Web Application type)
# We configure it as an installed app flow with loopback redirect
CLIENT_CONFIG = {
    "installed": {
        "client_id": "267707809897-djd46ripcrin1t1q1p6uetf9rd1mjiv1.apps.googleusercontent.com",
        "client_secret": "",  # Will be filled from user input
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

def main():
    creds_path = Path(__file__).resolve().parent.parent / "ga4_user_credentials.json"

    # Check if credentials already exist
    if creds_path.exists():
        print(f"Credentials already exist at {creds_path}")
        print("Delete the file to re-authenticate.")
        return

    # Get client secret
    print("Enter your Google OAuth Client Secret")
    print("(from Google Cloud Console > APIs & Services > Credentials > Airbyte client)")
    secret = input("Client Secret: ").strip()
    if not secret:
        print("ERROR: Client secret is required")
        return

    CLIENT_CONFIG["installed"]["client_secret"] = secret

    # Run OAuth flow
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    creds = flow.run_local_server(port=8090, prompt="consent")

    # Save credentials
    creds_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }
    with open(creds_path, "w") as f:
        json.dump(creds_data, f, indent=2)

    print(f"\nCredentials saved to {creds_path}")
    print("You can now run ga4_sync.py")


if __name__ == "__main__":
    main()

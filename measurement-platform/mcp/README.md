# webloom Merchant MCP — local patch

We run [`webloom-agency/merchant-center-mcp`](https://github.com/webloom-agency/merchant-center-mcp)
**read-only (stdio)** on the dedicated PC to give OpenClaw read access to Google Merchant
Center (Expand `5551449022`, SecondKind `5685025649`). Two local fixes are required for our
single-scope OAuth credential + Merchant API v1; they're vendored here so the setup is
reproducible if that PC is rebuilt.

- **Base repo:** https://github.com/webloom-agency/merchant-center-mcp
- **Base commit:** `b2578bde8fe7c0bea4330911536c65b4d2079988`
- **Patch:** [`webloom-merchant-mcp.patch`](./webloom-merchant-mcp.patch)

## What it changes
1. **`auth/scopes.py`** — request only the `content` scope (drop the openid/userinfo
   `BASE_SCOPES`). Our credential is content-only, so requesting userinfo/openid causes
   `invalid_scope` on token refresh even though Merchant API calls succeed.
2. **`merchant_server.py`** — send an empty POST body on the issue-render endpoints
   (`render_account_issues` / `render_product_issues`). Merchant API v1 rejects the older
   `languageCode` / `timeZone` payload.

## Apply (on the dedicated PC)
```
git clone https://github.com/webloom-agency/merchant-center-mcp
cd merchant-center-mcp
git checkout b2578bde8fe7c0bea4330911536c65b4d2079988
git apply /path/to/measurement-platform/mcp/webloom-merchant-mcp.patch
```

## Run (read-only stdio)
Env: `GOOGLE_MERCHANT_AUTH_TYPE=oauth`,
`GOOGLE_MERCHANT_CREDENTIALS_PATH=<repo>/measurement-platform/merchant_user_credentials.json`,
`GOOGLE_MERCHANT_READ_ONLY=1` (also the default). Launch as stdio:
`fastmcp run merchant_server.py:mcp`. The credential is minted by
[`../orchestration/merchant_auth.py`](../orchestration/merchant_auth.py) and verified by
[`../orchestration/merchant_smoke.py`](../orchestration/merchant_smoke.py).

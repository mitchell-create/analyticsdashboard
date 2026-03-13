# Shopify + Airbyte Setup

How to connect Shopify stores to Airbyte when using **self-hosted Airbyte** and **Shopify Dev Dashboard apps** (post–Jan 2026). Legacy custom apps are deprecated; new apps use OAuth and must be created in the [Shopify Dev Dashboard](https://dev.shopify.com).

---

## Quick Reference: Per-Client Checklist

1. [ ] Develop app for client in Dev Dashboard
2. [ ] Configure Custom Distribution and generate install link
3. [ ] Client installs the app on their store
4. [ ] Get access token (authorize URL → code → PowerShell)
5. [ ] Add Shopify source in Airbyte with token; use unique stream prefix per store

---

## Step 1: Develop the App (Dev Dashboard)

1. Go to [dev.shopify.com](https://dev.shopify.com) → **Create app**.
2. Configure the app:
   - App name (e.g. "Client Name – Data Sync")
   - App URL: `https://example.com` or `http://localhost:8000`
   - Redirect URL: `http://localhost:8000/auth_flow`
   - Uncheck "Embed app"
   - Add required `read_*` scopes (see [Required scopes](#required-scopes) below)
3. Release the app version.

---

## Step 2: Custom Distribution — Generate Install Link

1. In Shopify Partners, go to **Apps** → **Distribution** → **All apps**.
2. Find the app you developed → select it.
3. Click **Choose Distribution** → **Custom Distribution**.
4. Add the store's **My Shopify domain** (e.g. `fzy1vz-2y.myshopify.com`).
5. Click **Generate link**.
6. Send the link to the client and ask them to **install the app** on their store.

---

## Step 3: Get the Access Token

### 3a. Build the Authorize URL

Use the client's **My Shopify domain** (the subdomain part, e.g. `fzy1vz-2y`) and the app's **Client ID** (from Dev Dashboard → app → Settings → Client credentials):

```
https://{store}.myshopify.com/admin/oauth/authorize?client_id={client_id}&redirect_uri=http://localhost:8000/auth_flow
```

**Example:**
```
https://fzy1vz-2y.myshopify.com/admin/oauth/authorize?client_id=57a7b99551a0130eedfe4152b08a9994&redirect_uri=http://localhost:8000/auth_flow
```

Open this URL in a browser. The redirect URI must match what you set when creating the app.

### 3b. Complete the OAuth Flow and Copy the Code

1. Log in to Shopify if prompted.
2. Approve the app permissions.
3. You'll be redirected to `http://localhost:8000/auth_flow?code=...&hmac=...&shop=...`
4. Copy the `code` value from the URL (the part after `code=` and before `&`).
   - If you see "Verifying your connection...", the code is still in the address bar or in the page source — copy it before the page changes.
5. The code expires in a few minutes; use it immediately.

### 3c. Exchange Code for Access Token (PowerShell)

Run this in PowerShell. Replace `{store}`, `{client_id}`, `{client_secret}`, and `{code}` with the actual values:

```powershell
$body = @{
    client_id     = "{client_id}"
    client_secret = "{client_secret}"
    code          = "{code}"
}

Invoke-RestMethod -Uri "https://{store}.myshopify.com/admin/oauth/access_token" `
    -Method POST `
    -ContentType "application/x-www-form-urlencoded" `
    -Body $body
```

**Example:**
```powershell
$body = @{
    client_id     = "57a7b99551a0130eedfe4152b08a9994"
    client_secret = "shpss_xxxxxxxxxxxxxxxxxxxxxxxx"
    code          = "caf4e8db8dfaa955e1c6ed157f2fb566"
}

Invoke-RestMethod -Uri "https://fzy1vz-2y.myshopify.com/admin/oauth/access_token" `
    -Method POST `
    -ContentType "application/x-www-form-urlencoded" `
    -Body $body
```

The output will include `access_token` (starts with `shpat_`). Copy it.

---

## Step 4: Use in Airbyte

1. Create a new **Shopify** source in Airbyte (or edit existing).
2. Select **API Password** (not OAuth).
3. Enter:
   - **Shopify Store name:** the subdomain (e.g. `fzy1vz-2y`)
   - **Admin API access token:** paste the `access_token` from Step 3c
4. Use a **unique stream prefix** per store (e.g. `shopify_fzy1vz2y_` or `shopify_clientname_`).
5. Save and test the connection.

---

## Token Expiration

Dev Dashboard tokens expire every 24 hours. When syncs fail, repeat **Step 3** (authorize URL → code → PowerShell) to get a new token, then update the Airbyte source.

---

## Required scopes

Enable these `read_*` scopes in the Dev Dashboard app:

```
read_analytics
read_assigned_fulfillment_orders
read_checkouts
read_content
read_customers
read_discounts
read_draft_orders
read_fulfillments
read_gdpr_data_request
read_gift_cards
read_inventory
read_legal_policies
read_locations
read_locales
read_marketing_events
read_merchant_managed_fulfillment_orders
read_online_store_pages
read_order_edits
read_orders
read_price_rules
read_product_listings
read_products
read_publications
read_reports
read_resource_feedbacks
read_script_tags
read_shipping
read_shopify_payments_accounts
read_shopify_payments_bank_accounts
read_shopify_payments_disputes
read_shopify_payments_payouts
read_themes
read_third_party_fulfillment_orders
read_translations
```

---

## One source per store

Create a separate Airbyte Shopify source for each store. Each store has its own API credentials and cannot share one connection.

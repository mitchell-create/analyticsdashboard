# SecondKind Bold (secondkind) — Report Memory

> Read before writing; append after. See §7 of `../../INSIGHTS_PLAYBOOK.md`.

## Standing context (durable — Mitchell owns this; fill/correct the TODOs)

- **Business:** SecondKind Bold — postbiotic gut-health supplement, DTC ecommerce, US-only. Revenue/purchase ≈ **$28** (from the Meta audit), so AOV is low — a key constraint on paid economics.
- **KPIs they care about:** _TODO._ Runs Meta + Google paid; Klaviyo email (purchaser + engager lists synced). 
- **Seasonality / cycles:** _TODO._
- **Structural events (dated):** Google **NonBrand Search launched ~2026-04-18** (young account, ~8 weeks old at audit time); Meta SCALE campaign hit a security/auth checkpoint mid-June.
- **Reporting quirks:** Google's reported ROAS runs high — trust GA4 site-side; GA4 revenue is a proxy, not Shopify.
- **Sensitivities / preferences:** _TODO._
- **Account IDs:** Meta `act_1304012668006975` · Google `4613815221` · GA4 `512135208`.

## Focus threads (what we're watching & why)

- [OPEN] **Conversion signal too thin for the algorithms** — Meta ~15–20 purchases/wk (Purchase EMQ 6.9, target ≥8.5); Google 2 conv/30d. Both starve Smart Bidding / Advantage+. Consolidate + feed signal before scaling. Since 2026-06-15.
- [OPEN] **Post-click economics (Meta)** — ROAS ≈ 0.21–0.24 despite a strong 2.4% CTR; ~$133 cost/purchase vs ~$28 revenue/purchase. The leak is offer / AOV / landing page, **not** Meta delivery (creative scored 84). Raise AOV (bundles/subscription) + message-match the LP. Since 2026-06-15.
- [OPEN] **Account hygiene** — Meta: 22 campaigns / 82 ad sets (sprawl), **no Lookalikes** despite Klaviyo purchaser seeds, purchaser-exclusion unconfirmed. Google: brand bleeding into NonBrand, the only converting campaign budget-capped at $10/day, no image extensions / Customer Match / placement exclusions. Since 2026-06-15.

## Report log (newest first)

### 2026-06-15 — full claude-ads audit (Meta + Google)
- **Health:** Meta **76/100 (B)**, Google **70/100 (C)**. Full check-by-check PDF + markdown at `C:\Users\ReadyPlayerOne\ad-audits\secondkind\`.
- **Story we told:** young, low-volume account with solid creative + tracking foundations, but conversion signal too thin and structural clutter holding it back. **CRITICAL (Meta):** account had a "please authenticate your account" security checkpoint freezing the scale campaign — clear it first.
- **Top fixes:** Meta — clear the auth checkpoint, build 1/3/5% Lookalikes off Klaviyo purchasers, merge duplicate prospecting ad sets, lift Purchase EMQ, fix post-click economics before scaling. Google — enable Enhanced Conversions (free ~10% signal), add brand negatives (stop brand bleed), raise the budget-capped NonBrand (fund from the 0-conv Display/Shopping), switch Brand off Target-Impression-Share (bid-capped at $1.50).
- **Causes cited:** internal — thin signal, structural sprawl, settings drag [confirmed]; external — none checked.
- **Follow-ups:** re-audit after the cleanup; track ROAS + EMQ + the budget reallocation.

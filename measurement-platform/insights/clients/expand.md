# Expand (expand) — Report Memory

> Read before writing; append after. See §7 of `../../INSIGHTS_PLAYBOOK.md`.

## Standing context (durable — Mitchell owns this; fill/correct the TODOs)

- **Business:** _TODO (Mitchell): what Expand sells, to whom, rough AOV._ High revenue volume (GA4 ~$1M+/month).
- **KPIs they care about:** _TODO._ Runs Meta + Google paid; Klaviyo email is a meaningful revenue channel.
- **Seasonality / cycles:** _TODO._
- **Structural events (dated):** _TODO (any recent launches, promos, price/site/checkout changes)._
- **Reporting quirks:**
  - Google's *reported* ROAS runs ~14x, but GA4 site-side credits Google ~3.6x — **always report the GA4-confirmed figure**, treat Google's as platform-inflated.
  - GA4 revenue is a proxy, not Shopify orders.
- **Sensitivities / preferences:** _TODO._

## Focus threads (what we're actively watching & why)

- [OPEN] **Meta CPM (30-day)** — up ~23% with flat CTR; watching whether it's auction/seasonal pressure (market) vs a relevance slip (us). Run the §4.2 portfolio check: is CPM up across all clients? Since 2026-06-14.
- [OPEN] **Google attribution gap** — Google claims ~14x, GA4 says ~3.6x. Budget on the GA4 figure; watch whether the gap widens. Since 2026-06-14.
- [OPEN] **Site revenue + email attribution** — a w/w read showed a big drop (revenue −39%, email →~$0) that looked like incomplete recent data. Confirm on settled data before treating as real. Since 2026-06-14.
- [OPEN] **Creative: carousels win, DIRECT-gendered videos leak** — Carousel "Dynamic" sale ads carry ROAS with healthy 3–6% ATC; the EXF09 "Pratico/Junior Giant DIRECT FEMALE/Male" videos pull high CTR (6–8%) but ATC craters to 0.3–0.4% (clicks don't convert — hook vs offer/LP mismatch). Pause sub-1x video ads; investigate the landing experience for the DIRECT video traffic. Since 2026-06-15.

## Report log (newest first)

### 2026-06-14 — last 7d vs prior 7d (+ 30d) — calibration run on UNSETTLED window
- **Focused on:** Meta CPM/CTR/frequency, Google ROAS vs GA4, site revenue + checkout funnel.
- **Story we told:** Meta steady this week but pricier over 30d; Google efficient in-platform but trust GA4's ~3.6x over Google's ~14x; site revenue drop most likely a data-completeness artifact, not a real collapse.
- **Causes cited:** internal — possible auction pressure (Meta CPM), attribution overcount (Google) [likely]; external — none checked yet. Revenue drop tagged [likely artifact].
- **Follow-ups:** re-run on settled data (`:asof = current_date − 2`); if the revenue drop survives, walk the checkout funnel; run the §4.2 portfolio check on Meta CPM across all clients.

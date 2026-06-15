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
- [OPEN] **Creative: the leak is post-click on video, not attention** — Confirmed on the settled 2026-05-16→06-13 window. By type: **carousel ~70x ROAS at 3.3% ATC** on ~$5.5k spend vs **video ~8.9x at 0.6% ATC** on ~$11k (2x the budget into the weaker channel). Video hooks/hold are often *fine* — e.g. the Compatto repost has hook 39% / hold 31% — but ATC is ~0%, so the problem is what happens **after the click** (landing-page match / audience qualification), not the creative grabbing attention. Action: shift budget toward carousels; for video, fix the post-click experience before pushing more spend; pause the 0x video ads. Since 2026-06-15.

## Report log (newest first)

### 2026-06-14 — last 7d vs prior 7d (+ 30d) — calibration run on UNSETTLED window
- **Focused on:** Meta CPM/CTR/frequency, Google ROAS vs GA4, site revenue + checkout funnel.
- **Story we told:** Meta steady this week but pricier over 30d; Google efficient in-platform but trust GA4's ~3.6x over Google's ~14x; site revenue drop most likely a data-completeness artifact, not a real collapse.
- **Causes cited:** internal — possible auction pressure (Meta CPM), attribution overcount (Google) [likely]; external — none checked yet. Revenue drop tagged [likely artifact].
- **Follow-ups:** re-run on settled data (`:asof = current_date − 2`); if the revenue drop survives, walk the checkout funnel; run the §4.2 portfolio check on Meta CPM across all clients.

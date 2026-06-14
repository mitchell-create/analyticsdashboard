# Insights Playbook — Weekly Performance Diagnosis

> A reusable skill for analyzing client marketing performance. When asked to
> "analyze <client> last week" (or any period), follow this playbook: pull the
> comparison, apply the diagnostic rules, and write a prioritized, specific,
> *causal* read — never a stat dump. Used on-demand by Codex / the Slack bot;
> the same logic will back the automated weekly post when that's enabled.

The goal is the difference between **"Meta spend was up 18%"** (useless) and
**"Meta CTR fell 24% w/w while frequency climbed to 3.4 — classic creative
fatigue; refresh the top-spending ad sets before scaling further"** (actionable).

---

## 1. Data sources (warehouse: local Postgres, schema `public_marts` + `raw`)

| Need | Table | Key columns |
|---|---|---|
| Paid spend / reach (all channels) | `public_marts.fact_spend_daily` | client_slug, report_date, channel, spend, impressions, clicks |
| **Meta** rich metrics | `raw.meta_customaccount_insights_daily` | account_id, date_start, spend, impressions, inline_link_clicks, reach, frequency, ctr, cpc, cpm, actions (jsonb), action_values (jsonb) |
| Revenue + funnel (GA4) | `public_marts.fact_ga4_funnel_daily` | client_slug, report_date, sessions, product_views, add_to_carts, checkouts, purchases, purchase_revenue, bounce_rate, session_to_atc_rate, atc_to_checkout_rate, checkout_to_purchase_rate, overall_conversion_rate |
| Traffic by source/medium | `public_marts.fact_ga4_traffic_daily` | client_slug, report_date, source, medium, sessions, … |
| Email | `public_marts.fact_klaviyo_daily` | client_slug, report_date, … |
| Account → client map | `public_marts.client_ad_accounts` (or the seed) | client_slug, platform, account_id |

**Caveats to state honestly in any analysis:**
- **Revenue is GA4 purchase events**, not Shopify orders — a directional signal, not penny-accurate. Good for trends, not finance.
- **Google** has conversions + value in `raw.google_account_performance_report` (`metrics_conversions`, `metrics_conversions_value`) → Google ROAS = conversions_value / spend. Populated by `google_ads_sync.py` from 2026-06-14 on; older rows may be NULL, so date-bound your queries. **Both Meta and Google ROAS are platform-self-attributed and run HIGH** (last-click/data-driven, double-counting across channels — e.g. Google may claim 14x while the site's blended MER is ~3x). Always cross-check a platform ROAS against GA4 `purchase_revenue` and the blended MER before reporting it as truth; describe it as "Google-reported ROAS," and lean on **directional change** (ROAS down 30% w/w) over the absolute number.
- **chubble** has no GA4 property → no revenue/funnel signal for it.
- Meta ROAS uses `action_values → omni_purchase` (platform-attributed), which overcounts vs. true incrementality.

---

## 2. Core metrics & formulas

```
CTR   = clicks / impressions
CPM   = spend / impressions * 1000
CPC   = spend / clicks
Freq  = impressions / reach            (Meta only, from raw table)
ROAS  = conversion_value / spend       (Meta: omni_purchase value; Google: metrics_conversions_value)
MER   = GA4 purchase_revenue / total ad spend   (blended efficiency)
Conv-rate = purchases / sessions       (GA4 overall_conversion_rate)
```

Always compute **per channel** (meta/google/tiktok), then a **blended** view.

---

## 3. The comparison query (copy-paste, parameterized)

Set `:client` and `:asof` (default `current_date`). This gives current-vs-prior
for both a 7-day and 30-day window in one shot.

```sql
-- Paid metrics: current vs prior, 7d and 30d, per channel
with spend as (
  select channel, report_date, spend, impressions, clicks
  from public_marts.fact_spend_daily
  where client_slug = :client and report_date > :asof - 60
),
windowed as (
  select channel,
    case
      when report_date >  :asof - 7  then 'cur_7'
      when report_date >  :asof - 14 then 'prev_7'
    end as w7,
    case
      when report_date >  :asof - 30 then 'cur_30'
      when report_date >  :asof - 60 then 'prev_30'
    end as w30,
    spend, impressions, clicks
  from spend
)
select channel, bucket,
  round(sum(spend),2) spend, sum(impressions) impr, sum(clicks) clicks,
  round(sum(clicks)::numeric / nullif(sum(impressions),0) * 100, 2) ctr_pct,
  round(sum(spend) / nullif(sum(impressions),0) * 1000, 2) cpm,
  round(sum(spend) / nullif(sum(clicks),0), 2) cpc
from windowed, lateral (values (w7),(w30)) b(bucket)
where bucket is not null
group by channel, bucket
order by channel, bucket;
```

Then compute `% change = (cur - prev) / prev` for each metric, per channel.

**Meta frequency + ROAS** (the fatigue/efficiency signals) come from the raw table:

```sql
select
  case when d.date_start > :asof - 7 then 'cur_7' when d.date_start > :asof - 14 then 'prev_7' end as bucket,
  round(avg(d.frequency),2) avg_freq,
  round(sum(d.spend),2) spend,
  round(sum( (select coalesce(sum((a->>'value')::numeric),0)
             from jsonb_array_elements(d.action_values) a
             where a->>'action_type' = 'omni_purchase') ), 2) as conv_value
from raw.meta_customaccount_insights_daily d
join public_marts.client_ad_accounts c on d.account_id = c.account_id
where c.client_slug = :client and c.platform='meta' and d.date_start > :asof - 14
group by 1 having case when d.date_start > :asof - 7 then 'cur_7' when d.date_start > :asof - 14 then 'prev_7' end is not null;
```

**Google conversions + ROAS** (from the raw Google table):

```sql
select
  case when segments_date > :asof - 7 then 'cur_7' when segments_date > :asof - 14 then 'prev_7' end as bucket,
  round(sum(metrics_cost_micros)/1e6, 2) spend,
  round(sum(metrics_conversions), 1) conversions,
  round(sum(metrics_conversions_value), 2) conv_value,
  round(sum(metrics_conversions_value) / nullif(sum(metrics_cost_micros)/1e6, 0), 2) roas
from raw.google_account_performance_report d
join public_marts.client_ad_accounts c on d.customer_id::text = c.account_id
where c.client_slug = :client and c.platform='google' and segments_date > :asof - 14
group by 1 having case when segments_date > :asof - 7 then 'cur_7' when segments_date > :asof - 14 then 'prev_7' end is not null;
```

**GA4 funnel** (where conversions break):

```sql
select
  case when report_date > :asof - 7 then 'cur_7' when report_date > :asof - 14 then 'prev_7' end bucket,
  sum(sessions) sessions, sum(add_to_carts) atc, sum(checkouts) checkouts, sum(purchases) purch,
  round(sum(purchase_revenue),2) revenue,
  round(avg(overall_conversion_rate)*100,2) cvr_pct,
  round(avg(atc_to_checkout_rate)*100,2) atc_to_co_pct,
  round(avg(checkout_to_purchase_rate)*100,2) co_to_purch_pct,
  round(avg(bounce_rate)*100,2) bounce_pct
from public_marts.fact_ga4_funnel_daily
where client_slug = :client and report_date > :asof - 14
group by 1 having case when report_date > :asof - 7 then 'cur_7' when report_date > :asof - 14 then 'prev_7' end is not null;
```

---

## 4. Diagnostic ruleset (signal → likely cause)

Apply after computing % changes. Thresholds are defaults — tune per client.

| Pattern (vs prior period) | Diagnosis | Recommended action |
|---|---|---|
| CTR ↓ >15% **and** frequency ↑ (or >2.5–3) | **Creative fatigue** | Refresh creative/angles on top-spend ad sets before scaling |
| CPM ↑ >20%, CTR ~flat | **Auction pressure** (competition/seasonality) or audience too narrow | Broaden audience; check seasonal benchmarks; don't panic-cut |
| CPC ↑ >15% but CTR steady | Cost is CPM-driven, **not relevance** | Address CPM (audience/placement), not creative |
| ROAS ↓ >20% **and** spend ↑ >15% | **Scaling past the efficient frontier** | Pull back to the spend level where ROAS held; scale slower |
| Conv-rate ↓ >20%, sessions steady | **Site / offer / tracking** issue, not traffic | Check LP, promo expiry, pixel/GA4 tagging |
| `atc_to_checkout` or `checkout_to_purchase` ↓ | **Funnel-stage friction** (cart/checkout/shipping) | Audit that exact step — shipping cost, checkout bugs, payment |
| Spend ↓ unexpectedly | Budget pacing / delivery throttle / disapprovals | Check budgets, ad approvals, payment method |
| Bounce ↑ + sessions ↑ from one source | **Low-quality traffic** spike | Inspect `fact_ga4_traffic_daily` by source/medium |
| Revenue (GA4) ↓ vs spend flat/up | **MER erosion** | Blended efficiency declining — investigate by channel |
| Impressions ↓ + CPM ↓ | Delivery pulling back (low competition or low bids) | Often fine; confirm budgets aren't capped |

**Compound signals beat single metrics.** "CTR down" alone is noise; "CTR down + frequency up + CPM flat" is a diagnosis. Always look for the *combination*.

---

## 5. How to write the insight (the part that makes it good)

1. **Lead with the verdict, per channel.** One sentence: what happened and what it means. ("Meta is fatiguing; Google is stable but pricier.")
2. **Quantify with the specific delta.** "CTR 1.9% → 1.4% (-24% w/w)" beats "CTR dropped."
3. **Name the likely cause** from the ruleset — and your confidence. Don't assert; reason. ("Frequency rose to 3.4, so this reads as fatigue rather than audience change.")
4. **One concrete next action** per finding. Prioritized — the biggest $ impact first.
5. **Note what you can't see.** If Google ROAS is unavailable or GA4 revenue is the proxy, say so. Don't imply precision you don't have.
6. **Length:** 3–6 bullets per client. Skip channels that were boringly stable (just note "stable").

**Bad:** "Spend was $4,200, up 18%. Impressions 1.2M. Clicks 9,400. CTR 0.78%."
**Good:** ":red_circle: *Meta — creative fatigue.* CTR 1.9%→1.4% (-24% w/w) while frequency hit 3.4 and CPM held flat — the audience is over-served, not more expensive. Spend rose 18% into declining efficiency (ROAS 3.1→2.4). *Refresh creative on the top-2 ad sets before adding budget.*"

---

## 6. Period options

- **Weekly review (default):** last 7d vs prior 7d, `:asof = current_date`.
- **Smoothed/trend:** last 30d vs prior 30d (less noise, catches slow drifts).
- **Custom:** set `:asof` to any date to analyze a past week (e.g. `:asof = '2026-06-08'`).
- Use **both 7d and 30d** when they disagree — a 7d dip inside a healthy 30d trend is often noise; a 30d decline is structural.

---

## 7. Extensions (not built yet)

- Materialize a `vw_metrics_comparison` view for speed/consistency.
- Auto-post: wrap this in a Prefect flow that runs after the weekly sync and posts per-client to Slack (deferred by choice — on-demand for now).

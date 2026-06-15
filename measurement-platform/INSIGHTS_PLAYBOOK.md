# Insights Playbook — Weekly Performance Diagnosis

> A reusable skill for analyzing client marketing performance. When asked to
> "analyze <client> last week" (or any period), follow this playbook: pull the
> comparison, apply the diagnostic rules, and write a prioritized, specific,
> *causal* read — never a stat dump. Used on-demand by Codex / the Slack bot;
> the same logic will back the automated weekly post when that's enabled.

The goal is the difference between **"Meta spend was up 18%"** (useless) and
**"Meta's ads are wearing out — people have seen them too many times, so clicks
dropped 24%. Refresh the top 2 ad sets before spending more."** (actionable, and
a human can skim it).

---

## 0. Before you diagnose — check data completeness (READ FIRST)

Sources lag. **GA4 processes data with a 24–48h delay**, so the most recent 1–2
days are *incomplete*, and the warehouse only holds what the last sync captured.
If your window includes those trailing days, **every metric looks like it
dropped** — revenue, sessions, email/social attribution — purely from missing
data, not a real decline. This is the #1 cause of false alarms.

Also **read the client's memory file** (`insights/clients/<slug>.md`, see §7)
before you start — it carries the standing context and the threads we said we'd
watch, so each report builds on the last instead of starting cold.

Two rules:
1. **Analyze complete periods.** Default `:asof = current_date - 2` so "this
   week" is the last 7 *fully-settled* days. State the exact dates you used.
2. **A metric that collapses to ~0 or drops >50% in a week is a data-completeness
   suspect first, a business event second.** Before diagnosing ("email revenue
   cratered"), confirm the source has complete rows for the period — check
   `max(report_date)` and per-day row counts. Only call it real once the data is
   confirmed complete. Klaviyo/GA4-attributed channel revenue is especially
   prone to this.

```sql
-- Completeness probe: run before any analysis. Look for a clean daily cadence
-- up to (:asof) and flag the last settled date per source.
select 'ga4'  src, max(report_date) last_day, count(distinct report_date) days
  from public_marts.fact_ga4_funnel_daily where client_slug = :client and report_date > :asof - 14
union all select 'spend', max(report_date), count(distinct report_date)
  from public_marts.fact_spend_daily     where client_slug = :client and report_date > :asof - 14
union all select 'klaviyo', max(report_date), count(distinct report_date)
  from public_marts.fact_klaviyo_daily   where client_slug = :client and report_date > :asof - 14;
```

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

## 4.1 Drill down to root cause (the why behind the why)

§4 gives the *first* layer. Don't stop there — ask "why" 2–3 times until you hit
something **actionable** (a lever we can pull) or **external** (a market force). A
client doesn't want "CPM is up"; they want *why* it's up and whether it's on us or
the market.

Walk the chain. Example ladders:

- **CPM up** → it costs more to reach the same people → *why?* → either **(a)** our
  engagement/relevance slipped (CTR soft, more people scrolling past) so the
  auction charges us more, or **(b)** the auction itself got hotter — seasonal or
  competitive, everyone's CPM is up. (a) is on us; (b) is the market → §4.2.
- **CTR down** → fewer people clicking → *why?* → **creative fatigue** (frequency
  climbing, same ads running for weeks), **wrong audience** (recently widened or
  changed), or **weaker offer/hook**. Check frequency, how long the creatives have
  run, and any recent audience edits.
- **Conversion rate down, traffic steady** → people arrive but don't buy → *why?*
  → **site/offer** (price, a promo ended, shipping, checkout bug, out-of-stock) or
  **market demand softening** (→ §4.2). Walk the funnel (§3 GA4 query) to find
  *which step* leaks: view→ATC (interest/price), ATC→checkout (cart/shipping),
  checkout→purchase (payment/trust).
- **ROAS down while spend up** → each new dollar buys less → *why?* → scaled past
  the efficient audience (costs climb as you push volume), creative can't carry
  the bigger budget, or tracking lost some conversions.

End every chain at one of two things:
1. **An internal lever** — creative, audience, budget, bid, funnel, offer,
   tracking. Name the specific action.
2. **An external factor** — seasonality, demand, category trend, platform/policy
   change, competition. **Verify it in §4.2 before stating it.**

State confidence honestly: "frequency is 3.4 and these creatives have run 6 weeks,
so fatigue is **likely**" — not just "fatigue."

---

## 4.2 Is it you or the market? (external context)

The most valuable thing you can tell a client is whether a move is **their problem
or everyone's.** "Your conversion rate fell 15%" panics them. "Your conversion
rate fell 15%, but ecommerce conversion is down ~10% across the board this quarter
([source]) — so most of this is the market; the extra 5% is what we're chasing"
informs them.

**When to look outward:** a metric moved materially **and** the internal data
doesn't fully explain it (funnel rates flat but revenue down; CPM up everywhere;
CVR down with no site change). If an internal cause fully explains it, skip this.

**How to check — in order of trust:**
1. **Your own portfolio first.** Is this happening across *several* clients at
   once? If every account's CPM jumped this week, it's the auction/season, not
   their creative. Six clients = a built-in control group. This is your strongest,
   cheapest signal — use it before the web.
2. **Platform benchmark tools**, if available to you (e.g. Meta's industry-
   benchmark / performance-trend endpoints) — category-level CPM/CTR/CVR trends.
3. **The web.** Search category + metric + timeframe: "ecommerce conversion rate
   trend Q2 2026", "Meta CPM increase June 2026", consumer-confidence / retail-
   spending headlines, platform policy or algorithm changes, seasonal effects
   (holidays, back-to-school, weather).

**Rigor — don't hand-wave a macro story:**
- **Cite the source + date.** No source → it's a hypothesis, not a fact; say so.
- **Quantify if you can.** "Industry CVR down ~10% ([source])" beats "things are soft."
- **Prefer the portfolio check** — your own clients are the cleanest benchmark.
- **If you find nothing, say so:** "no clear market driver found — looks
  client-specific." Never invent "economic uncertainty" to fill space.
- **Tag every external cause** [confirmed] / [likely] / [hypothesis].

---

## 4.3 Creative analysis (Meta ad-level): what's working, and why

Account-level metrics tell you *that* Meta moved; **ad-level** tells you *which
creative* moved it. Data: `raw.meta_ad_insights_daily` (per ad, per day, from
`meta_creative_sync.py`) → tagged with `creative_type` + `creative_key` by
`stg_meta_ad_creative` → `fact_creative_daily`.

**A creative is a funnel.** Each metric isolates one stage, so the panel *is* the
diagnosis — find the stage where it leaks:

| Stage | Metric | Formula | A weak number here means |
|---|---|---|---|
| Stop the scroll | **Hook rate** | 3-sec views ÷ impressions | weak opening (first frame / first line) |
| Keep watching | **Hold rate** | ThruPlay ÷ impressions | the body loses them after the hook |
| Create interest | **Link CTR** | link clicks ÷ impressions | angle / offer / CTA isn't compelling |
| Cost of reach | **CPM** | spend ÷ impressions × 1000 | relevance down, or auction up (→ §4.2) |
| Cost of a click | **Link CPC** | spend ÷ link clicks | (falls out of CTR + CPM) |
| Wearing out | **Frequency** | impressions ÷ reach | rising + CTR falling = fatigue |
| Intent | **ATC rate** | add-to-cart ÷ link clicks | clicks aren't qualified / LP mismatch |
| Resonance | **Engagement rate** | post_engagement ÷ impressions | creative isn't landing |
| Efficiency | **CPA** | spend ÷ purchases | — |
| Return | **ROAS** | purchase value ÷ spend | the bottom line |

(ATC / purchases / engagement come out of the `actions` + `action_values` jsonb —
same `jsonb_array_elements` pattern as the omni_purchase query in §3.)

**Read the combination, not one number** — that's where the "why" is:
- High hook, low hold → the opening over-promises; the body/payoff is weak.
- High hook + hold, low CTR → great video, weak ask — fix the CTA/offer, not the hook.
- High CTR, low ATC/ROAS → the click is unqualified or the landing page doesn't match the ad's promise.
- Good everything, but ROAS sliding while frequency climbs → **fatigue**: it worked, now it's over-shown. Refresh it.

**Group by the creative, then rank — don't decode the name's meaning.** Names are
too inconsistent across clients to reliably extract "angle" or "hook." So:
- **By `creative_key`** — the ad name with "Copy / Copy 2" variants collapsed into
  one row. Rank these by the panel: the top rows are your best creatives. You don't
  need to know *what* the creative is — just that it wins, and where it's weak.
- **By `creative_type`** (video / image / carousel) — the one clean cut that always
  works; which format the audience responds to.
- For each winner, the panel names the fix: strong everywhere but weak hold rate →
  recut the middle to hold attention. (If a client adopts the 11-field convention,
  `angle` / `persona` / `hook` light up and you can additionally group by those.)

**Rules that keep it honest:**
- **Minimum spend before you crown a winner.** Don't rank a creative on $30 / 2 purchases — set a floor (e.g. ≥ $200 spend or ≥ 5 purchases) and label anything below it "not enough data."
- **Compare like with like** — settled window (§0), and same objective (a prospecting ad and a retargeting ad aren't peers).
- **Separate "new & unproven" from "tested & losing."** A 3-day-old ad with thin data isn't a loser yet.

**Queries** (from `fact_creative_daily` — group by the creative, rank by the panel):

```sql
-- 1) Which CREATIVE wins — variants grouped (creative_key), ranked by ROAS, with
--    each one's WEAKEST funnel stage flagged (its iteration lever).
with c as (
  select creative_key, max(creative_type) creative_type,
    sum(spend) spend, sum(impressions) impr, sum(link_clicks) lc,
    sum(video_3s_views) v3s, sum(video_thruplays) thru,
    sum(add_to_cart) atc, sum(purchases) pur, sum(conversion_value) cv
  from public_marts.fact_creative_daily
  where client_slug = :client and report_date between :asof - 30 and :asof - 2
  group by creative_key
  having sum(spend) >= 200                       -- significance floor; tune per client
),
r as (                                           -- rate panel per creative
  select *,
    lc::numeric/nullif(impr,0)   ctr,
    v3s::numeric/nullif(impr,0)  hook,
    thru::numeric/nullif(impr,0) hold,
    atc::numeric/nullif(lc,0)    atc_rate,
    cv/nullif(spend,0)           roas
  from c
),
p as (                                           -- rank on each stage (hook/hold: video only)
  select *,
    percent_rank() over (order by ctr)                                                ctr_pr,
    case when v3s > 0 then percent_rank() over (partition by (v3s>0) order by hook) end hook_pr,
    case when v3s > 0 then percent_rank() over (partition by (v3s>0) order by hold) end hold_pr,
    percent_rank() over (order by atc_rate)                                           atc_pr
  from r
)
select creative_key, creative_type,
  round(spend,2) spend, round(roas,2) roas,
  round(ctr*100,2) ctr_pct, round(hook*100,1) hook_pct,
  round(hold*100,1) hold_pct, round(atc_rate*100,1) atc_pct,
  case least(ctr_pr, hook_pr, hold_pr, atc_pr)   -- lowest percentile = the lever
    when ctr_pr  then 'link CTR (offer / CTA)'
    when hook_pr then 'hook (opening)'
    when hold_pr then 'hold (retention)'
    when atc_pr  then 'ATC (click quality / LP)'
  end as weakest_stage
from p
order by roas desc nulls last;

-- 2) Which TYPE wins — the always-reliable cut (video vs image vs carousel)
select creative_type,
  round(sum(spend),2)                                              spend,
  round(sum(link_clicks)::numeric/nullif(sum(impressions),0)*100,2) link_ctr_pct,
  round(sum(add_to_cart)::numeric/nullif(sum(link_clicks),0)*100,1) atc_rate_pct,
  round(sum(spend)/nullif(sum(purchases),0),2)                     cpa,
  round(sum(conversion_value)/nullif(sum(spend),0),2)            roas
from public_marts.fact_creative_daily
where client_slug = :client and report_date between :asof - 30 and :asof - 2
group by creative_type
order by roas desc nulls last;
```

(`weakest_stage` is roughest with few creatives or thin video data — read it as a
nudge, not gospel. Hook/hold only apply to video.)

For **fatigue**, trend a winning creative's hook / link-CTR rate and `frequency` by
week — one whose hook rate decays as frequency climbs is due for a refresh.

> **How names are read** (`stg_meta_ad_creative`): we don't decode meaning. Every ad
> gets a `creative_type` (video/image/carousel, by keyword) and a `creative_key`
> (the name with "Copy / Copy N" variants stripped, so a creative's variants group
> into one row). That ranks creatives + finds each one's weak stage on ANY client's
> naming style. If a client adopts the 11-field convention (`name_scheme =
> 'convention'`), the positional dims — `angle`, `persona`, `hook`, `offer` —
> populate too, and you can additionally group by those.

---

## 5. How to write the insight (the part that makes it good)

Write it to be **skimmed in 15 seconds.** Plain English, short lines, bullets —
not dense paragraphs. A reader should get the whole story from the **bold headers
alone**, then drop into the bullets only if they want the detail.

**Format — one short block per channel, biggest-$ channel first:**

> **`<emoji>` `<Channel>` — `<plain-English verdict, 4–7 words>`**
> - **What changed:** the key number + its delta. `CTR 1.9% → 1.4% (down 24%)`.
> - **Why:** the cause in everyday words (see the translations below).
> - **Do:** one concrete next step.

**Rules:**
1. **Put the verdict in the header.** Someone reading only the bold lines should
   still get it: *"Meta — steady but getting pricier"*, *"Site — fewer sales,
   worth a look."*
2. **Translate the jargon — keep the number, gloss the meaning:**
   - *creative fatigue* → "people have seen these ads too many times"
   - *CPM up / auction pressure* → "it costs more to reach the same people"
   - *frequency 3.4* → "each person's seen the ad ~3 times"
   - *past the efficient frontier* → "spending past the point where it pays back"
   - *MER* → "total sales ÷ total ad spend"
   - *ROAS* → "sales per $1 of ad spend"
   - *conversion rate* → "share of visitors who buy"
3. **One number per bullet, not five.** `CPM up 23%` beats dumping
   spend+impressions+clicks+CTR+CPC in a row.
4. **Short sentences.** If a bullet runs past ~2 lines, split it.
5. **Flag confidence + what you can't see.** "GA4 revenue is a proxy, not Shopify";
   "this may be incomplete recent data — verify before acting."
6. **Skip the boring.** A stable channel gets one line: *"Google — stable, nothing
   to do."* Don't pad.
7. **Length:** 2–4 bullets per channel; a whole-client read fits on a phone screen.

**Bad (dense, jargony, can't skim):**
> "Meta spend was $4,200, up 18%, with CTR at 0.78% and frequency at 3.4 against a
> CPM that held flat, indicating creative fatigue as efficiency declined to a 2.4
> ROAS from 3.1."

**Good (skimmable, plain, bulleted):**
> **:red_circle: Meta — ads are wearing out**
> - **What changed:** clicks-per-view down 24% (1.9% → 1.4%); sales per ad-$ down to 2.4 from 3.1.
> - **Why:** each person has now seen these ads ~3.4 times — they're tuning them out, *not* costing more to reach (cost-per-1,000-views held flat).
> - **Do:** refresh the creative on your 2 top-spending ad sets before adding budget.

---

## 6. Period options

- **Weekly review (default):** last 7d vs prior 7d, `:asof = current_date - 2` (skip GA4's incomplete trailing 1–2 days; see §0). Don't default to `current_date` or the latest days will read as a false drop.
- **Smoothed/trend:** last 30d vs prior 30d (less noise, catches slow drifts).
- **Custom:** set `:asof` to any date to analyze a past week (e.g. `:asof = '2026-06-08'`).
- Use **both 7d and 30d** when they disagree — a 7d dip inside a healthy 30d trend is often noise; a 30d decline is structural.

---

## 7. Client memory — continuity across reports

Each client has a memory file: `measurement-platform/insights/clients/<slug>.md`
(built from `_TEMPLATE.md`). **Read it before writing; append after.** This is how
reports build on each other instead of restarting every time — so you can say "the
checkout drop we flagged last month recovered" instead of re-finding it.

**Before** — read the file for:
- **Standing context** — the business, the KPIs they fixate on (especially which
  *conversion* metrics), seasonality, past events, reporting quirks, sensitivities.
- **Focus threads** — what we said we'd watch, and why. Check what happened to each
  (did the CPM creep continue? did the creative refresh work?).

**During** — use it for continuity: reference open threads, confirm or revise past
causes ("we guessed fatigue last month; the refresh lifted CTR back to 1.8%, so
that was right"), and respect sensitivities (if they care most about new-customer
ROAS, lead with it).

**After** — append a dated log entry: what you focused on, the story you told, the
causes you cited (internal + external, with confidence), follow-ups for next time.
Move closed threads to [RESOLVED].

Mitchell owns the **standing context** (the durable business facts). The **threads
+ log accrue automatically** as reports run. No file yet for a client? Create one
from `_TEMPLATE.md`.

---

## 8. Extensions (not built yet)

- Materialize a `vw_metrics_comparison` view for speed/consistency.
- Auto-post: wrap this in a Prefect flow that runs after the weekly sync and posts per-client to Slack (deferred by choice — on-demand for now).

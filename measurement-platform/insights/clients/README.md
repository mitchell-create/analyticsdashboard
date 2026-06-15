# Client report memory

One markdown file per client (`<slug>.md`), built from [`_TEMPLATE.md`](_TEMPLATE.md).
The insights process **reads a client's file before writing their report and
appends a dated entry after** — see §7 of [`../../INSIGHTS_PLAYBOOK.md`](../../INSIGHTS_PLAYBOOK.md).

This is what gives reports continuity: instead of re-discovering issues every time,
we carry forward *what we're watching and why*, and check what happened to it.

## What's in each file

- **Standing context** — durable business facts (what they sell, KPIs they care
  about, seasonality, past events, sensitivities). **Mitchell owns this** — it's
  the part the AI can't infer. Fill it in; correct it as things change.
- **Focus threads** — the metrics we've said we'd watch, and why. Accrue/resolve
  automatically as reports run.
- **Report log** — a dated entry per report: what we focused on, the story we
  told, the causes we cited (with confidence), follow-ups. Append-only.

## Notes

- Memory **starts accruing now** — past (pre-system) reports aren't here. If a
  client has important history ("we've been fighting CPM creep since the spring"),
  drop it into Standing context or Focus threads so it carries forward.
- **Safe to commit.** Narrative only — no tokens, no PII, no credentials.
- If a client has no file yet, create one from `_TEMPLATE.md`.

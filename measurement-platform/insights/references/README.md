# Diagnostic reference library

Senior-level platform diagnostic concepts that back the "why" layer of the
[INSIGHTS_PLAYBOOK](../../INSIGHTS_PLAYBOOK.md). Pull these in when a metric move
needs platform-specific reasoning.

## Google
- [google_quality_score.md](google_quality_score.md) — the 3 QS components + component-level diagnosis
- [google_impression_share.md](google_impression_share.md) — lost IS: **budget vs rank** (and why more budget won't help a rank problem)
- [google_smart_bidding.md](google_smart_bidding.md) — strategies, learning periods, when to intervene vs leave alone

## Meta
- [meta_breakdown_effect.md](meta_breakdown_effect.md) — why "budget went to the higher-CPA segment" is usually correct (**marginal** vs average efficiency)
- [meta_auction_overlap.md](meta_auction_overlap.md) — self-competition across overlapping ad sets
- [meta_learning_phase.md](meta_learning_phase.md) — don't judge (or edit) an ad set mid-learning
- [meta_ad_relevance_diagnostics.md](meta_ad_relevance_diagnostics.md) — quality / engagement / conversion rankings

## Attribution

These docs are reused verbatim from the MIT-licensed reference sets in:
- [mathiaschu/google-ads-analyzer](https://github.com/mathiaschu/google-ads-analyzer)
- [mathiaschu/meta-ads-analyzer](https://github.com/mathiaschu/meta-ads-analyzer)

> MIT License — Copyright (c) 2026 Mathias Chu. Reused under the MIT License; see
> each source repo for the full license text.

The broader **claude-ads** audit skill (AgriciDaniel/claude-ads, MIT) is installed
separately as a Claude Code skill (`~/.claude/skills/ads*`), not vendored here.

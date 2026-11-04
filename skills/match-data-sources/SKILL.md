---
name: match-data-sources
description: Rules for researching football facts for match previews - which sources to trust (tiers), how to write a sourced claim with quote and retrieval time, fact keys, freshness, corroboration of key facts, conflicts, paywalls, and never fabricating. Use whenever researching, citing or fact-checking match data.
---

# Sourcing football facts

## A claim (one item of `web_claims.claims`)
```json
{"id":"W-007","fact_key":"H.predicted_xi","category":"lineup","statement":"Predicted Real Madrid XI.",
 "value":[{"name":"...","number":1,"position":"G"}, ...11],"unit":null,"as_of":"2026-11-02T10:00:00Z","confidence":"medium",
 "sources":[{"kind":"web","url":"https://...","title":"...","publisher":"Marca","tier":1,"quote":"<verbatim, <= 400 chars>","retrieved_at":"<now, UTC>"}]}
```
- `fact_key` from `config/facts.yaml` (`H.`/`A.` prefixes; `T.tactics.<anything>` for tactical descriptions);
  `null` only for context that no graphic or number uses.
- `value` must have the registered type (numbers as numbers; `form` = list of W/D/L oldest→newest; `xi` = exactly 11
  with one `G`; absences = `[{player, reason, status: out|doubt}]`).
- `quote` is copied verbatim from the page and must support the value. No quote, no claim.
- `as_of` = when the fact was true (article date, stats date); `retrieved_at` = when you read it.

## Trust tiers (`config/sources.yaml`)
1 — official (UEFA, leagues, clubs) and major outlets (BBC, ESPN, Sky, Athletic, Reuters, Marca, AS);
2 — statistics/analysis (FBref, Understat, WhoScored, Sofascore, FotMob, Transfermarkt, The Analyst);
3 — everything else (warning for key facts). Never: social media, forums, video comments (blocked).

## Key facts need corroboration
Kick-off, venue, injuries/suspensions and predicted XIs need two independent domains, an API source, or an explicit
`"single_source": true` (then the analysis must state the uncertainty). Predicted line-ups are predictions — say so.
Subdomains count once: `match.uefa.com` and `www.uefa.com` are one domain. A flag on any claim makes the fact
`single_source`, even when a second cited source exists; only an unresolved conflict outranks it.

## Freshness
Team news ≤ 48 h old, stats ≤ 7 days. Close to kick-off, confirmed line-ups replace predicted ones.

## Never
Fabricate, round a number to make it "nicer", infer a statistic from memory, or cite a page you did not open. If a
fact cannot be found, leave it out and report the gap. Paywalled page → use another source; never quote paywalled text
you cannot see.

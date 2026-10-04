# Phase 4 — forward-validation stage. Pre-registration v1.1 — FROZEN (R-Y, ChatGPT, 2026-10-04; written 2026-10-03 BEFORE the round-2 historical table was run)

R-Y: v1 accepted on one revision, applied verbatim before freezing — §4 class-S minimum changed from a generic 4 episodes
(incompatible with the ex-top-3 concentration gate) to the already-frozen candidate minimums A ≥ 10 / C ≥ 8; 365 forward
days kept; B ≥ 60 trades at the first evaluation, ≥ 100 from the second. Nothing else changed.

Required by the frozen round-2 document (R-X): this is the only path from `historical_survivor` to `research_accepted`.
It is frozen on written acceptance; it is never edited after the first forward evaluation, and it is written before
any round-2 historical result exists, so no number here can have been shaped by one. `research_accepted` never means
`trade_approved`; Phase 10 additionally needs Kraken paper reproduction.

## 1. Who enters
Only candidates whose round-2 historical outcome is `historical_survivor` (including `historical_survivor (assumed
availability)` for C). A `historical_rejected` candidate is retired; an `inconclusive` candidate is retired unless its
inconclusiveness is purely an episode-count shortfall, in which case it may enter the forward stage under its class rules
(the forward span then supplies the episodes). Entry is recorded in the manifest with the round-2 table's data_hash.

## 2. The forward span and its data
- Freeze instant: acceptance of this document. **Forward bars = daily bars opening at or after 2026-10-04 00:00 UTC**
  (the frozen snapshot ends 2026-10-01; the 10-02 and 10-03 bars existed when this was written and are excluded).
  Bars before that are used only for indicator warm-up and the first parameter selection; they are never forward evidence.
- Source: the live collector (`md-backfill`, daily Coinbase bars into `md_candles`; `universe_history` maintained by
  `universe-sync`). Each evaluation exports a fresh full snapshot with the publishable key, records its data_hash,
  universe_hash and membership_hash, and uses completed bars only. Listing windows, exclusion map, monthly top-20 universe
  mechanics, cost sets, allocator and delisting treatment are exactly those of the frozen round-1/round-2 documents.
- F&G (C only): **live-captured rows only** (`fund-snapshot` collector, 00:20 UTC daily, `available_at` = capture time).
  The D+1 assumed-availability rule is NOT used forward. Usable = verified `available_at ≤ decision close`; never
  forward-filled; the 80% / 30-day coverage rule applies to the forward span.
- Costs: canonical 0.50%/side (assumed tier) until the live Kraken tier is read; a tier reading replaces the cost record
  for later evaluations and is logged; it is not a re-tune. Stress ×1.25 and severe 0.95% reported as before.

## 3. The process under test (not a single parameter set)
The deployable process is the walk-forward itself. Forward, it continues unchanged: at each 90-day boundary after the
freeze, parameters are re-selected on the trailing 365-day fit window by in-fit Sharpe from the candidate's frozen grid
and applied to the next 90 days; the first forward window uses the parameters selected on the 365 days ending at the last
completed bar before 2026-10-04. The forward verdict curve is the continuous frozen-parameter run over the forward span
(positions carry across boundaries; §4 of the round-1 document). Selection never touches forward bars that have not
completed. Boundary dates are fixed now: 2026-10-04 + k × 90 days.

## 4. Minimum forward sample before any evaluation (frozen)
| class | minimum | rationale |
|---|---|---|
| S (A, C) | ≥ 365 forward calendar days AND the candidate's frozen round-2 minimum of completed forward episodes: **A ≥ 10 round trips, C ≥ 8 episodes** | one full year so the calendar-year test can run; the ex-top-3 concentration gate needs well over three episodes to be meaningful (R-Y: a 4-episode minimum would have made it unsatisfiable) |
| X (B) | ≥ 365 forward calendar days AND ≥ 60 completed forward trades | monthly rebalance with n ∈ {3, 5} yields roughly 40–80 trades per year; 100 would take two years and is set for the second evaluation instead |
Before the minimum is reached nothing is evaluated; a dashboard monitor may display the running curve (descriptive, no
decision, no rule change). If the minimum is not reached within 3 years of the freeze the candidate is retired
(`forward_expired`).

## 5. Evaluation schedule and decision rule (frozen; no optional stopping)
- Evaluations happen only at the 90-day boundaries of §3, starting at the first boundary at which §4 is satisfied.
- Gates = the candidate's class gate from the frozen round-2 document §0, computed on the forward verdict curve only
  (class S: positive canonical and ×1.25 return, ≥ 2 of 3 chronological thirds of the forward span, positive P&L in ≥ 2
  calendar years touched by the span, scale invariant, no boundary dependency, P&L ex-top-3 trades > 50%, the candidate's
  own falsifier against forward 100% BTC buy-and-hold / forward no-floor twin / forward base rate; class X: the round-1
  booleans with the trade minimum at 60 for the first evaluation and 100 from the second onward).
- **Acceptance needs two consecutive passing evaluations** (90 days apart) — the second is the confirmation. On the
  second pass the outcome is `forward_survivor` = `research_accepted` (Phase 5 eligible; Phase 10 after Kraken paper
  reproduction).
- **Any failing evaluation is final: `forward_rejected`**, candidate retired. Re-entry needs a new pre-registration and
  a fresh forward span; the retired candidate's forward data is never reused as its own evidence.
- Outcomes are exactly `forward_pending`, `forward_survivor`, `forward_rejected`, `forward_expired`.

## 6. Reporting per evaluation
Manifest with: candidate, class, round-2 reference (table data_hash, outcome), freeze instant, forward span, evaluation
index, snapshot hashes, parameter selections per forward window, continuous forward curve, every gate boolean, falsifier
numbers, episode/trade counts vs minimum, cost record, `stale_marks`, F&G coverage (C), paired twin (B), per-regime state
(filter off, descriptive). Nothing is written to `research_runs` until the evaluation has been independently reviewed;
`research_runs` rows carry `evidence_class = forward` and never `trade_approved`.

## 7. Not allowed during the forward stage
Changing a grid, threshold, cost assumption (other than the logged live-tier reading), universe rule, gate, minimum,
boundary date or evaluation cadence; evaluating off-schedule; reading forward results before the first scheduled
evaluation other than the descriptive monitor; pooling historical and forward spans into one verdict.

## Questions for the reviewer — answered R-Y (Revise → applied / Accept / Freeze on revision)
1. Minimums: S revised to A ≥ 10 / C ≥ 8 forward episodes with 365 days; X 365 d + 60 trades, 100 from the second evaluation → accepted.
2. Two consecutive passing evaluations for acceptance, any fail final → accepted.
3. Frozen as v1.1 once §4 carried the revision.

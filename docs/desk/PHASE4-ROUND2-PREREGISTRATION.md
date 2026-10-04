# Phase 4, round 2 — post-Round-1 hypothesis screening. Pre-registration v2 — FROZEN (R-X, ChatGPT, 2026-10-03, at PR #51 @ 8a52e079)

Frozen answers (R-X): Q1 episode minimums A ≥ 10 / C ≥ 8 accepted. Q2 = (ii): C runs the declared assumed-availability
D+1 screening, `evidence_class = assumed_availability`; it may reject C or yield at most `historical_survivor (assumed
availability)`; the verified-availability result stays `inconclusive` at 0% coverage. Q3 frozen. Procedural requirement:
the forward-validation stage (`PHASE4-FORWARD-VALIDATION.md`) is pre-registered and sent for review BEFORE the round-2
historical table is run. Nothing below this line changes.

**Evidence status rule (the most important line in this document).** Round 1's results (R-V) were observed before these
hypotheses were written. The 2021–2026 OOS span is therefore no longer untouched for them. The round-2 historical run is
**hypothesis screening**: it may reject a hypothesis or nominate it for forward validation; it can never by itself confer
`research_accepted`. Round-2 historical outcomes are exactly `historical_survivor`, `historical_rejected` or
`inconclusive (reason)`. A `historical_survivor` advances only to a **forward-validation stage** under the rule frozen
here, on bars that did not exist at the freeze (new data_hash); that stage, pre-registered separately and reviewed
**before** the round-2 table is run (so its rules cannot be shaped by the round-2 result), is the only path to
`research_accepted`. `research_accepted` never means `trade_approved`.

Inherits every rule of round 1 (`PHASE4-PREREGISTRATION.md` v2, R-S FINAL) unless a line below says otherwise: same frozen
snapshot `8df7990c93dcc632` / universe `64e00348d99bb713` / membership `99c437c3e40dbb57`, same monthly top-20 universe where
a candidate uses alts, same exclusion map, canonical 0.50% / stress 0.625% / severe 0.95% cost sets, 365/90 walk-forward
with selection inside fit windows only, continuous frozen-parameter OOS verdict curve, boundary-dependency rule, scale
invariance, delisting stress, per-regime reporting with the filter off, `stale_marks` in every record, nothing to
`research_runs` before review. Grids stay at ≤ 4 points. Each candidate carries a pre-stated rationale, its honest
provenance (which round-1 observation it responds to) and a pre-stated falsifier.

## 0. Candidate classes and their gates (frozen now; nothing waived after results)
| class | members | gate (ALL must hold for `historical_survivor`) | episode minimum (fewer ⇒ `inconclusive`) |
|---|---|---|---|
| **S — single-asset timing** | A, C | continuous OOS return > 0 (canonical costs) · > 0 under ×1.25 stress (continuous) · positive in ≥ 2 of 3 chronological thirds · positive OOS P&L in ≥ 2 calendar years · scale invariant · no boundary dependency · P&L excluding the 3 best completed trades > 50% of total P&L · the candidate's own falsifier | A: ≥ 10 completed round trips in OOS; C: ≥ 8 completed non-overlapping episodes in OOS |
| **X — cross-sectional** | B | the full round-1 gate (11 booleans incl. ≥ 100 OOS trades, `symbols>=min`, `not_top3_dependent`) · the candidate's own falsifier | ≥ 100 OOS trades (round-1 rule) |
Symbol-diversification tests are structurally impossible for a BTC-only rule and are replaced for class S by the temporal
and trade-concentration tests above; they are not waived for class X. `inconclusive` is a legitimate outcome and is never
converted into a pass.

## Candidate A — BTC-only trend. **Provenance: post-Round-1 decomposition hypothesis** (same SMA family and grid as the
rejected broad-alt `sma_trend`, restricted to BTC after observing that the alt version failed). Not an untouched test of
SMA trend.
- Hypothesis: the trend premium in crypto sits in the deepest-liquidity asset; alts added dispersion, not premium.
- Rule: long BTC when close > SMA_slow and SMA_fast > SMA_slow on completed daily bars; flat (cash) otherwise. One
  position. **Verdict run: max_positions = 1, gross_cap 1.0 (100% BTC exposure)** — the correct canonical implementation
  of a single-asset rule, declared here as the deviation from the 10-slot allocator. The 10-slot / 10%-invested version is
  a sizing sensitivity, reported, never the verdict.
- Grid: (fast, slow) ∈ {(20,100), (50,200)}. Two points. Selection by in-fit Sharpe as in round 1.
- Benchmarks: 100%-allocated BTC buy-and-hold over the same OOS span (one entry at the first OOS open, canonical costs)
  and cash. The 10%-slot B&H of round 1 is also printed for continuity.
- Falsifier (quantitative): with R_A, R_BH the continuous OOS returns and DD_A, DD_BH the max drawdowns,
  A is `historical_rejected` unless **R_A ≥ R_BH, or (R_A ≥ 0.70 × R_BH and DD_A ≤ 0.70 × DD_BH)**; if R_BH ≤ 0 the first
  clause reduces to R_A > 0 (already required by the class-S gate). Independently, A must be positive after canonical
  and ×1.25 costs (class-S gate).

## Candidate B — cross-sectional alt strength with a breadth cash floor. **Provenance: post-Round-1 response** (the
rejected `momentum_top` lost through 2022; the floor is the hypothesis that the loss came from holding alts while the
liquid cross-section was broadly weak).
- Hypothesis: relative strength among liquid alts is tradeable only while strength within that cross-section is broad.
- Rule, at each monthly rebalance close (the engine's decision close, 30-day cadence as in `momentum_top`):
  - **Breadth (top-20 only, never the Phase-3 whole-market series)** = number of frozen top-20 members with close > their
    own SMA50 / number of members, computed from completed bars at that close. Members carry ≥ 90 contiguous fresh bars by
    construction, so SMA50 exists for every member.
  - **Fail closed:** if the membership at that close has fewer than 20 names, or any member's bar for the completed day is
    missing, that rebalance goes to cash (all positions sold, no buys); the event is counted and reported as
    `breadth_fail_closed`. The denominator never shrinks silently.
  - If breadth < **0.50** (fixed, not tuned): cash — sell every position, no buys. Otherwise rank members by `lookback`-day
    return and hold the top `n`, equal slots, selling anything not in the top `n`. Exits at rebalance only.
- Grid: n ∈ {3, 5} × lookback ∈ {60, 90}. Four points. Canonical 10-slot allocator (slots beyond n stay in cash).
- **Paired comparison (exact):** parameters are selected on the cash-floor candidate (the deployable rule). The
  **no-floor twin** then runs the identical rule with the floor removed, using **the same selected parameters in each OOS
  fold** and the same continuous schedule. Falsifier: the floor variant must beat its twin on continuous OOS return AND
  max drawdown AND profit factor; otherwise the breadth mechanism is `historical_rejected` as cosmetic (R-P cash-sitting
  rule). B must also pass the full class-X gate.

## Candidate C — BTC timing on Extreme Fear (architecture §10, H-SWEEP-A as a hypothesis). **Provenance: not a round-1
rule; still post-Round-1 in time, so status rules above apply.**
- Hypothesis: a Fear & Greed reading at or below the threshold marks capitulation that is followed by above-base-rate
  **90-day** BTC returns (primary structural horizon). 30-day forward return is a pre-registered sensitivity, not part of
  the hypothesis.
- Rule (**Option I, timing; executable on the one-position-per-symbol engine**): when FLAT and the usable F&G reading for
  the completed day D is ≤ threshold, buy BTC at the next open; hold exactly **H = 90** bars; sell at the open after the
  90th completed holding bar; no stop; all F&G readings while holding are ignored. Verdict run: max_positions = 1,
  gross_cap 1.0 (declared, as for A); the 10-slot version is a sizing sensitivity. Genuine multi-lot accumulation (Option
  II) is deferred to the accumulation phase; no pyramiding is smuggled into the tournament engine.
- Grid: threshold ∈ {20, 25}. Two points (H fixed at 90). A fit window with no completed episode for either threshold
  selects the first grid point (20, the stricter). Sensitivity reported for the selected threshold: H = 30.
- **Availability timestamp (frozen data rule).** F&G rows carry `observed_for_date`, `value`, `source`, `available_at`.
  A decision at close t may use the reading for date D only if `available_at ≤ t`. **Usable** = has a verified
  `available_at`. Missing readings stay missing; never forward-filled; a missing reading is `no signal`.
  - Live rows (collector `fund-snapshot`, 00:20 UTC daily since 2026-10-02): `available_at` = the collector's capture
    time (observed pattern: the value dated D is captured at D 00:20 UTC, i.e. before D's close).
  - **Fact recorded at drafting (2026-10-03): `market_sentiment_daily` holds 2 rows (2026-10-02, 2026-10-03).** There is
    no stored F&G history over the 2021–2026 OOS span; any history would be a backfill from alternative.me's historical
    endpoint, which gives the date and value but not when the value was published. Backfilled rows therefore get
    `available_at = NULL` and are **unusable** under this rule.
  - Consequence, stated before any run: on verified availability C's historical coverage is 0% ⇒ **C is `inconclusive`
    by rule on the historical span.** Two pre-registered ways forward, for the reviewer to choose (§ Questions):
    (i) C is forward-validation-only: live rows accumulate with verified `available_at`; C is evaluated in the
    forward stage once its episode minimum is met; or
    (ii) a declared **assumed-availability** screening run: backfilled rows get `available_at := close of D+1`
    (the reading dated D usable only from the decision close of D+1, a ~47-hour lag beyond the live-observed pattern),
    `evidence_class = assumed_availability`; its best possible outcome is `historical_survivor (assumed availability)`,
    which still requires forward validation on live rows; it can reject the hypothesis.
- Coverage rule: C is `inconclusive` if usable point-in-time coverage is < 80% of OOS days **or** any unexplained
  contiguous coverage gap exceeds 30 days.
- Falsifier (same non-overlapping executable signals, never all fear days): mean and hit rate of the 90-day forward BTC
  return after the executed entries must both exceed the unconditional mean and hit rate of 90-day forward BTC returns
  over the same OOS span (reported side by side); otherwise `historical_rejected` even if the equity line is positive.
  "All Extreme-Fear days" is reported as a descriptive event study only (overlapping days are correlated).
- Caveat carried in the record: F&G is a composite partly derived from price and volatility, so it is not independent
  of the price features.

## Benchmarks and controls: 100% BTC buy-and-hold (1 slot), 10%-slot BTC buy-and-hold (round-1 continuity), cash,
`breakout20` negative control (never enters selection or trial accounting).

## Reporting additions for round 2
- Each candidate's class, provenance, rationale, falsifier and evidence status printed beside its outcome.
- `stale_marks`, episode count vs minimum, `breadth_fail_closed` count (B), paired-twin table (B), F&G coverage share,
  longest gap, usable-row count and evidence class (C), signal table and base-rate comparison (C).
- Trial count = Σ grid points × folds over A, B, C; the control never enters it.

## Forward-validation stage (to be pre-registered separately BEFORE the round-2 table is run)
Rule frozen here; applies to bars after 2026-10-01 (the frozen snapshot's last bar); a declared minimum forward sample
per class before any evaluation; the same gates as §0 on the forward span; only this stage can confer `research_accepted`.

## Not in round 2: any retuning of round-1 rules; any regime filter; intraday data; leverage; shorts; multi-lot accumulation.

## Questions for the reviewer — answered in R-X (Accept / ii / Freeze); kept for the record
1. Episode minimums A ≥ 10 round trips, C ≥ 8 episodes: accept, or set other numbers? → accepted.
2. C on the historical span: (i) forward-only, or (ii) the declared assumed-availability screening run (D+1 close lag)? → (ii).
3. Freeze v2 as written once 1–2 are answered? → frozen.

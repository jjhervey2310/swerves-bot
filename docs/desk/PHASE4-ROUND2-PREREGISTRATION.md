# Phase 4, round 2 — pre-registration DRAFT v1 (for independent review before any code or run)

Inherits every rule of round 1 (`PHASE4-PREREGISTRATION.md` v2, R-S FINAL) unless a line below says otherwise: same frozen
snapshot and hashes, same monthly top-20 liquidity universe where a candidate uses the alt universe, same exclusion map,
canonical/stress/severe cost sets, fixed allocator, continuous OOS verdict curve, eight advancement booleans, nothing to
`research_runs` before review. Round 1 taught that generic rules on the whole alt universe lose 80–90%; round 2 therefore
requires every candidate to carry a **pre-stated market-structure rationale and a pre-stated falsifier**. Round 1 results
were seen before this draft; the discipline is that no candidate below is a tuned version of a round-1 rule, each is a
different hypothesis, and the grids stay at ≤ 4 points.

## Candidate A — BTC-only trend (hypothesis: the trend premium that exists in crypto is in the asset with the deepest
liquidity and the fewest idiosyncratic blow-ups; alts add dispersion, not premium)
- Rule: long BTC when close > SMA_slow and SMA_fast > SMA_slow on completed daily bars; flat (cash) otherwise. Single
  position, slot = full gross_cap (max_positions = 1 is a declared deviation from the 10-slot allocator because the
  strategy is single-asset by construction; both 10-slot and 1-slot versions are reported, the 1-slot is the verdict).
- Grid: (fast, slow) ∈ {(20,100), (50,200)}. Two points.
- Falsifier: continuous OOS return below BTC buy-and-hold with no drawdown improvement ⇒ rejected regardless of sign.

## Candidate B — cross-sectional long-only with an explicit cash floor (hypothesis: relative strength among liquid
alts is tradeable only while the market is broadly healthy; the loss in round 1 came from holding alts through 2022)
- Rule: monthly, rank the top-20 universe by 90-day return; hold the top n equally-slotted; hold **cash** instead of any
  slot whenever breadth (share of the top-20 above their own SMA50, computed as in the regime engine) < 0.50 at the rebalance
  close. Breadth threshold fixed at 0.50, not tuned. Exits: monthly rebalance only.
- Grid: n ∈ {3, 5} × lookback ∈ {60, 90}. Four points.
- Falsifier: filtered variant must beat the same rule without the cash floor on OOS return AND max drawdown AND
  profit factor (the R-P cash-sitting rule); otherwise the breadth mechanism is rejected as cosmetic.

## Candidate C — BTC accumulation on Extreme Fear (architecture §10 hypotheses H-SWEEP-A/B/C; hypothesis: the
Fear & Greed index at ≤ 25 marks capitulation that is followed by positive 90-day BTC returns more often than base rate)
- Rule: on a completed day where the F&G reading dated that day is ≤ 25, buy one BTC slot at the next open; hold for a
  fixed horizon H then sell; no stop. At most one open slot per 7 calendar days. Cash otherwise.
- Grid: H ∈ {30, 90} days × threshold ∈ {20, 25}. Four points. Data: `market_sentiment_daily` must be joined by date to
  the completed bar (the F&G value for day D is known at D's close); history coverage of F&G over the OOS span is
  reported, and any gap is `no signal`, never forward-filled.
- Falsifier: hit rate and mean H-day return after signals must exceed the unconditional base rate over the same OOS span
  (reported side by side); if not, rejected even if the equity line is positive.

## Benchmarks and controls (unchanged): BTC buy-and-hold (now also reported at 1 slot = 100% for comparability with A), cash,
breakout20 negative control.

## Reporting additions for round 2
- Each candidate's rationale and falsifier are printed in the table next to its verdict.
- `stale_marks` count from the engine (R-V hardening) in every record.
- For C: number of signals, base-rate comparison table, F&G coverage share.

## Not in round 2 (explicitly): any retuning of round-1 rules; any regime filter; intraday data; leverage; shorts.

## Questions for the reviewer
1. Candidate A's single-slot deviation from the frozen allocator: acceptable as declared, or run A inside the 10-slot
   allocator only?
2. Candidate B's breadth floor at 0.50 reuses the regime engine's breadth input (not its labels). Is that an acceptable
   reuse, or should breadth be recomputed from the top-20 only (my current wording) to keep it independent of Phase 3?
3. Candidate C's F&G history: if coverage of the OOS span is below 80%, should C be inconclusive by rule?

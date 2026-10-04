# Phase 4, round 3 — runner forensics. Pre-registration DRAFT v3 (after reviews R-AC and R-AD; for independent review before any code, label or feature is computed)

Changes from v1 are marked **[R-AC n]**: (1) OOS scoring and the gate run on the FULL eligible universe, gray zone and
delisted names included; (2) label denominator is the next executable open; (3) base rate is the 3× share of all
eligible candidates; (4) verified and assumed are two separate pipelines, never a selectable hyperparameter.
Changes from v2 are marked **[R-AD]**: the objective is 2× and above (Jacob's stated win threshold), so the label hierarchy
is 2× primary / 3× secondary / 5× tail; the primary model learns 2× versus not-2×; 3× and 5× are enrichment tests.

Status: post-Round-2 hypothesis screening (R-AA: zero survivors in two rounds). Outcomes are `historical_survivor` /
`historical_rejected` / `inconclusive (reason)`; nothing here confers `research_accepted`; a survivor feeds a round-4
STRATEGY pre-registration (entry/exit rules derived from the score), never a trade. Direction and falsifier set by the
independent reviewer (R-AB) and adopted verbatim:

> **Falsifier.** If a point-in-time runner-forensics model built from fundamentals, revenue/fees, tokenomics,
> liquidity/volume acceleration, relative strength, flows, and catalysts cannot distinguish future 3x–5x runners from
> matched non-runners out-of-sample with materially better precision than the base rate, after liquidity and survivorship
> controls, reject the entire Round-3 hypothesis.

## 0. Data reality (audited 2026-10-04, before design; this decides what the study can honestly use)
| feature family | point-in-time source available over 2021–2026? | evidence class |
|---|---|---|
| price, volume, dollar volume, relative strength, volume acceleration, drawdown, age since listing | yes — `md_candles` daily (data_hash `8df7990c93dcc632`) + `universe_history` listing windows incl. 88 delisted names | **verified** (reconstructed from completed bars; no publication-lag question) |
| protocol fees / revenue / TVL / DEX volume | no stored history: `fund_snapshots_daily` holds 3 days (2026-10-02 →), 2,629 names. DeFiLlama's historical per-protocol endpoints can be backfilled, but they give the value by date, not when it was published, and values are revised | **assumed_availability** (declared lag; see §3) or excluded |
| stablecoin / ETF flows | same: DeFiLlama stablecoin history backfillable, publication time unknown | **assumed_availability** or excluded |
| tokenomics (unlock schedules, supply changes, FDV/mcap) | no point-in-time source identified; `token_map` has no history | **excluded** unless a dated source with publication timestamps is found in Stage 0 |
| catalysts (listings, upgrades, partnerships) | no point-in-time source; any reconstruction from today's knowledge is hindsight | **excluded** |
Consequence, stated now: round 3 is run twice, exactly as C was in round 2 — a **verified** study on price/volume-derived
features only, and an **assumed-availability** study adding backfilled fundamentals and flows. Each gets its own outcome;
the assumed study can reject the hypothesis but its best outcome is `historical_survivor (assumed availability)`. The
falsifier's "fundamentals, tokenomics, catalysts" families are either assumed or excluded; this is recorded, not hidden.

## 1. Stage 0 — data audit and feature freeze (reviewed before any label is computed)
Deliverable: a feature manifest listing every feature with its formula on completed bars, its source table, its evidence
class, its declared lag, and the first/last date it exists; a feature with no point-in-time source is dropped here.
No label and no model output exists when this manifest is reviewed. Backfills (DeFiLlama) are loaded with `available_at`
NULL (unusable in the verified study) and the declared lag rule of §3 applies only in the assumed study.

## 2. Stage 1 — the case-control study
- **Formation dates**: the first decision close of each UTC month from 2021-03 to 2025-11 (57 months), so the longest
  label horizon completes inside the frozen snapshot (ends 2026-10-01).
- **Candidate set at a formation date** (survivorship control): every name listed at that close with ≥ 90 completed
  contiguous bars and 3-day median dollar volume ≥ $250k, INCLUDING names later delisted (a delisting inside the horizon
  is a non-runner, never a dropped row). Exclusion map of round 1 applies (stablecoins, wrapped assets).
- **Labels [R-AC 2, R-AD]**: `entry_reference` = the next available executable OPEN after the formation decision close
  (the formation close itself is never a reference, so an overnight gap is never counted as capturable return). With
  `M` = max completed close during the next 180 bars starting at the entry-reference bar:
  `runner_2x` (PRIMARY positive) = M ≥ 2 × entry_reference; `runner_3x` (secondary tier) = M ≥ 3 ×; `runner_5x`
  (extreme tier) = M ≥ 5 ×; primary non-positive = every eligible name with M < 2 ×, delisted names included. No
  gray zone exists in the primary definition. A name with no executable open after the formation close is ineligible
  that month (counted). A delisting inside the horizon ends the window early; the label is computed on the closes that
  exist (a delisted name is never dropped).
- **Training set = scoring population [R-AD]**: the primary model learns `runner_2x` versus not-`runner_2x` on every
  eligible training name, and the OOS model scores every eligible name at every formation date; no future-return band
  is ever removed from training or scoring, so the model is trained and graded on the same objective. A cleaner-contrast
  model (3× vs < 1.5×) may be fitted as a DIAGNOSTIC only; it never gates and its numbers are labelled diagnostic.
- **Liquidity control (stratification)**: inside each formation month, eligible names are bucketed into dollar-volume
  quintiles; precision@k and the base rate are computed within each (month, quintile) stratum on the FULL eligible
  population of that stratum [R-AC 1], then averaged with positive-count weights, so a model cannot win by preferring
  small names. The matched 3× vs < 1.5× diagnostic uses the same strata.
- **Features at formation** (Stage-0 manifest; all from bars completed by the formation close): 30/90-day returns,
  relative strength vs BTC (7/30/90 d), dollar-volume acceleration (7 d vs 30 d, 30 d vs 90 d), volume z-score,
  distance from 90-day high and from 365-day high, drawdown from listing high, realised vol 20/60 d, age since first
  bar, market-breadth context (share of candidates above their SMA50). Assumed study adds: fees/revenue 7 d and 30 d
  growth, revenue yield (revenue / market cap), TVL change 30 d, stablecoin supply change 30 d.
- **Model (frozen, simple on purpose)**: L2-regularised logistic regression on standardised features, fit on formation
  months strictly earlier than the test year. **Two separate pipelines [R-AC 4]** — `verified` (price/volume features
  only) and `assumed` (adds the backfilled fundamentals of §3) — each with its own run, outcome and evidence class;
  the evidence class is never a hyperparameter and no selection step ever compares the two. Within each pipeline the
  only selected parameter is C ∈ {0.1, 1.0}, by in-fit log-loss. Test years 2022, 2023, 2024, 2025 (expanding window;
  2021 is fit-only). Trials counted per pipeline (2 × 4 = 8 each).
- **Statistic [R-AC 1, 3; R-AD]**: population precision@k for `runner_2x`, with k = the top 10% of each formation
  month's ELIGIBLE names by model score, versus the **base rate = share of `runner_2x` among all eligible names** of
  the same (month, quintile) stratum, averaged with positive-count weights. **Enrichment tests (reported, not gates)**:
  the share of `runner_3x` and of `runner_5x` in the top-10%, top-5% and top-20% score buckets versus their own
  full-population base rates — the highest buckets should hold progressively more 3× and 5× runners. Also reported:
  lift at top 5% and top 20% for 2×, AUC on the full population, calibration by decile, the diagnostic model's numbers.
- **"Materially better than base rate" (frozen now; operates on the 2× full-population metric above)**: population
  precision@10% for `runner_2x` ≥ 2 × the full-universe 2× base rate in the pooled OOS AND ≥ 1.5 × in at least 3 of
  the 4 test years AND the lift survives when the most liquid quintile is removed AND when the top three contributing
  months are removed. Anything less is `historical_rejected`. 3× and 5× enrichment is reported alongside, never gated.
- **Minimum evidence**: ≥ 40 `runner_2x` positives among eligible names across the OOS test years in total and ≥ 5 in
  every test year; fewer ⇒ `inconclusive (episodes)`.
- **Leakage controls**: features from completed bars only; labels start at the next executable open; no future label
  ever removes a name from the scored population [R-AC 1]; the formation close is excluded from both; standardisation
  statistics fit on training months only; no feature uses market cap or supply figures that
  are not point-in-time; the delisted names' bars end at delisting and their labels are computed on what exists.
- **Negative control**: each pipeline re-run on `runner_2x` labels shuffled within (month, quintile) strata of the full
  eligible population; its population precision must sit at the base rate; if it does not, the pipeline leaks and the
  table is invalid.
- **Permutation p-value**: 1,000 within-stratum label permutations; reported, not a gate.

## 3. Assumed-availability rule for backfilled fundamentals (assumed study only)
A value dated D is usable from the decision close of D + 7 (a week's lag, since DeFiLlama figures are revised for days
after the date); evidence_class = `assumed_availability`; the verified pipeline never sees them. **Subordination
[R-AC]**: the assumed pipeline is explicitly subordinate — its survivor can only generate a round-4 hypothesis; it can
never establish a verified fundamental edge, and its outcome is always suffixed "(assumed availability)".

## 4. What a survivor leads to
A `historical_survivor` (either study) does not trade. It qualifies the score as an input to a round-4 strategy
pre-registration (entry when score in the top decile at a formation close, exit rules to be pre-registered), which
then runs under the round-1 engine and gates and, if it survives, enters the frozen forward-validation stage. The
assumed study's survivor additionally needs the live collectors (`fund-snapshot`, daily since 2026-10-02) to accumulate
verified fundamentals before any forward evaluation.

## 5. Hard rules
Nothing in §2 changes after the first label is computed; Stage 0 is reviewed first; no feature is added after seeing a
lift; the negative control is run every time the real pipeline is; nothing to `research_runs` before review.

## Questions for the reviewer — v2 answers R-AD (Revise / Revise / Accept / Not yet) applied above
1. Label hierarchy 2× primary / 3× secondary / 5× tail on max completed close within 180 bars vs the next executable
   open; primary model trained and graded on 2× vs not-2× over every eligible name; 3× vs <1.5× diagnostic only — accept?
2. "Materially better" unchanged in thresholds, on 2× population precision with the 2× full-universe base rate; 3× and 5×
   enrichment reported, never gated — accept?
3. Freeze v3?

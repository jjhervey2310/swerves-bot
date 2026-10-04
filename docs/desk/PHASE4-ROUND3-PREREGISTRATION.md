# Phase 4, round 3 — runner forensics. Pre-registration DRAFT v1 (for independent review before any code, label or feature is computed)

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
- **Labels** (from the next open forward; the formation close is never inside the window): `runner_3x` = max close
  within 180 bars ≥ 3 × formation close; `runner_5x` = ≥ 5 ×; `non_runner` = max close within 180 bars < 1.5 ×; names in
  between are neither and are excluded from training and scoring (they are counted and reported). Primary label:
  `runner_3x`; `runner_5x` reported.
- **Liquidity control (matching)**: inside each formation month, names are bucketed into dollar-volume quintiles; each
  runner is matched to the non-runners of its own month and quintile; all lift statistics are computed within (month,
  quintile) strata and then averaged with runner-count weights, so a model cannot win by preferring small names.
- **Features at formation** (Stage-0 manifest; all from bars completed by the formation close): 30/90-day returns,
  relative strength vs BTC (7/30/90 d), dollar-volume acceleration (7 d vs 30 d, 30 d vs 90 d), volume z-score,
  distance from 90-day high and from 365-day high, drawdown from listing high, realised vol 20/60 d, age since first
  bar, market-breadth context (share of candidates above their SMA50). Assumed study adds: fees/revenue 7 d and 30 d
  growth, revenue yield (revenue / market cap), TVL change 30 d, stablecoin supply change 30 d.
- **Model (frozen, simple on purpose)**: L2-regularised logistic regression on standardised features, fit on formation
  months strictly earlier than the test year. Grid ≤ 4: C ∈ {0.1, 1.0} × feature set ∈ {verified, assumed}. Selection
  by in-fit log-loss only. Test years 2022, 2023, 2024, 2025 (expanding window; 2021 is fit-only). Trials counted.
- **Statistic**: precision@k with k = the top 10% of each formation month's candidates by model score, versus the base
  rate (runner share of that month's candidates), computed within strata as above. Also reported: lift at top 5% and
  top 20%, AUC, calibration by decile, and the same numbers for `runner_5x`.
- **"Materially better than base rate" (frozen now)**: precision@10% ≥ 2 × base rate in the pooled OOS AND ≥ 1.5 × base
  rate in at least 3 of the 4 test years AND the lift survives when the most liquid quintile is removed AND when the
  top three contributing months are removed. Anything less is `historical_rejected`.
- **Minimum evidence**: ≥ 40 runners (3x) across the OOS test years in total and ≥ 5 in every test year; fewer ⇒
  `inconclusive (episodes)`.
- **Leakage controls**: features from completed bars only; labels start at the next open; the formation close is excluded
  from both; standardisation statistics fit on training months only; no feature uses market cap or supply figures that
  are not point-in-time; the delisted names' bars end at delisting and their labels are computed on what exists.
- **Negative control**: the same pipeline on labels shuffled within (month, quintile) strata; its precision must sit at
  the base rate; if it does not, the pipeline leaks and the table is invalid.
- **Permutation p-value**: 1,000 within-stratum label permutations; reported, not a gate.

## 3. Assumed-availability rule for backfilled fundamentals (assumed study only)
A value dated D is usable from the decision close of D + 7 (a week's lag, since DeFiLlama figures are revised for days
after the date); evidence_class = `assumed_availability`; the verified study never sees them.

## 4. What a survivor leads to
A `historical_survivor` (either study) does not trade. It qualifies the score as an input to a round-4 strategy
pre-registration (entry when score in the top decile at a formation close, exit rules to be pre-registered), which
then runs under the round-1 engine and gates and, if it survives, enters the frozen forward-validation stage. The
assumed study's survivor additionally needs the live collectors (`fund-snapshot`, daily since 2026-10-02) to accumulate
verified fundamentals before any forward evaluation.

## 5. Hard rules
Nothing in §2 changes after the first label is computed; Stage 0 is reviewed first; no feature is added after seeing a
lift; the negative control is run every time the real pipeline is; nothing to `research_runs` before review.

## Questions for the reviewer (one word each)
1. Labels: 3× within 180 bars primary, 5× reported, non-runner < 1.5×, in-between excluded — accept?
2. "Materially better": precision@10% ≥ 2× base rate pooled, ≥ 1.5× in 3 of 4 years, survives removing the top liquidity quintile and the top three months — accept?
3. Two studies (verified price-only; assumed with backfilled fundamentals at a 7-day lag), tokenomics and catalysts excluded for lack of point-in-time sources — accept, or defer round 3 until such sources exist?
4. Stage 0 feature manifest reviewed before any label is computed — accept?

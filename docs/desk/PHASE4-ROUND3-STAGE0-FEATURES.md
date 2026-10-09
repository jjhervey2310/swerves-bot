# Phase 4 round 3 — Stage 0 feature manifest, DRAFT v1 (for independent review; NO feature value, label or model output exists)

Governed by the frozen round-3 pre-registration v3 (R-AE). Machine-readable twin: `desk-loop/bt/round3_manifest.json`
(definitions only; the computation module is written after this manifest is frozen). Availability audit (read-only,
nothing stored): `docs/desk/PHASE4-ROUND3-STAGE0-AUDIT.json`.

## 1. Formation and eligibility (restated from v3, mechanical detail added)
First decision close of each UTC month 2021-03 → 2025-11 (57 dates). Eligible at a close: listed per `universe_history`
(later-delisted names included), ≥ 90 contiguous completed bars ending at that close, 3-day median dollar volume ≥ $250k,
not in the round-1 exclusion map, and an executable open exists after the close. Dollar volume = close × volume per bar.

## 2. Verified pipeline — 16 features, all from completed `md_candles` bars (data_hash `8df7990c93dcc632`), lag 0
| feature | formula at formation close (bars = completed bars, index −1 = last completed) | bars needed |
|---|---|---|
| ret_30 / ret_90 | close[−1]/close[−31]−1 ; close[−1]/close[−91]−1 | 31 / 91 |
| rs_btc_7 / 30 / 90 | (own k-day gross return) / (BTC k-day gross return) − 1 | 8 / 31 / 91 |
| dv_accel_7_30 / dv_accel_30_90 | mean(dv last 7)/mean(dv last 30) − 1 ; mean(dv last 30)/mean(dv last 90) − 1 | 30 / 90 |
| vol_z_20 | (volume[−1] − mean(volume[−21:−1])) / std(volume[−21:−1]); std = 0 ⇒ NaN | 21 |
| dist_hi_90 / dist_hi_365 | close[−1]/max(close last 90) − 1 ; close[−1]/max(close last ≤365 available) − 1 | 90 / 90 |
| dd_listing_high | close[−1]/max(close since first bar) − 1 | 1 |
| rv_20 / rv_60 | std of log returns over last 20 / 60 bars × √365 | 21 / 61 |
| age_bars | log1p(completed bars since first bar) | 1 |
| log_dv_90 | log(mean dv last 90) — also the stratification variable (quintiles within month) | 90 |
| breadth_ctx | share of that month's eligible names with close[−1] > own SMA50 (market context; same value for every name) | 50 |
NaN rule: any NaN verified feature ⇒ the name is ineligible at that date (counted and reported); no imputation.
Standardisation: mean/std fitted on training months only, per pipeline.

## 3. Assumed pipeline — adds 6 features from backfilled DeFiLlama history, evidence class `assumed_availability`
**Family rule (frozen before any value is read):** the DeFiLlama protocols whose token symbol equals S AND whose
`gecko_id` equals `token_map.gecko_id` for S when `token_map` knows S; when it does not, a symbol-only match is accepted
only if exactly one protocol carries that symbol; otherwise S has no family. Family values are summed across versions
and chains. This replaces the one-slug-per-symbol mapping in `token_map`, which is ambiguous for 104 of 256 names and
wrong in visible cases (AAVE→aave-aptos, SUSHI→sushi-aptos, WIF→world-is-flat, MASK→nullmask).
**Availability rule:** a family value dated D is usable from the decision close of D+7, and only for D ≥ the family's
earliest `listedAt` on DeFiLlama (history before listing was back-computed, never published point-in-time).
| feature | formula | endpoint |
|---|---|---|
| fees_growth_30 | Σ fees(31..D) / Σ fees(D−59..D−30) − 1 | summary/fees/{slug}?dataType=dailyFees |
| rev_growth_30 | same on daily revenue | summary/fees/{slug}?dataType=dailyRevenue |
| rev_yield | 12 × Σ revenue(last 30 d) / market cap at D (DeFiLlama mcap; NaN if absent) | protocol/{slug} |
| tvl_change_30 | tvl[D]/tvl[D−30] − 1 (family sum) | protocol/{slug} |
| stable_supply_30 | global stablecoin circulating USD[D]/[D−30] − 1 (market context, same for every name) | stablecoins.llama.fi/stablecoincharts/all |
| has_fundamentals | 1 if a family exists and fees or TVL exist at D under the availability rule, else 0 | — |
NaN rule: fundamental features NaN ⇒ 0 after standardisation, with `has_fundamentals` as an explicit feature whose
coefficient is reported, so a "has fundamentals at all" effect cannot pass as a fundamentals signal.

## 4. Availability audit (2026-10-09, read-only; the reason the assumed pipeline is subordinate)
| | |
|---|---|
| universe names (excl. map) | 480 |
| with ≥ 1 DeFiLlama protocol sharing the symbol (before the gecko_id rule) | 290, of which 134 multi-protocol families |
| with a fees module | 188 |
| earliest `listedAt` by year among matched | 2021: 23 · 2022: 47 · 2023: 47 · 2024: 29 · 2025: 23 · 2026: 19 · none: 102 |
| earliest daily-fees date by year (best family member) | ≤2020: 15 · 2021: 13 · 2022: 22 · 2023: 27 · 2024: 47 · 2025: 50 · 2026: 14 |
| stablecoin series | 2017-11-29 → 2026-10-08, daily |
Reading: for the 2021–2023 formation dates, usable fundamentals exist for well under a quarter of eligible names, and
the `has_fundamentals` flag will itself correlate with age and size. The assumed pipeline is therefore expected to be
dominated by the verified features plus that flag; its enrichment numbers are reported, its outcome is subordinate by
the frozen rule, and it can only generate a round-4 hypothesis.

## 5. Excluded for lack of a point-in-time source
Tokenomics (unlock schedules, supply changes), catalysts, and point-in-time market cap outside `rev_yield`.

## 6. What happens after this manifest is frozen
The computation module implements exactly these definitions with a test per feature on synthetic bars (look-ahead
proof: a spike in the bar opening at the formation close changes nothing); the DeFiLlama backfill is loaded with
`available_at` NULL and the lag rule applied in code; the shuffled-label negative control runs with the real pipeline.
Only then are labels computed, once, and the table sent unchanged.

## Questions for the reviewer (one word each)
1. Verified feature list and NaN-ineligibility rule — accept?
2. Assumed family rule (symbol + gecko_id; unique-symbol fallback) and availability rule (D+7 and ≥ listedAt) — accept?
3. Fundamentals NaN → 0 with an explicit `has_fundamentals` feature — accept, or drop names without fundamentals from the assumed pipeline (smaller, biased population)?
4. Freeze Stage 0?

# Phase 4 round 3 — Stage 0 feature manifest, DRAFT v2 (after review R-AG; NO feature value, label or model output exists)

Changes from v1 **[R-AG]**: (1) `breadth_ctx` denominator = the pre-feature candidate set; 91-closes note; (2) no symbol-only
fallback — identity chain Coinbase name → CoinGecko id → DeFiLlama family incl. parent children, slug set frozen in the
audit file, audit rerun (111 usable of 480); (3) per-feature missingness indicators with training-only mean imputation,
`stable_supply_30` fails the month closed, `has_family` kept as an extra indicator.

Governed by the frozen round-3 pre-registration v3 (R-AE). Machine-readable twin: `desk-loop/bt/round3_manifest.json`
(definitions only; the computation module is written after this manifest is frozen). Availability audit (read-only,
nothing stored): `docs/desk/PHASE4-ROUND3-STAGE0-AUDIT.json`.

## 1. Formation and eligibility (restated from v3, mechanical detail added)
First decision close of each UTC month 2021-03 → 2025-11 (57 dates). **Pre-feature candidate set** at a close: listed per
`universe_history` (later-delisted names included), ≥ 90 contiguous completed bars ending at that close, 3-day median
dollar volume ≥ $250k, not in the round-1 exclusion map, and an executable open exists after the close. Dollar volume =
close × volume per bar. This set is the denominator of `breadth_ctx` and the stratification population; the verified
NaN filter (§2) is applied after it and its removals are counted. Note **[R-AG]**: `ret_90` / `rs_btc_90` need 91 closes,
so a name with exactly 90 bars enters the candidate set and is counted as verified-feature-ineligible that month.

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
| breadth_ctx | share of the month's PRE-FEATURE candidate set with close[−1] > own SMA50 (denominator fixed before any feature NaN filter; same value for every name) **[R-AG]** | 50 |
NaN rule: any NaN verified feature ⇒ the name is verified-feature-ineligible at that date (counted and reported); no
imputation; `breadth_ctx` and the strata are computed on the pre-feature candidate set, never on the post-filter set.
Standardisation: mean/std fitted on training months only, per pipeline.

## 3. Assumed pipeline — adds 4 fundamental features + 1 market-context + 5 indicators from backfilled DeFiLlama history, evidence class `assumed_availability`
**Identity and family rule (frozen; resolved once; slug set stored in `PHASE4-ROUND3-STAGE0-AUDIT.json`; never remapped) [R-AG]:**
Coinbase's currency name for the symbol → the unique CoinGecko coin with the same symbol AND the same normalised name
(none or several ⇒ no family; no symbol-only fallback, no guessing) → DeFiLlama child-level protocols whose `gecko_id` is
that CoinGecko id, plus every child of a parentProtocol whose `gecko_id` is that id. Parents are never summed themselves,
only child-level `/protocols` entries, so a parent and its children are never double-counted. `token_map.gecko_id` is not
used: it was derived from DeFiLlama's own records, so matching on it was circular (that is how v1 produced
WIF→world-is-flat).
**Availability rule:** a family value dated D is usable from the decision close of D+7, and only for D ≥ the family's
earliest `listedAt`; a family with no `listedAt` on any member is unusable (strict default; alternative in Q2).
| feature | formula | endpoint |
|---|---|---|
| fees_growth_30 | Σ fees(D−29..D) / Σ fees(D−59..D−30) − 1 (family sum) | summary/fees/{slug}?dataType=dailyFees |
| rev_growth_30 | same on daily revenue | summary/fees/{slug}?dataType=dailyRevenue |
| rev_yield | 12 × Σ revenue(D−29..D) / market cap at D (DeFiLlama mcap; NaN if absent) | protocol/{slug} |
| tvl_change_30 | tvl[D]/tvl[D−30] − 1 (family sum) | protocol/{slug} |
| stable_supply_30 | global stablecoin circulating USD[D]/[D−30] − 1 (same for every name); **missing ⇒ the formation month fails closed for the assumed pipeline** | stablecoins.llama.fi/stablecoincharts/all |
| fees_growth_30_missing, rev_growth_30_missing, rev_yield_missing, tvl_change_30_missing | 1 if that feature is NaN at D, else 0 — one indicator per feature, because missingness differs by field | — |
| has_family | 1 if the frozen audit resolves a usable family for the symbol, else 0 (additional indicator, never a replacement for the per-feature flags) | — |
NaN rule **[R-AG]**: each fundamental feature NaN ⇒ training-only mean imputation (standardised 0) with its own
missingness indicator; all means and stds estimated from observed values in training months only; the global
`stable_supply_30` is never imputed.

## 4. Availability audit under the frozen identity chain (2026-10-09, read-only)
| | |
|---|---|
| universe names (excl. map) | 480 |
| no unique CoinGecko identity (no Coinbase record, or 0 / ≥ 2 CoinGecko coins with the same symbol and name) | 123 |
| identity but no DeFiLlama protocol or parent with that gecko_id | 145 |
| family resolved but no `listedAt` on any member (unusable under the strict rule) | 101 (incl. BTC, LDO: the oldest protocols; DeFiLlama began stamping `listedAt` on 2021-10-12, so these predate stamping) |
| **families usable (strict)** | **111**, of which 83 with a fees module, 59 multi-slug (versions/chains summed) |
| usable: earliest `listedAt` by year | 2021: 11 · 2022: 23 · 2023: 25 · 2024: 18 · 2025: 20 · 2026: 14 |
| usable: earliest daily-fees date by year | ≤2020: 7 · 2021: 6 · 2022: 9 · 2023: 15 · 2024: 22 · 2025: 20 · 2026: 2 · none: 2 |
| stablecoin series | 2017-11-29 → 2026-10-08, daily, complete |
Reading: the assumed pipeline has fundamentals for 111 of 480 names, and for the 2021–2022 formation dates for fewer
than 35 of them. It is a verified-features model plus a sparse fundamentals overlay; the frozen subordination stands.
If the reviewer accepts the stamping-date floor (Q2), the usable count rises to 212 with availability from 2021-10-12.

## 5. Excluded for lack of a point-in-time source
Tokenomics (unlock schedules, supply changes), catalysts, and point-in-time market cap outside `rev_yield`.

## 6. What happens after this manifest is frozen
The computation module implements exactly these definitions with a test per feature on synthetic bars (look-ahead
proof: a spike in the bar opening at the formation close changes nothing); the DeFiLlama backfill is loaded with
`available_at` NULL and the lag rule applied in code; the shuffled-label negative control runs with the real pipeline.
Only then are labels computed, once, and the table sent unchanged.

## Questions for the reviewer — v1 answers R-AG (Revise ×3 / Not yet) applied above
1. `breadth_ctx` on the pre-feature candidate set; 91-closes note; NaN filter after the candidate set — accept?
2. Identity chain (Coinbase name → unique CoinGecko symbol+name → DeFiLlama gecko_id incl. parent children; frozen slug set;
   no fallback) — accept? And for the 101 families with no `listedAt`: keep them unusable (strict), or set their
   availability start to 2021-10-12, the date DeFiLlama began stamping `listedAt` (they were listed before it)?
3. Per-feature missingness indicators + training-only mean imputation, `stable_supply_30` fails closed, `has_family` kept — accept?
4. Freeze Stage 0 v2?

# Phase 5 — BTC accumulation policy. Pre-registration DRAFT v1 (for independent review before any code or result)

Decision taken 2026-10-11 after the Phase 4 close-out (R-AJ): the trading-rule path is closed; the next question matches
the structural edge. **Question:** given a stream of mined BTC (produced below market price) and a stream of cash, which
accumulation policy produces the most BTC-denominated and USD-denominated wealth over a 5-year horizon without
catastrophic loss, versus the benchmark of simply holding every mined coin? Governance unchanged: pre-registered,
independently reviewed, frozen, run once, table sent unchanged; `research_accepted` never means `trade_approved`; only
Jacob moves money. The output of this phase is a **policy comparison**, never a trade signal.

## 1. Inputs (declared by Jacob before the freeze; they are parameters, not tunables; the study reports sensitivity to each)
| input | symbol | status |
|---|---|---|
| mined BTC per month | `m_btc` | TO BE DECLARED (current fleet; held constant, with a ±30% sensitivity) |
| all-in production cost per BTC (USD) | `c_btc` | TO BE DECLARED (electricity + hosting + depreciation share) |
| cash contribution per month (USD) | `m_cash` | TO BE DECLARED (may be 0) |
| required operating cash reserve (months of fixed cost) | `R` | TO BE DECLARED (default 6) |
| tax treatment (US person) | `τ` | mined BTC = ordinary income at receipt (fair value), later sale = capital gain/loss on the difference; frozen rates: short-term 37%, long-term 20%; sensitivity at 0% to isolate the policy effect |
| starting state | | 0 BTC, cash = R months of fixed cost, at the first bar of the test span |

## 2. Data
- BTC daily bars from the frozen snapshot (data_hash `8df7990c93dcc632`, 2020-03-08 → 2026-10-01), completed bars only.
- Fear & Greed point-in-time series (`market_sentiment_daily`, `available_at` rule): historical rows under the declared
  D+1 assumed-availability lag (`evidence_class = assumed_availability`, as accepted R-X); live rows verified. Used only
  by the fear-weighted policies; their outcome carries the assumed label on the historical span.
- Costs: Kraken canonical 0.50%/side on every sale or purchase; ×1.25 stress; severe 0.95%.
- No alt data; no fundamentals; no catalysts.

## 3. Policies (frozen; ≤ 4 grid points each; nothing added after results)
| # | policy | rule each month at the first completed close | grid |
|---|---|---|---|
| H | **HODL (benchmark)** | keep every mined coin; cash contributions buy BTC at the next open; never sell; reserve R kept in cash first | — |
| P1 | fixed sweep (architecture H-SWEEP-B) | sell a fixed share `s` of the month's production for cash; cash above reserve buys BTC only when price < SMA200 | s ∈ {0.25, 0.50} |
| P2 | trend hedge | hold production while close > SMA200; when close < SMA200 sell share `s` of holdings above reserve into cash; buy back fully at the next close > SMA200; one switch per month | s ∈ {0.50, 1.00} |
| P3 | drawdown ladder | never sell; hold cash contributions and swept production in reserve; deploy tranches of 25% of excess cash at drawdown-from-ATH ≥ {20%, 35%, 50%, 65%} (one tranche per level per cycle) | tranche levels fixed |
| P4 | fear-weighted sweep (H-SWEEP-A/C hybrid; assumed-availability on history) | convert excess cash to BTC at a monthly rate: 1× base at F&G 50, 2× at ≤ 35, 4× at ≤ 25, 0.5× at ≥ 75; a 90-day time cap releases one tranche regardless | base rate ∈ {5%, 10%} of excess cash per month |
Sizing is proportional to the inputs, so results are reported per 1 BTC/month and per $1,000/month and scale linearly.

## 4. Evaluation (frozen)
- **Historical path:** 2020-03 → 2026-10 on the frozen snapshot, every policy from the same starting state; reported.
- **Resampled paths (the verdict):** 2,000 block-bootstrap paths of BTC daily returns (block 60 bars) with the F&G
  series resampled jointly in the same blocks (keeps the fear/price dependence), 5-year horizon, seed 7.
- Metrics per policy, per path: terminal BTC held, terminal USD wealth (BTC at terminal price + cash, after taxes),
  maximum drawdown of USD wealth, months of forced selling (reserve breached), BTC sold in total.
- Verdict statistics: median terminal USD wealth; 5th-percentile terminal USD wealth; median terminal BTC; P(≥ 5 BTC)
  per 1 BTC/month of production; maximum drawdown median; forced-selling probability.
- Walk-forward is not applicable to a policy study; instead every grid value is reported (no selection) and the
  pre-registered falsifier below is applied to each grid point separately; the number of grid points is the trial count.

## 5. Falsifier (frozen)
A policy **beats HODL** only if, on the resampled paths, ALL hold at the canonical cost and the frozen tax rates:
1. median terminal USD wealth ≥ 1.05 × HODL's;
2. 5th-percentile terminal USD wealth ≥ HODL's (never worse in the tail);
3. median maximum drawdown of USD wealth ≤ 0.85 × HODL's (a real reduction, not a rounding);
4. median terminal BTC ≥ 0.90 × HODL's (it may not quietly convert the stack to cash);
5. the same four hold under ×1.25 costs;
6. the same four hold on the historical path OR the policy's historical shortfall versus HODL is < 10%.
Anything less ⇒ the policy is `rejected`; the benchmark stands. Outcomes per policy: `beats_hodl` / `rejected` /
`inconclusive (reason)`. No `research_accepted` is issued by this phase; a `beats_hodl` policy enters a 12-month
live shadow run on real mined coins before anything is proposed for approval.

## 6. Reporting
Per policy and grid point: the six statistics above at canonical / ×1.25 / severe costs and at τ = frozen / 0%;
the historical path table; sensitivity to `m_btc` ±30% and `c_btc` ±30%; manifest with data_hash, F&G hash and
evidence class, inputs, seeds, trial count. Nothing to `research_runs` before review.

## 7. Not in this phase
Alts; leverage; shorts; any prediction model; any rule not listed in §3; mining-fleet decisions (hashrate, hosting).

## Questions for the reviewer (one word each)
1. The policy set (HODL, fixed sweep, trend hedge, drawdown ladder, fear-weighted sweep) and grids — accept?
2. The resampled-path verdict with block 60, 2,000 paths, joint F&G resampling, and the six falsifier conditions — accept?
3. Tax modelling as frozen rates with a 0% sensitivity — accept, or require a different treatment?
4. Freeze v1 once Jacob declares the four inputs?

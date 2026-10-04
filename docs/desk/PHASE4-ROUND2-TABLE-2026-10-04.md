# Phase 4 round 2 table — 2026-10-04 (FROZEN v2, R-X; screening only; nothing in research_runs)

data_hash `8df7990c93dcc632` · universe_hash `64e00348d99bb713` · membership_hash `99c437c3e40dbb57` · trials 176

| candidate | class | evidence | episodes/trades | OOS cont. | ×1.25 | severe | maxDD | PF | thirds | scale | boundary | falsifier | outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A_btc_trend | S | — | 26 | -36.6% | -40.6% | -49.8% | -63.3% | 0.65 | ✗ | ✓ | ✓ | ✗ | **historical_rejected** — oos_positive, positive_x1.25, thirds_2_of_3, positive_years>=2, ex_top3_trades>50%, falsifier |
| B_momentum_floor | X | — | 97 | -35.8% | -37.2% | -41.0% | -45.6% | 0.7 | ✗ | ✓ | ✓ | ✓ | **historical_rejected** — oos_trades 97 < 100 |
| C_fear_greed__verified | S | verified | 0 | +0.0% | +0.0% | +0.0% | +0.0% | — | ✗ | ✓ | ✓ | ✗ | **inconclusive** — F&G coverage share 0.00 / longest gap 1981 d (verified) |
| C_fear_greed | S | assumed_availability | 10 | -58.5% | -59.6% | -62.4% | -77.7% | 0.33 | ✗ | ✓ | ✓ | ✗ | **historical_rejected** — oos_positive, positive_x1.25, thirds_2_of_3, ex_top3_trades>50%, falsifier |
| btc_bh_100pct | benchmark | — | 1 | +22.6% | — | — | -76.7% | — | — | — | — | — | n/a |
| btc_bh_10pct_slot | benchmark | — | 1 | +2.3% | — | — | -11.1% | — | — | — | — | — | n/a |
| cash | benchmark | — | 0 | +0.0% | — | — | +0.0% | — | — | — | — | — | n/a |
| breakout20 | negative_control | — | 331 | -64.9% | — | — | -86.4% | — | — | — | ✓ | — | n/a |

## Booleans, falsifiers, provenance

- **A_btc_trend** (post-Round-1 decomposition hypothesis (same SMA family and grid as the rejected broad-alt sma_trend, restricted to BTC)): oos_positive=F, positive_x1.25=F, thirds_2_of_3=F, positive_years>=2=F, scale_invariant=T, boundary_dependency_ok=T, ex_top3_trades>50%=F; falsifier {'ok': False, 'R_A': -0.36577572759904364, 'R_BH': 0.2260823394111111, 'DD_A': -0.6327420699406245, 'DD_BH': -0.7667059828725817, 'beats_return': False, 'partial_clause': False}
  - benchmark_btc_bh_100: {'total_return': 0.2260823394111111, 'max_drawdown': -0.7667059828725817, 'trades': 1}
  - sensitivity_10_slot: {'total_return': -0.017783525702330216, 'max_drawdown': -0.08565181600318061, 'trades': 26, 'profit_factor': 0.8714508865523645}
  - stale_marks: 0
  - delisting: {'exposure_pnl_share': 0.0, 'exposure_trade_share': 0.0, 'triggered': False, 'canonical_ok': True}
- **B_momentum_floor** (post-Round-1 response (rejected momentum_top lost through 2022; the breadth cash floor is the hypothesis)): oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=F, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=T, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T; falsifier {'ok': True, 'checks': {'higher_return': True, 'smaller_drawdown': True, 'higher_profit_factor': True}, 'twin': {'total_return': -0.5461536094785777, 'max_drawdown': -0.5678670019423957, 'trades': 164, 'profit_factor': 0.6524055994212183}}
  - sensitivity: {'cap_0.95': {'total_return': -0.33930873396821293, 'max_drawdown': -0.4386508258161338, 'trades': 97, 'profit_factor': 0.7022062584146344}, 'cap_0.90': {'total_return': -0.32097942808199564, 'max_drawdown': -0.42080930615154555, 'trades': 97, 'profit_factor': 0.7049405654258483}}
  - stale_marks: 0
  - delisting: {'exposure_pnl_share': 0.027156603459139787, 'exposure_trade_share': 0.030927835051546393, 'triggered': False, 'canonical_ok': True}
- **C_fear_greed__verified** (architecture H-SWEEP-A as a hypothesis; written after round 1, so screening status applies): oos_positive=F, positive_x1.25=F, thirds_2_of_3=F, positive_years>=2=F, scale_invariant=T, boundary_dependency_ok=T, ex_top3_trades>50%=F; falsifier {'ok': False, 'horizon': 90, 'signals': {'n': 0, 'mean': None, 'hit': None}, 'base_rate': {'n': 1945, 'mean': 0.057784886776817056, 'hit': 0.5167095115681234}}
  - sensitivity_10_slot: {'total_return': 0.0, 'max_drawdown': 0.0, 'trades': 0, 'profit_factor': None}
  - sensitivity_hold_30: {'total_return': 0.0, 'max_drawdown': 0.0, 'trades': 0, 'profit_factor': None}
  - coverage: {'days': 1981, 'usable': 0, 'share': 0.0, 'longest_gap_days': 1981, 'evidence_class': 'verified', 'unusable_rows': 3161, 'inconclusive': True, 'rule': 'inconclusive if share < 0.8 or any contiguous gap > 30 days'}
  - event_study_all_fear_days: {'n_days': 0, 'mean': None, 'hit': None, 'note': 'overlapping fear days are correlated; descriptive'}
  - signals: {'executed_entries': 0}
  - stale_marks: 0
  - delisting: {'exposure_pnl_share': 0.0, 'exposure_trade_share': 0.0, 'triggered': False, 'canonical_ok': True}
- **C_fear_greed** (architecture H-SWEEP-A as a hypothesis; written after round 1, so screening status applies): oos_positive=F, positive_x1.25=F, thirds_2_of_3=F, positive_years>=2=T, scale_invariant=T, boundary_dependency_ok=T, ex_top3_trades>50%=F; falsifier {'ok': False, 'horizon': 90, 'signals': {'n': 11, 'mean': -0.02273681214598192, 'hit': 0.36363636363636365}, 'base_rate': {'n': 1945, 'mean': 0.057784886776817056, 'hit': 0.5167095115681234}}
  - sensitivity_10_slot: {'total_return': -0.055789718130576094, 'max_drawdown': -0.11701177570797106, 'trades': 11, 'profit_factor': 0.48861696228503637}
  - sensitivity_hold_30: {'total_return': -0.6618826367784721, 'max_drawdown': -0.7791885782378016, 'trades': 25, 'profit_factor': 0.43652943370316494}
  - coverage: {'days': 1981, 'usable': 1980, 'share': 0.9994952044422009, 'longest_gap_days': 1, 'evidence_class': 'assumed_availability', 'unusable_rows': 0, 'inconclusive': False, 'rule': 'inconclusive if share < 0.8 or any contiguous gap > 30 days'}
  - event_study_all_fear_days: {'n_days': 263, 'mean': 0.01567331784986908, 'hit': 0.42585551330798477, 'note': 'overlapping fear days are correlated; descriptive'}
  - signals: {'executed_entries': 11}
  - stale_marks: 0
  - delisting: {'exposure_pnl_share': 0.0, 'exposure_trade_share': 0.0, 'triggered': False, 'canonical_ok': True}

## Per regime state (filter OFF, descriptive)

- **A_btc_trend**: risk_on: 4 trades, P&L +3012; neutral: 6 trades, P&L -1921; risk_off: 15 trades, P&L -1688; unknown: 1 trades, P&L -3061
- **B_momentum_floor**: risk_on: 45 trades, P&L +1999; neutral: 11 trades, P&L -359; risk_off: 38 trades, P&L -5345; unknown: 3 trades, P&L +130
- **C_fear_greed__verified**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 0 trades, P&L +0; unknown: 0 trades, P&L +0
- **C_fear_greed**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 11 trades, P&L -5852; unknown: 0 trades, P&L +0

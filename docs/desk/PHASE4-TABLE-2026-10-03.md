# Phase 4 tournament table — 2026-10-03 (FROZEN rules v2, R-S FINAL; nothing in research_runs)

data_hash `8df7990c93dcc632` · universe_hash `64e00348d99bb713` · membership_hash `99c437c3e40dbb57` · monthly rankings 77

| candidate | role | trials | OOS chained | OOS continuous | cont. ×1.25 | maxDD cont. | trades | PF | thirds | scale | delist | boundary | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sma_trend | candidate | 44 | -86.4% | -69.6% | -71.4% | -89.2% | 289 | 0.65 | ✗ | ✓ | ✓ | ✓ | rejected |
| momentum_top | candidate | 88 | -98.2% | -91.0% | -91.5% | -93.7% | 231 | 0.43 | ✗ | ✓ | ✓ | ✓ | rejected |
| mean_reversion | candidate | 88 | -96.6% | -94.9% | -95.9% | -96.3% | 1163 | 0.73 | ✗ | ✓ | ✓ | ✓ | rejected |
| breakout20 | negative_control | 22 | -98.2% | -64.9% | -67.2% | -86.4% | 331 | 0.65 | ✗ | ✓ | ✓ | ✗ | n/a (negative_control) |
| buy_and_hold_btc | benchmark | 22 | +10.2% | +2.3% | +2.2% | -11.1% | 1 | inf | ✗ | ✓ | ✓ | ✗ | n/a (benchmark) |
| cash | benchmark | 22 | +0.0% | +0.0% | +0.0% | +0.0% | 0 | None | ✗ | ✓ | ✓ | ✓ | n/a (benchmark) |

## Advancement booleans

- **sma_trend**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **momentum_top**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **mean_reversion**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **breakout20**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=T, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=F
- **buy_and_hold_btc**: oos_positive=T, survives_fees_x1.25=T, survives_fees_x1.25_oos=T, oos_trades>=100=F, thirds_2_of_3=F, scale_invariant=T, symbols>=min=F, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=F
- **cash**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=F, thirds_2_of_3=F, scale_invariant=T, symbols>=min=F, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T

## Per regime state (filter OFF, labels descriptive)

- **sma_trend**: risk_on: 44 trades, P&L -160; neutral: 74 trades, P&L -3686; risk_off: 161 trades, P&L -4478; unknown: 10 trades, P&L +1364
- **momentum_top**: risk_on: 59 trades, P&L -5698; neutral: 31 trades, P&L -1626; risk_off: 131 trades, P&L -2929; unknown: 10 trades, P&L +1148
- **mean_reversion**: risk_on: 229 trades, P&L -2696; neutral: 206 trades, P&L -1673; risk_off: 706 trades, P&L -6246; unknown: 22 trades, P&L +1129
- **breakout20**: risk_on: 62 trades, P&L +30; neutral: 56 trades, P&L -1407; risk_off: 207 trades, P&L -4359; unknown: 6 trades, P&L -756
- **buy_and_hold_btc**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 0 trades, P&L +0; unknown: 1 trades, P&L +226
- **cash**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 0 trades, P&L +0; unknown: 0 trades, P&L +0

## Sensitivities (continuous OOS)

- sma_trend / cap_0.95: return -71.1%, maxDD -89.2%, trades 304, PF 0.6342169556419065
- sma_trend / cap_0.90: return -73.6%, maxDD -89.8%, trades 320, PF 0.6057439493057971
- sma_trend / severe_costs: return -76.5%, maxDD -91.4%, trades 288, PF 0.6057993920184203
- momentum_top / cap_0.95: return -91.0%, maxDD -93.6%, trades 242, PF 0.4237282954119304
- momentum_top / cap_0.90: return -91.4%, maxDD -94.0%, trades 252, PF 0.40421134116599633
- momentum_top / severe_costs: return -92.9%, maxDD -94.9%, trades 229, PF 0.38989575220704714
- mean_reversion / cap_0.95: return -94.4%, maxDD -96.0%, trades 1195, PF 0.7366791757119723
- mean_reversion / cap_0.90: return -93.3%, maxDD -95.1%, trades 1196, PF 0.7352024107034705
- mean_reversion / severe_costs: return -98.2%, maxDD -98.6%, trades 1163, PF 0.6623748871290286

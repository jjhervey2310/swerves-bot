# Phase 4 tournament table — 2026-10-03 (FROZEN rules v2, R-S FINAL; nothing in research_runs)

data_hash `8df7990c93dcc632` · universe_hash `64e00348d99bb713` · membership_hash `99c437c3e40dbb57` · monthly rankings 77

| candidate | role | trials | OOS chained | OOS continuous | cont. ×1.25 | maxDD cont. | trades | PF | thirds | scale | delist | boundary | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sma_trend | candidate | 44 | -71.3% | -80.5% | -81.7% | -92.9% | 305 | 0.53 | ✗ | ✓ | ✓ | ✓ | rejected |
| momentum_top | candidate | 88 | -90.7% | -90.5% | -90.9% | -91.8% | 219 | 0.39 | ✗ | ✓ | ✓ | ✓ | rejected |
| mean_reversion | candidate | 88 | -90.9% | -91.3% | -92.9% | -93.7% | 1064 | 0.75 | ✗ | ✓ | ✓ | ✓ | rejected |
| breakout20 | negative_control | 22 | -57.6% | -64.9% | -67.2% | -86.4% | 331 | 0.65 | ✗ | ✓ | ✓ | ✓ | n/a (negative_control) |
| buy_and_hold_btc | benchmark | 22 | +10.2% | +2.3% | +2.2% | -11.1% | 1 | inf | ✗ | ✓ | ✓ | ✗ | n/a (benchmark) |
| cash | benchmark | 22 | +0.0% | +0.0% | +0.0% | +0.0% | 0 | None | ✗ | ✓ | ✓ | ✓ | n/a (benchmark) |

## Advancement booleans

- **sma_trend**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **momentum_top**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **mean_reversion**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **breakout20**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=T, thirds_2_of_3=F, scale_invariant=T, symbols>=min=T, not_single_year=T, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T
- **buy_and_hold_btc**: oos_positive=T, survives_fees_x1.25=T, survives_fees_x1.25_oos=T, oos_trades>=100=F, thirds_2_of_3=F, scale_invariant=T, symbols>=min=F, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=F
- **cash**: oos_positive=F, survives_fees_x1.25=F, survives_fees_x1.25_oos=F, oos_trades>=100=F, thirds_2_of_3=F, scale_invariant=T, symbols>=min=F, not_single_year=F, not_top3_dependent=F, delisting_canonical=T, boundary_dependency_ok=T

## Per regime state (filter OFF, labels descriptive)

- **sma_trend**: risk_on: 60 trades, P&L -2012; neutral: 77 trades, P&L -2280; risk_off: 158 trades, P&L -5123; unknown: 10 trades, P&L +1364
- **momentum_top**: risk_on: 48 trades, P&L -3114; neutral: 38 trades, P&L -1759; risk_off: 128 trades, P&L -4249; unknown: 5 trades, P&L +69
- **mean_reversion**: risk_on: 201 trades, P&L -2313; neutral: 192 trades, P&L -2355; risk_off: 649 trades, P&L -5590; unknown: 22 trades, P&L +1129
- **breakout20**: risk_on: 62 trades, P&L +30; neutral: 56 trades, P&L -1407; risk_off: 207 trades, P&L -4359; unknown: 6 trades, P&L -756
- **buy_and_hold_btc**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 0 trades, P&L +0; unknown: 1 trades, P&L +226
- **cash**: risk_on: 0 trades, P&L +0; neutral: 0 trades, P&L +0; risk_off: 0 trades, P&L +0; unknown: 0 trades, P&L +0

## Sensitivities (continuous OOS)

- sma_trend / cap_0.95: return -80.4%, maxDD -92.6%, trades 320, PF 0.5215141914021549
- sma_trend / cap_0.90: return -82.5%, maxDD -93.2%, trades 337, PF 0.4889447724018559
- sma_trend / severe_costs: return -85.1%, maxDD -94.6%, trades 304, PF 0.4860581033004115
- momentum_top / cap_0.95: return -91.5%, maxDD -92.6%, trades 230, PF 0.3791988049347412
- momentum_top / cap_0.90: return -90.6%, maxDD -91.8%, trades 238, PF 0.385703015342684
- momentum_top / severe_costs: return -92.3%, maxDD -93.2%, trades 219, PF 0.3591094270775062
- mean_reversion / cap_0.95: return -89.6%, maxDD -92.5%, trades 1095, PF 0.7649949263289058
- mean_reversion / cap_0.90: return -88.0%, maxDD -91.3%, trades 1096, PF 0.7646310650007659
- mean_reversion / severe_costs: return -96.6%, maxDD -97.4%, trades 1063, PF 0.6687019700675217

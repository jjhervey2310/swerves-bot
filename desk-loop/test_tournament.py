"""Phase 4 tournament tests — frozen pre-registration v2 (R-S FINAL)."""
import math, unittest
from market_time import DAY
from bt.data import Bar, Market
from bt import tournament as T, strategies, regime
from bt.engine import Order, run
from bt_costs import CostModel

T0 = 1_600_000_000 - 1_600_000_000 % DAY
COSTS = CostModel(0.001, 0.001, venue="t", tier="t")


def bars_from(closes, t0=T0, vol=1.0):
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        out.append(Bar(t0 + i * DAY, o, max(o, c) * 1.001, min(o, c) * 0.999, c, vol if not callable(vol) else vol(i)))
    return out


def path(n, drift=0.001, phase=0.0, start=100.0):
    return [start * math.exp(drift * i) * (1 + 0.02 * math.sin(i / 5 + phase)) for i in range(n)]


def mkt(n=500, names=30, vols=None, extra=None):
    bars = {"BTC": bars_from(path(n), vol=1000.0)}; L = {"BTC": (T0, None)}
    for j in range(names):
        v = (vols or {}).get(f"S{j}", 10.0 + j)                    # dollar volume ranks S29 > S28 > …
        bars[f"S{j}"] = bars_from(path(n, 0.0012, j), vol=v); L[f"S{j}"] = (T0, None)
    for k, (b, l) in (extra or {}).items():
        bars[k] = b; L[k] = l
    return Market(bars, L)


def dec(k): return T0 + (k + 1) * DAY


class Universe(unittest.TestCase):
    def test_top20_by_dollar_volume_excluding_map_and_short_history(self):
        m = mkt(extra={"USDC": (bars_from([1.0] * 500, vol=1e9), (T0, None)), "NEW": (bars_from(path(30), t0=T0 + 470 * DAY, vol=1e9), (T0 + 470 * DAY, None))})
        u = T.monthly_universe(m)
        last = u.at(dec(499))
        self.assertEqual(len(last), 20); self.assertNotIn("USDC", last); self.assertNotIn("NEW", last)   # excluded; < 90 bars
        self.assertEqual(sorted(last), sorted({"BTC"} | {f"S{j}" for j in range(11, 30)}))                 # BTC (1000×) + top 19 names

    def test_rankings_only_on_month_change_and_frozen_between(self):
        u = T.monthly_universe(mkt())
        self.assertGreaterEqual(len(u.times), 10)
        import datetime as dt
        months = [dt.datetime.fromtimestamp(t - 1, dt.timezone.utc).strftime("%Y-%m") for t in u.times]
        self.assertEqual(len(months), len(set(months)))                                                     # one ranking per month
        self.assertIs(u.at(u.times[3] + 5 * DAY), u.members[3])                                             # frozen until next ranking

    def test_ties_by_symbol_and_gap_in_window_disqualifies(self):
        same = path(500, 0.0012, 0.0)                                                                          # identical prices AND volumes → exact ties
        m = Market({"BTC": bars_from(path(500), vol=1000.0), **{f"S{j}": bars_from(same, vol=10.0) for j in range(25)}}, {"BTC": (T0, None), **{f"S{j}": (T0, None) for j in range(25)}})
        u = T.monthly_universe(m)
        self.assertEqual(sorted(u.at(dec(499))), sorted(["BTC"] + sorted(f"S{j}" for j in range(25))[:19]))
        bars = dict(m.bars); bars["S0"] = [b for b in bars["S0"] if b.t != T0 + 460 * DAY]                   # gap inside the 90-bar window
        self.assertNotIn("S0", T.monthly_universe(Market(bars, m.listings)).at(dec(499)))

    def test_dropped_name_keeps_its_exit_rule_but_gets_no_new_entry(self):
        m = mkt(n=400)
        u = T.monthly_universe(m, top=3)
        held = {"n": 0}
        def strat(view, pf):
            if view.t == dec(100): return [Order("S0", "buy")]
            if "S0" in pf.positions and "S0" not in view.universe() and view.t == dec(200): held["n"] += 1; return [Order("S0", "sell")]
            return []
        r = run(m, strat, COSTS, universe=u)
        self.assertEqual(held["n"], 1); self.assertEqual([t.symbol for t in r["trades"]], ["S0"])
        self.assertNotIn("S0", m.as_of(dec(200), None, u).universe())
        s = strategies.sma_trend(None, 5, 20)
        view = m.as_of(dec(300), None, u)
        class PF: positions = {"S0": object()}
        self.assertIn("S0", strategies._scope(None, view, PF()))                                             # held name still evaluated for exit


class Continuous(unittest.TestCase):
    def test_no_boundary_liquidation_and_switch_does_not_force_close(self):
        m = mkt(n=600, names=5)
        picks = [{"test": (dec(300), dec(390)), "params": {"fast": 5, "slow": 20}}, {"test": (dec(390), dec(480)), "params": {"fast": 10, "slow": 40}}]
        c = T.continuous_oos(m, strategies.sma_trend, picks, COSTS, T.SIZING["canonical"], 10_000, None)
        last_t = max(t.exit_t for t in c["trades"])
        self.assertTrue(all(t.exit_t == last_t for t in c["trades"] if t.reason == "eod"))                   # eod only at the very end, never at the fold boundary
        self.assertFalse(any(t.exit_t == dec(390) - DAY and t.reason == "eod" for t in c["trades"]))
        chained = {"total_return": 0.10}
        self.assertTrue(T.boundary_dependency(chained, {"total_return": 0.11}, 3)["ok"])
        self.assertFalse(T.boundary_dependency(chained, {"total_return": -0.01}, 3)["ok"])                  # sign flip
        self.assertFalse(T.boundary_dependency(chained, {"total_return": 0.15}, 3)["ok"])                   # > 20%

    def test_thirds_and_scale_invariance(self):
        eq = [(i, 100 * (1.01 ** i)) for i in range(30)]
        self.assertTrue(T.thirds(eq)["ok"])
        down = [(i, 100 * (0.99 ** i)) for i in range(30)]
        self.assertFalse(T.thirds(down)["ok"])
        self.assertTrue(T.scale_invariance(eq, [(i, 10 * e) for i, e in eq])["ok"])
        self.assertFalse(T.scale_invariance(eq, [(i, e + (1 if i == 5 else 0)) for i, e in eq])["ok"])


class Delisting(unittest.TestCase):
    def test_stress_reprices_delisted_exits_only_when_triggered(self):
        from bt.engine import Trade
        bars = {"BTC": bars_from(path(300), vol=1e6), "DEAD": bars_from(path(200), vol=lambda i: 1e6 if i < 150 else 1.0)}
        m = Market(bars, {"BTC": (T0, None), "DEAD": (T0, T0 + 200 * DAY)})
        dead_exit = Trade("DEAD", T0 + 100 * DAY, T0 + 200 * DAY, 100.0, 120.0, 10.0, 0.2, 200.0, "delisted")
        ok = Trade("BTC", T0 + 10 * DAY, T0 + 50 * DAY, 100.0, 110.0, 10.0, 0.1, 100.0, "signal")
        d = T.delisting_stress(m, [dead_exit, ok], 10_000, 1_000, 0.03)
        self.assertTrue(d["triggered"]); self.assertEqual(d["cases"]["canonical"]["repriced_exits"], 1)
        # last reliable bar is index 150: its 3-day median (bars 148–150) still has two reliable prints; canonical haircut 50%
        px = bars["DEAD"][150].c * 0.5
        self.assertAlmostEqual(d["cases"]["canonical"]["delta_pnl"], 10.0 * (px - 120.0), places=6)
        self.assertLess(d["cases"]["tail"]["adjusted_return"], d["cases"]["mild"]["adjusted_return"])
        small = T.delisting_stress(m, [ok] * 20 + [dead_exit], 10_000, 1_000, 0.03)
        self.assertFalse(small["triggered"]); self.assertTrue(small["canonical_ok"])                        # < 10% share: not triggered → ok by rule


class Table(unittest.TestCase):
    def test_evaluate_emits_all_advancement_booleans_and_per_state(self):
        m = mkt(n=900, names=25)
        u = T.monthly_universe(m); s = regime.compute_series(m)
        rec = T.evaluate(m, "sma_trend", u, s)
        for k in ("oos_positive", "survives_fees_x1.25", "survives_fees_x1.25_oos", "oos_trades>=100", "thirds_2_of_3", "scale_invariant",
                  "symbols>=min", "not_single_year", "not_top3_dependent", "delisting_canonical", "boundary_dependency_ok"):
            self.assertIn(k, rec["advancement"])
        self.assertIn(rec["verdict"], ("research_accepted_pending_review", "rejected", "inconclusive"))
        self.assertEqual(set(rec["per_regime_state"]), set(regime.STATES))
        self.assertTrue(rec["scale"]["ok"])
        self.assertEqual(T.evaluate(m, "cash", u, s)["verdict"], "n/a (benchmark)")
        self.assertEqual(T.CANDIDATES["breakout20"][2], "negative_control")

    def test_frozen_constants(self):
        self.assertAlmostEqual(T.COSTS["canonical"].per_side(), 0.005, places=12); self.assertEqual(T.SIZING["canonical"], {"max_positions": 10, "gross_cap": 1.0})
        self.assertEqual(T.DELIST["canonical"], (10, 0.50)); self.assertEqual(T.MIN_OOS_TRADES, 100)
        self.assertEqual(len(T.CANDIDATES["momentum_top"][1]), 4); self.assertEqual(len(T.CANDIDATES["mean_reversion"][1]), 4)
        self.assertIn("USDT", T.EXCLUDE); self.assertIn("WBTC", T.EXCLUDE)


class UniverseThreading(unittest.TestCase):
    """R-U: parameter selection, OOS, fee stress and robustness must all run on the frozen monthly schedule. A strong
    name OUTSIDE the top-N must not be able to change the selected parameters or the gate."""
    def test_outsider_cannot_influence_selection_or_gate(self):
        from bt import research
        n = 800
        bars = {"BTC": bars_from(path(n), vol=1000.0)}; L = {"BTC": (T0, None)}
        for j in range(3):                                                   # the top-3 universe: BTC + two dull names
            bars[f"S{j}"] = bars_from([100.0] * n, vol=500.0 - j); L[f"S{j}"] = (T0, None)
        # OUT: tiny volume (never top-3) but a perfect trend that sma_trend(5,20) would love
        bars["OUT"] = bars_from(path(n, drift=0.01), vol=0.001); L["OUT"] = (T0, None)
        m = Market(bars, L)
        u = T.monthly_universe(m, top=3)
        self.assertTrue(all("OUT" not in mem for mem in u.members))
        grid = [{"fast": 5, "slow": 20}, {"fast": 50, "slow": 200}]
        with_u = research.walk_forward(m, lambda **kw: strategies.sma_trend(None, **kw), grid, COSTS, 365, 90, universe=u)
        without = research.walk_forward(m, lambda **kw: strategies.sma_trend(None, **kw), grid, COSTS, 365, 90)
        self.assertIn("OUT", without["oos"]["pnl_by_symbol"])                            # the unthreaded run trades the outsider …
        self.assertNotIn("OUT", with_u["oos"]["pnl_by_symbol"])                           # … the frozen-universe run never can
        self.assertNotIn("OUT", with_u["oos_fee_stress"]["pnl_by_symbol"])
        self.assertNotEqual(without["oos"]["total_return"], with_u["oos"]["total_return"])
        rob = research.robustness(m, lambda **kw: strategies.sma_trend(None, **kw), grid[0], COSTS, universe=u)
        self.assertNotIn("OUT", rob["base"]["pnl_by_symbol"]); self.assertNotIn("OUT", rob["fees_x1.25"]["pnl_by_symbol"])
        rec = T.evaluate(m, "sma_trend", u, regime.compute_series(m))
        self.assertNotIn("OUT", rec["oos_chained"]["pnl_by_symbol"]); self.assertNotIn("OUT", rec["pnl_by_symbol_top"])
        self.assertNotIn("OUT", rec["oos_continuous"]["pnl_by_symbol"])

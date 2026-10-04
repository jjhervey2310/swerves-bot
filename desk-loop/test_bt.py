import random, unittest
from market_time import DAY, LookAheadError
from bt_costs import CostModel
from bt.data import Bar, Market, market_from_rows
from bt.engine import Order, run
from bt.metrics import summarize
from bt import research, strategies

T0 = 1_700_000_000 - (1_700_000_000 % DAY)
COSTS = CostModel(0.004, 0.008, "test", "unit", slippage=0.001)


def walk(seed, n=400, start=100.0, drift=0.0005, vol=0.03):
    rng = random.Random(seed); out, px = [], start
    for k in range(n):
        o = px; c = o * (1 + rng.gauss(drift, vol)); h = max(o, c) * (1 + abs(rng.gauss(0, 0.005))); l = min(o, c) * (1 - abs(rng.gauss(0, 0.005)))
        out.append(Bar(T0 + k * DAY, o, h, l, c, 1000 + rng.random() * 500)); px = c
    return out


def market(n=400):
    return Market({"BTC": walk(1, n), "AAA": walk(2, n), "BBB": walk(3, n), "DEAD": walk(4, 150)}, {"BTC": (T0, None), "AAA": (T0, None), "BBB": (T0, None), "DEAD": (T0, T0 + 150 * DAY)})


def mk(bars, listings=None):
    return Market(bars, listings, infer_listings=listings is None)


class AsOf(unittest.TestCase):
    def test_view_hides_incomplete_and_future_bars(self):
        m = market(); v = m.as_of(T0 + 10 * DAY + 3600)       # an hour into day 10
        self.assertEqual(len(v.bars("BTC")), 10)                # days 0..9 only
        with self.assertRaises(LookAheadError):
            v.bar_at("BTC", T0 + 10 * DAY)

    def test_universe_excludes_delisted_and_unlisted(self):
        m = market()
        self.assertIn("DEAD", m.as_of(T0 + 100 * DAY).universe())
        self.assertNotIn("DEAD", m.as_of(T0 + 160 * DAY).universe())

    def test_strategy_cannot_see_decision_bar_future(self):
        seen = {}
        def spy(view, pf):
            seen["max_t"] = max(seen.get("max_t", 0), max(b.t for b in view.bars("BTC"))); return []
        run(market(50), spy, COSTS)
        self.assertEqual(seen["max_t"], T0 + 49 * DAY)         # never a bar at/after the last decision close

    def test_view_holds_no_market_reference(self):
        v = market().as_of(T0 + 10 * DAY)
        self.assertFalse(hasattr(v, "_m"))
        self.assertEqual(set(v.__slots__), {"t", "_bars", "_universe", "_bar_seconds", "_regime"})

    def test_stale_asset_is_not_in_universe(self):
        m = market()
        self.assertNotIn("DEAD", m.as_of(T0 + 149 * DAY + 3 * DAY).universe())   # last bar long gone even before delisting


class Boundary(unittest.TestCase):
    def test_end_t_bounds_information_not_labels(self):
        """A spike in the bar opening exactly at the fold boundary must not change the fit run (R-F #1)."""
        fe = T0 + 100 * DAY
        def mkt(spike):
            bars = walk(5, 200)
            if spike:
                b = bars[100]; bars[100] = Bar(b.t, b.o, b.h * 50, b.l, b.c * 50, b.v)   # the bar that OPENS at fe
            return mk({"AAA": bars, "BTC": walk(1, 200)})
        s = strategies.sma_trend(["AAA"], 5, 20)
        a = run(mkt(False), strategies.sma_trend(["AAA"], 5, 20), COSTS, end_t=fe)
        b = run(mkt(True), strategies.sma_trend(["AAA"], 5, 20), COSTS, end_t=fe)
        self.assertEqual(a["final_cash"], b["final_cash"])
        self.assertTrue(all(t <= fe for t, _ in a["equity"]))

    def test_equity_is_stamped_at_the_close(self):
        r = run(market(10), strategies.cash(), COSTS)
        self.assertEqual(r["equity"][0][0], T0 + DAY)


class Fills(unittest.TestCase):
    def test_stop_is_live_on_the_entry_bar(self):
        bars = [Bar(T0, 100, 101, 99, 100, 1), Bar(T0 + DAY, 100, 125, 80, 120, 1), Bar(T0 + 2 * DAY, 120, 121, 119, 120, 1)]
        m = mk({"X": bars})
        s = lambda view, pf: [Order("X", "buy", stop=90, target=130)] if view.t == T0 + DAY else []
        tr = run(m, s, COSTS)["trades"][0]
        self.assertEqual((tr.entry_t, tr.exit_t, tr.reason), (T0 + DAY, T0 + DAY, "stop"))
        self.assertAlmostEqual(tr.exit_px, 90 * (1 - COSTS.per_side()), places=9)

    def test_order_sequence_does_not_change_holdings(self):
        """Identical same-day buys in normal and reversed order → identical portfolio (R-F #3/#4)."""
        syms = ["AAA", "BBB", "BTC"]
        def strat(order):
            fired = {"n": 0}
            def s(view, pf):
                fired["n"] += 1
                return [Order(x, "buy") for x in order] if fired["n"] == 1 else []
            return s
        a = run(market(30), strat(syms), COSTS, start_cash=10_000, max_positions=2)
        b = run(market(30), strat(list(reversed(syms))), COSTS, start_cash=10_000, max_positions=2)
        self.assertEqual([tr.symbol for tr in sorted(a["trades"], key=lambda x: x.symbol)], [tr.symbol for tr in sorted(b["trades"], key=lambda x: x.symbol)])
        self.assertAlmostEqual(a["final_cash"], b["final_cash"], places=9)
        self.assertEqual(a["no_fills"], 1)                         # 3 signals, 2 slots: one deterministic refusal, recorded
        self.assertEqual([e[1] for e in a["events"] if e[2] == "no_fill"], ["BTC"])   # (priority 0, symbol asc) → BTC loses

    def test_slot_size_scales_with_equity_and_is_all_or_none(self):
        """R-G: same strategy from $10k and $100k → identical normalised equity curves."""
        a = run(market(120), strategies.sma_trend(["AAA", "BBB"], 5, 20), COSTS, start_cash=10_000)
        b = run(market(120), strategies.sma_trend(["AAA", "BBB"], 5, 20), COSTS, start_cash=100_000)
        na = [e / a["start_cash"] for _, e in a["equity"]]; nb = [e / b["start_cash"] for _, e in b["equity"]]
        self.assertEqual(len(na), len(nb))
        self.assertTrue(all(abs(x - y) < 1e-9 for x, y in zip(na, nb)))
        fills = [e for e in a["events"] if e[2] == "fill"]
        self.assertTrue(fills and all(abs(float(e[3]) - 0.1 * eq) < 0.011 for e in fills for eq in [next(v for t, v in a["equity"] if t == e[0])]))

    def test_capital_starvation_is_visible_and_ranked(self):
        s = lambda view, pf: [Order(x, "buy", priority=p) for x, p in (("AAA", 1), ("BBB", 3), ("BTC", 2))] if view.t == T0 + DAY else []
        r = run(market(10), s, COSTS, max_positions=2)
        self.assertEqual([e[1] for e in r["events"] if e[2] == "fill"], ["BBB", "BTC"])
        self.assertEqual([e[1] for e in r["events"] if e[2] == "no_fill"], ["AAA"])

    def test_sells_release_cash_before_same_open_buys(self):
        state = {"n": 0}
        def s(view, pf):
            state["n"] += 1
            if state["n"] == 1: return [Order("AAA", "buy")]
            if state["n"] == 2: return [Order("AAA", "sell"), Order("BBB", "buy")]
            return []
        r = run(market(10), s, COSTS, start_cash=10_000, max_positions=1, gross_cap=0.9)   # one slot (90% of equity): BBB fills only if AAA's sell frees the slot and its cash first
        self.assertEqual({tr.symbol for tr in r["trades"]}, {"AAA", "BBB"})


    def test_buy_fills_next_open_with_costs_and_sell_closes(self):
        m = market(30); fired = {"n": 0}
        def s(view, pf):
            fired["n"] += 1
            if fired["n"] == 1: return [Order("AAA", "buy", tag="t")]
            if fired["n"] == 3: return [Order("AAA", "sell")]
            return []
        r = run(m, s, COSTS)
        tr = r["trades"][0]
        self.assertEqual(tr.entry_t, T0 + 1 * DAY)              # decided at close of day 0, filled day 1 open
        self.assertAlmostEqual(tr.entry_px, m.bars["AAA"][1].o * (1 + COSTS.per_side()), places=9)
        self.assertEqual(tr.exit_t, T0 + 3 * DAY); self.assertEqual(tr.reason, "signal")

    def test_stop_before_target_and_gap_fills_at_open(self):
        bars = [Bar(T0, 100, 101, 99, 100, 1), Bar(T0 + DAY, 100, 101, 99, 100, 1), Bar(T0 + 2 * DAY, 80, 130, 70, 120, 1)]
        m = mk({"X": bars})
        s = lambda view, pf: [Order("X", "buy", stop=90, target=125)] if view.t == T0 + DAY else []
        r = run(m, s, COSTS); tr = r["trades"][0]
        self.assertEqual(tr.reason, "stop")
        self.assertAlmostEqual(tr.exit_px, 80 * (1 - COSTS.per_side()), places=9)   # entry bar: gapped through 90 at the open → stopped at the open

    def test_costs_reduce_pnl(self):
        m = market(60); s = strategies.buy_and_hold(["AAA"])
        free = CostModel(0.0, 0.0, "test", "free")
        self.assertLess(run(m, s, COSTS)["final_cash"], run(m, strategies.buy_and_hold(["AAA"]), free)["final_cash"])


class StrategyHygiene(unittest.TestCase):
    def test_tournament_strategies_do_not_touch_the_market(self):
        import re, inspect
        src = inspect.getsource(strategies)
        self.assertIsNone(re.search(r"\b(market|_m\b|bar_opening_at|_ts|_bars\b)", src), "strategies.py must only use the AsOfView interface")


class FailClosed(unittest.TestCase):
    """R-H: a research loader never infers a universe from bars."""
    def rows(self):
        return [{"symbol": "AAA", "bar_time": T0 + i * DAY, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for i in range(3)]

    def test_market_from_rows_requires_listings_by_default(self):
        with self.assertRaises(ValueError):
            market_from_rows(self.rows())
        self.assertEqual(market_from_rows(self.rows(), infer_listings=True).listings["AAA"][0], T0)

    def test_snapshot_without_listings_is_refused(self):
        import json, tempfile, os
        from bt import load
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "snap.json")
            with open(p, "w") as f: json.dump({"rows": self.rows()}, f)
            with self.assertRaises(ValueError):
                load.load_snapshot(p)
            with open(p, "w") as f: json.dump({"rows": self.rows(), "listings": {"AAA": [T0, None]}}, f)
            self.assertEqual(load.load_snapshot(p).listings["AAA"], (T0, None))

    def test_no_fill_reasons_and_sizing_in_manifest(self):
        s = lambda view, pf: [Order(x, "buy", priority=p) for x, p in (("AAA", 1), ("BBB", 3), ("BTC", 2))] if view.t == T0 + DAY else []
        r = run(market(10), s, COSTS, max_positions=2)
        self.assertEqual(r["no_fill_reasons"], {"slots": 1})
        man = research.manifest("x", {}, market(10), COSTS, "next_open", [], {}, {}, {}, None, sizing=r["sizing"])
        self.assertEqual(man["sizing"]["gross_cap"], 1.0)
        man2 = research.manifest("x", {}, market(10), COSTS, "next_open", [], {}, {}, {}, None, sizing={"rule": "slot", "gross_cap": 0.9, "max_positions": 2})
        self.assertNotEqual(man["config_hash"], man2["config_hash"])


class Research(unittest.TestCase):
    def test_folds_do_not_overlap_fit_and_test(self):
        fs = research.folds(T0, T0 + 400 * DAY, 180, 60)
        self.assertTrue(fs)
        for a, fe, ts, te in fs:
            self.assertEqual(fe, ts); self.assertGreater(te, ts)

    def test_walk_forward_counts_trials_and_reports_oos(self):
        m = market(400)
        wf = research.walk_forward(m, lambda **kw: strategies.sma_trend(["AAA", "BBB"], **kw), [{"fast": 20, "slow": 50}, {"fast": 10, "slow": 40}], COSTS, 180, 60)
        self.assertEqual(wf["trials"], 2 * len(wf["folds"]))
        self.assertIn("total_return", wf["oos"]); self.assertIn("total_return", wf["oos_fee_stress"])
        self.assertLessEqual(wf["oos_fee_stress"]["total_return"], wf["oos"]["total_return"] + 1e-9)   # higher fees never help

    def test_gate_rejects_single_symbol_edge_and_accepts_broad(self):
        bad = {"total_return": 0.5, "symbols_with_profit": 1, "pnl_by_year": {2024: 10, 2025: 5}, "pnl_ex_top": {3: 1}}
        self.assertEqual(research.gate(bad, {"fees_x1.25": {"total_return": 0.3}, "neighbours": []}, 4, oos_stress={"total_return": 0.1})["verdict"], "rejected")
        good = {"total_return": 0.5, "symbols_with_profit": 5, "pnl_by_year": {2024: 10, 2025: 5}, "pnl_ex_top": {3: 12}}
        self.assertEqual(research.gate(good, {"fees_x1.25": {"total_return": 0.3}, "neighbours": []}, 4, oos_stress={"total_return": 0.1})["verdict"], "accepted")
        # R-O: full-sample fee survival alone never passes; OOS fee stress must be positive too, and missing fails
        self.assertEqual(research.gate(good, {"fees_x1.25": {"total_return": 0.3}, "neighbours": []}, 4, oos_stress={"total_return": -0.1})["verdict"], "rejected")
        self.assertFalse(research.gate(good, {"fees_x1.25": {"total_return": 0.3}, "neighbours": []}, 4)["checks"]["survives_fees_x1.25"])
        self.assertEqual(research.gate(None, None, None)["verdict"], "inconclusive")

    def test_manifest_hashes_are_deterministic(self):
        m = market(50)
        a = research.manifest("x", {"k": 1}, m, COSTS, "rule", [], {}, {}, None, {"verdict": "inconclusive"})
        b = research.manifest("x", {"k": 1}, m, COSTS, "rule", [], {}, {}, None, {"verdict": "inconclusive"})
        self.assertEqual((a["config_hash"], a["data_hash"], a["universe_hash"]), (b["config_hash"], b["data_hash"], b["universe_hash"]))
        self.assertNotEqual(a["config_hash"], research.manifest("x", {"k": 2}, m, COSTS, "rule", [], {}, {}, None, {})["config_hash"])

    def test_fingerprint_sees_highs_lows_and_volume(self):
        b1 = walk(9, 20); b2 = list(b1); x = b2[5]; b2[5] = Bar(x.t, x.o, x.h * 1.5, x.l, x.c, x.v)
        self.assertNotEqual(mk({"A": b1}).fingerprint(), mk({"A": b2}).fingerprint())

    def test_monte_carlo_shape(self):
        mc = research.monte_carlo(run(market(300), strategies.buy_and_hold(["AAA", "BBB"]), COSTS), n=50, block=10)
        self.assertLessEqual(mc["terminal_p05"], mc["terminal_p95"]); self.assertLessEqual(mc["mdd_p05"], 0)


if __name__ == "__main__":
    unittest.main()


class Attribution(unittest.TestCase):
    """R-I: trailing stop, fixed-dollar diagnostic sizing, legacy strategy parity on synthetic bars."""
    def test_trail_ratchets_on_closing_highs_only(self):
        bars = [Bar(T0, 100, 101, 99, 100, 1), Bar(T0 + DAY, 100, 112, 99, 110, 1), Bar(T0 + 2 * DAY, 110, 125, 108, 120, 1),
                Bar(T0 + 3 * DAY, 120, 121, 104, 105, 1), Bar(T0 + 4 * DAY, 105, 106, 100, 101, 1)]
        m = mk({"X": bars})
        s = lambda view, pf: [Order("X", "buy", stop=50, trail=0.10)] if view.t == T0 + DAY else []
        r = run(m, s, COSTS); tr = r["trades"][0]
        # entry day1 open 100(+cost); seed high = day1 close 110 (no ratchet on the entry bar); day2 close 120 → stop 108; day3 low 104 → stopped at 108
        self.assertEqual(tr.reason, "stop"); self.assertEqual(tr.exit_t, T0 + 3 * DAY)
        self.assertAlmostEqual(tr.exit_px, 108 * (1 - COSTS.per_side()), places=9)

    def test_fixed_usd_does_not_scale_with_equity(self):
        s = lambda view, pf: [Order("AAA", "buy")] if view.t in (T0 + DAY, T0 + 5 * DAY) else ([Order("AAA", "sell")] if view.t == T0 + 3 * DAY else [])
        r = run(market(10), s, COSTS, start_cash=10_000, fixed_usd=100.0)
        self.assertEqual([e[3] for e in r["events"] if e[2] == "fill"], ["100.00", "100.00"])
        self.assertEqual(r["sizing"]["rule"], "fixed-usd DIAGNOSTIC")
        self.assertEqual(len(r["cash_curve"]), len(r["equity"]))

    @staticmethod
    def vol_market(n=500):
        def walk(seed, n, drift):
            rnd = random.Random(seed); px = 100.0; out = []
            for i in range(n):
                o = px; c = o * (1 + rnd.gauss(drift, 0.04)); h = max(o, c) * (1 + abs(rnd.gauss(0, 0.01))); l = min(o, c) * (1 - abs(rnd.gauss(0, 0.01)))
                v = rnd.lognormvariate(0, 0.8) * (3 if rnd.random() < 0.08 else 1)
                out.append(Bar(T0 + i * DAY, o, h, l, c, v)); px = c
            return out
        return Market({"BTC": walk(1, n, 0.0005), "AAA": walk(2, n, 0.002), "BBB": walk(3, n, 0.001), "CCC": walk(5, n, 0.0), "DEAD": walk(4, 200, 0.002)},
                      {"BTC": (T0, None), "AAA": (T0, None), "BBB": (T0, None), "CCC": (T0, None), "DEAD": (T0, T0 + 200 * DAY)})

    def test_legacy_port_and_honest_engine_agree_when_capital_is_unconstrained(self):
        """Cell 1 (verbatim legacy) and cell 2 (honest engine, same $100) must match trade-for-trade on a path where
        listings and cash never bind — otherwise the port, not the data, would explain a #1 vs #2 gap."""
        import bt_attrib
        _, ms = bt_attrib.report(self.vol_market(), 10_000, "synthetic-vol")
        c1, c2, c3 = [ms[k] for k in sorted(ms)][:3]
        self.assertGreater(c1["trades"], 5)
        for k in ("trades", "win_rate"):
            self.assertEqual(c1[k], c2[k])
        for k in ("avg_trade_return", "profit_factor", "total_return"):
            self.assertAlmostEqual(c1[k], c2[k], places=6)
        self.assertEqual(c2["trades"], c3["trades"])                       # same signals; only the size differs
        self.assertGreater(c3["exposure_pct"], c2["exposure_pct"])         # slot sizing deploys more than $100 of $10k

    def test_delisted_holding_closes_at_last_close(self):
        bars = [Bar(T0 + i * DAY, 100, 101, 99, 100, 1) for i in range(5)]
        m = mk({"X": bars, "Y": [Bar(T0 + i * DAY, 1, 1, 1, 1, 1) for i in range(8)]}, {"X": (T0, T0 + 5 * DAY), "Y": (T0, None)})
        s = lambda view, pf: [Order("X", "buy")] if view.t == T0 + DAY else []
        r = run(m, s, COSTS); tr = r["trades"][0]
        self.assertEqual(tr.reason, "delisted"); self.assertEqual(tr.exit_t, T0 + 5 * DAY)
        self.assertAlmostEqual(tr.exit_px, 100 * (1 - COSTS.per_side()), places=9)

    def test_weekly_cap_counts_fills_not_refused_proposals(self):
        """R-O: a proposal refused by the engine must not consume one of the week's two opportunities."""
        m = self.vol_market()
        s = strategies.breakout_legacy(per_week=2)
        proposals = []
        def spy(view, pf):
            out = s(view, pf); proposals.extend(o.symbol for o in out); return out
        r = run(m, spy, COSTS, start_cash=10_000, max_positions=1)     # one slot → many refusals (slots)
        refused = r["no_fill_reasons"].get("slots", 0)
        self.assertGreater(refused, 0)
        self.assertGreater(len(proposals), len(r["trades"]))              # refusals happened, and later signals were still proposed

    def test_legacy_strategy_caps_two_entries_per_week_and_attrib_report_runs(self):
        import bt_attrib
        text, ms = bt_attrib.report(market(200), 10_000, "synthetic")
        self.assertTrue(text.startswith(bt_attrib.BANNER) and text.rstrip().endswith(bt_attrib.BANNER))
        self.assertEqual(len(ms), 4)
        for m in ms.values():
            self.assertIn("exposure_pct", m); self.assertIn("avg_cash_pct", m)
        n = {}
        s = strategies.breakout_legacy(per_week=2)
        sym_all = lambda view, pf: n.setdefault(view.t, [o.symbol for o in s(view, pf)])
        run(market(200), sym_all, COSTS)
        import datetime as dt
        wk = {}
        for t, syms in n.items():
            k = dt.datetime.fromtimestamp(t - 1, dt.timezone.utc).isocalendar()[:2]; wk[k] = wk.get(k, 0) + len(syms)
        self.assertTrue(all(v <= 2 for v in wk.values()))


class Loader(unittest.TestCase):
    """R-M: pagination completeness per symbol — a full page must be followed by another request."""
    def test_symbol_with_2001_rows_loads_all_pages(self):
        from bt import load
        calls = []
        def fake_get(table, query):
            calls.append(query)
            if table == "universe_history":
                return [{"symbol": "AAA"}]
            off = int(query.split("offset=")[1]); lim = int(query.split("limit=")[1].split("&")[0])
            total = 2001
            return [{"symbol": "AAA", "bar_time": T0 + i * DAY, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1} for i in range(off, min(off + lim, total))]
        orig = load.sb_get
        load.sb_get = fake_get
        try:
            counts = {}
            rows = load.load_md_candles(page=1000, counts=counts)
        finally:
            load.sb_get = orig
        self.assertEqual(len(rows), 2001); self.assertEqual(counts["AAA"], 2001)
        self.assertEqual(sum(1 for q in calls if "md_candles" in q or "offset=" in q), 3)   # 1000 + 1000 + 1


class StaleMarks(unittest.TestCase):
    """R-V hardening: a held name with no bar today is marked at its last known completed close, and the stale mark is surfaced."""
    def test_missing_bar_marks_at_last_close_not_entry(self):
        bars = [Bar(T0 + i * DAY, 100 + i, 101 + i, 99 + i, 100 + i, 1) for i in range(6)]
        bars = [b for b in bars if b.t != T0 + 3 * DAY]                                   # day 3 missing while held
        m = mk({"X": bars, "Y": [Bar(T0 + i * DAY, 1, 1, 1, 1, 1) for i in range(6)]}, {"X": (T0, None), "Y": (T0, None)})
        s = lambda view, pf: [Order("X", "buy")] if view.t == T0 + DAY else []
        r = run(m, s, COSTS, start_cash=1_000, max_positions=1)
        eq = dict(r["equity"])
        units = 1_000 / (101 * (1 + COSTS.per_side()))
        self.assertAlmostEqual(eq[T0 + 4 * DAY], units * 102, places=6)                    # day 3 marked at day-2 close (102), not entry (101+cost)
        self.assertEqual(r["stale_marks"], 1)
        self.assertEqual([e for e in r["events"] if e[2] == "stale_mark"][0][:2], (T0 + 3 * DAY, "X"))

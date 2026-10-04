"""Phase 4 round 2 tests — PHASE4-ROUND2-PREREGISTRATION.md v2 (FROZEN R-X). Synthetic bars and readings only."""
import datetime as dt, inspect, math, re, unittest
from market_time import DAY
from bt.data import Bar, Market
from bt.engine import Order, run
from bt.metrics import summarize
from bt import round2 as R2, sentiment as S, strategies, tournament as T, research
from bt_costs import CostModel
from test_tournament import T0, COSTS, bars_from, path, mkt, dec


def day(k):
    return dt.datetime.fromtimestamp(T0 + k * DAY, dt.timezone.utc).date()


def readings(n, low_days=(), value=50, low=15, available=None):
    """One reading per bar day k; available=None => backfilled (NULL); 'live' => captured at D 00:20 UTC."""
    out = []
    for k in range(n):
        a = None if available is None else T0 + k * DAY + 20 * 60
        out.append({"snapshot_date": str(day(k)), "fear_greed": low if k in low_days else value, "source": "t", "available_at": a})
    return out


class Sentiment(unittest.TestCase):
    def test_null_available_at_is_unusable_and_assumed_lag_is_d_plus_1_close(self):
        rows = readings(10, low_days=(3,))
        ver = S.from_rows(rows)
        self.assertEqual(ver.unusable, 10); self.assertIsNone(ver.at(T0 + 100 * DAY)); self.assertEqual(ver.evidence_class, "verified")
        asm = S.assumed_availability(rows)
        self.assertEqual(asm.evidence_class, S.ASSUMED_LAG_LABEL)
        r = asm.by_date[day(3)]
        self.assertEqual(r["available_at"], T0 + 5 * DAY)                      # dated D=k3, usable from the close of D+1 = D+2 00:00
        self.assertIsNone(asm.usable_for_day(day(3), T0 + 4 * DAY))             # at D's own close: NOT usable
        self.assertIsNone(asm.usable_for_day(day(3), T0 + 5 * DAY - 1))
        self.assertEqual(asm.usable_for_day(day(3), T0 + 5 * DAY)["value"], 15)
        self.assertEqual(asm.at(T0 + 5 * DAY)["observed_for_date"], day(3))     # at the close of D+1 the lagged reading is the one in force (max_age 1)
        self.assertIsNone(asm.at(T0 + 6 * DAY)) if asm.by_date.get(day(5)) is None else None

    def test_live_rows_usable_at_the_days_close_and_no_forward_fill(self):
        rows = readings(10, low_days=(3,), available="live")
        del rows[4]                                                             # day 4 missing: must stay missing
        ser = S.from_rows(rows)
        self.assertEqual(ser.usable_for_day(day(3), T0 + 4 * DAY)["value"], 15)
        self.assertIsNone(ser.usable_for_day(day(4), T0 + 5 * DAY))
        self.assertIsNone(ser.at(T0 + 5 * DAY))                                  # day 4 missing: the day-3 reading is stale at day 4's close, never carried

    def test_coverage_rule(self):
        rows = readings(200, available="live")
        full = S.from_rows(rows).coverage(T0 + DAY, T0 + 200 * DAY)
        self.assertFalse(full["inconclusive"]); self.assertGreaterEqual(full["share"], 0.99)
        gap = S.from_rows(rows[:50] + rows[90:]).coverage(T0 + DAY, T0 + 200 * DAY)     # 40-day hole > 30
        self.assertTrue(gap["inconclusive"]); self.assertGreaterEqual(gap["longest_gap_days"], 40)
        none = S.from_rows(readings(200)).coverage(T0 + DAY, T0 + 200 * DAY)            # all backfilled: 0%
        self.assertEqual(none["share"], 0.0); self.assertTrue(none["inconclusive"])
        self.assertNotEqual(S.from_rows(rows).fingerprint(), S.assumed_availability(readings(200)).fingerprint())


class ViewExog(unittest.TestCase):
    def test_reading_not_yet_available_is_invisible(self):
        m = mkt(30, names=2)
        ser = S.from_rows(readings(30, low_days=(5,), available="live"))
        v = m.as_of(dec(5), exog={"fear_greed": ser})
        self.assertEqual(v.exog("fear_greed")["value"], 15)
        asm = S.assumed_availability(readings(30, low_days=(5,)))
        self.assertEqual(m.as_of(dec(5), exog={"fear_greed": asm}).exog("fear_greed")["observed_for_date"], day(4))   # day 5's reading not yet available
        self.assertIsNone(m.as_of(dec(5)).exog("fear_greed"))


class CandidateC(unittest.TestCase):
    def test_option_i_timing_holds_exactly_90_bars_and_ignores_signals_while_holding(self):
        m = mkt(400, names=2)
        ser = S.from_rows(readings(400, low_days=(10, 11, 12, 50, 200), available="live"))
        r = run(m, strategies.fear_greed_timing(threshold=25, hold_bars=90), COSTS, exog={"fear_greed": ser}, **R2.ONE_SLOT)
        tr = [t for t in r["trades"] if t.reason != "eod"]
        self.assertEqual(len(tr), 2)                                            # day 10 cluster -> one episode; 50 ignored while holding; 200 -> second
        self.assertEqual(tr[0].entry_t, dec(10)); self.assertEqual(tr[0].exit_t, tr[0].entry_t + 90 * DAY)
        self.assertEqual(tr[1].entry_t, dec(200))
        self.assertEqual(r["sizing"]["max_positions"], 1)
        self.assertAlmostEqual(tr[0].units * tr[0].entry_px, 10_000.0, delta=1)   # one slot = the whole book

    def test_stale_reading_never_triggers(self):
        m = mkt(60, names=2)
        rows = readings(60, low_days=(10,), available="live"); del rows[11]      # day 11 missing: the day-10 reading must not carry
        s = strategies.fear_greed_timing(threshold=25, hold_bars=5)
        r = run(m, s, COSTS, exog={"fear_greed": S.from_rows(rows)}, **R2.ONE_SLOT)
        self.assertEqual([t.entry_t for t in r["trades"] if t.reason != "eod"], [dec(10)])

    def test_falsifier_uses_executed_signals_vs_base_rate(self):
        m = mkt(300, names=2)
        span = (dec(0), dec(290))
        fwd = R2.forward_returns(m, span, 90)
        self.assertIn(dec(0), fwd); self.assertNotIn(dec(250), fwd)            # no 90 bars ahead
        from bt.engine import Trade
        good = [Trade("BTC", dec(5), 0, 1, 1, 1, 0, 0, "signal")]
        res = R2.c_falsifier(m, good, span)
        self.assertEqual(res["signals"]["n"], 1); self.assertGreater(res["base_rate"]["n"], 100)
        self.assertEqual(R2.c_falsifier(m, [], span)["ok"], False)


class CandidateB(unittest.TestCase):
    def market(self, n=260, names=22):
        return mkt(n, names=names)

    def test_breadth_on_frozen_members_and_fail_closed(self):
        m = self.market()
        uni = T.monthly_universe(m)
        s = strategies.momentum_floor(n=3, lookback=60)
        r = run(m, s, COSTS, universe=uni, **R2.TEN_SLOT)
        self.assertGreater(s.state["rebalances"], 0)
        self.assertTrue(all(b is None or 0 <= b <= 1 for _, b in s.state["breadth"]))
        # fewer than 20 members -> every rebalance fails closed, never a buy
        small = mkt(260, names=10); uni2 = T.monthly_universe(small)
        s2 = strategies.momentum_floor(n=3, lookback=60); r2 = run(small, s2, COSTS, universe=uni2, **R2.TEN_SLOT)
        self.assertEqual(s2.state["fail_closed"], s2.state["rebalances"]); self.assertEqual(r2["trades"], [])

    def test_missing_member_bar_fails_closed_that_rebalance(self):
        m = self.market()
        uni = T.monthly_universe(m)
        t_dec = uni.times[1] + 30 * DAY                                         # a rebalance well inside the second month
        hole = Market({s: [b for b in bs if not (s == "S5" and b.t == t_dec - DAY)] for s, bs in m.bars.items()}, m.listings)
        v = hole.as_of(t_dec, universe=uni)
        self.assertIn("S5", v.universe_members()); self.assertNotIn("S5", v.universe())
        s = strategies.momentum_floor(n=3, lookback=60); s.state["last"] = t_dec - 30 * DAY
        pf = type("PF", (), {"positions": {"S9": None}})()
        out = s(v, pf)
        self.assertEqual([(o.symbol, o.side) for o in out], [("S9", "sell")]); self.assertEqual(s.state["fail_closed"], 1)

    def test_floor_sends_to_cash_and_twin_does_not(self):
        m = mkt(260, names=22, extra=None)
        uni = T.monthly_universe(m)
        down = Market({s: bars_from(path(260, drift=-0.004, phase=j), vol=10.0 + j) for j, s in enumerate(m.bars)}, m.listings)   # everything below SMA50
        uni_d = T.monthly_universe(down)
        f = strategies.momentum_floor(n=3, lookback=60); rf = run(down, f, COSTS, universe=uni_d, **R2.TEN_SLOT)
        tw = strategies.momentum_floor(n=3, lookback=60, floor=False); rt = run(down, tw, COSTS, universe=uni_d, **R2.TEN_SLOT)
        self.assertGreater(f.state["cash_rebalances"], 0); self.assertEqual(rf["trades"], [])
        self.assertGreater(len(rt["trades"]), 0)
        self.assertEqual(tw.state["cash_rebalances"], 0); self.assertEqual(len(tw.state["breadth"]), len(f.state["breadth"]))   # twin logs the same breadth, never acts on it

    def test_b_falsifier_requires_all_three(self):
        self.assertTrue(R2.b_falsifier({"total_return": 0.2, "max_drawdown": -0.1, "profit_factor": 1.5}, {"total_return": 0.1, "max_drawdown": -0.2, "profit_factor": 1.1})["ok"])
        self.assertFalse(R2.b_falsifier({"total_return": 0.2, "max_drawdown": -0.3, "profit_factor": 1.5}, {"total_return": 0.1, "max_drawdown": -0.2, "profit_factor": 1.1})["ok"])


class ClassGates(unittest.TestCase):
    def test_a_falsifier_quantitative(self):
        self.assertTrue(R2.a_falsifier({"total_return": 0.5, "max_drawdown": -0.5}, {"total_return": 0.4, "max_drawdown": -0.6})["ok"])
        self.assertTrue(R2.a_falsifier({"total_return": 0.30, "max_drawdown": -0.30}, {"total_return": 0.40, "max_drawdown": -0.60})["ok"])      # 75% of return, DD halved
        self.assertFalse(R2.a_falsifier({"total_return": 0.30, "max_drawdown": -0.59}, {"total_return": 0.40, "max_drawdown": -0.60})["ok"])     # trivial DD improvement does not rescue
        self.assertFalse(R2.a_falsifier({"total_return": 0.27, "max_drawdown": -0.30}, {"total_return": 0.40, "max_drawdown": -0.60})["ok"])     # below 70%
        self.assertTrue(R2.a_falsifier({"total_return": 0.01, "max_drawdown": -0.3}, {"total_return": -0.2, "max_drawdown": -0.6})["ok"])        # B&H negative: positive A suffices

    def test_outcomes(self):
        ok = {"a": True, "b": True}
        self.assertEqual(R2.outcome(ok, True, 12, 10, True), ("historical_survivor", None))
        self.assertEqual(R2.outcome(ok, True, 5, 10, True)[0], "inconclusive")
        self.assertEqual(R2.outcome({"a": True, "b": False}, True, 12, 10, True), ("historical_rejected", "b"))
        self.assertEqual(R2.outcome(ok, False, 12, 10, True), ("historical_rejected", "falsifier"))
        self.assertEqual(R2.outcome(ok, True, 12, 10, False)[0], "inconclusive")
        self.assertEqual(R2.outcome(ok, True, 12, 10, True, "coverage 0%")[0], "inconclusive")

    def test_frozen_constants(self):
        self.assertEqual(set(R2.CANDIDATES), {"A_btc_trend", "B_momentum_floor", "C_fear_greed"})
        self.assertEqual(R2.CANDIDATES["A_btc_trend"]["min_episodes"], 10); self.assertEqual(R2.CANDIDATES["C_fear_greed"]["min_episodes"], 8)
        self.assertEqual(R2.CANDIDATES["B_momentum_floor"]["min_trades"], 100)
        self.assertEqual(R2.CANDIDATES["A_btc_trend"]["grid"], [{"fast": 20, "slow": 100}, {"fast": 50, "slow": 200}])
        self.assertEqual(len(R2.CANDIDATES["B_momentum_floor"]["grid"]), 4); self.assertEqual(R2.CANDIDATES["C_fear_greed"]["grid"], [{"threshold": 20}, {"threshold": 25}])
        self.assertEqual((R2.C_HOLD_BARS, R2.C_HOLD_SENSITIVITY, R2.B_BREADTH_FLOOR, R2.B_MEMBERS_REQUIRED, R2.C_ASSUMED_LAG_DAYS), (90, 30, 0.50, 20, 1))
        self.assertAlmostEqual(R2.COSTS["stress"].per_side(), 0.00625); self.assertAlmostEqual(R2.COSTS["canonical"].per_side(), 0.005)
        self.assertEqual(R2.ONE_SLOT, {"max_positions": 1, "gross_cap": 1.0}); self.assertEqual(R2.OUTCOMES, ("historical_survivor", "historical_rejected", "inconclusive"))
        src = inspect.getsource(R2) + open(__file__.replace("test_round2.py", "bt_round2.py")).read()
        self.assertIsNone(re.search(r"save_run|sb_upsert|sb_insert|research_accepted\s*=\s*True", src))


class Smoke(unittest.TestCase):
    def test_table_on_synthetic_data(self):
        m = mkt(420, names=24)
        rows = readings(420, low_days=tuple(range(60, 70)) + tuple(range(200, 205)) + (330,))
        table = R2.run_table(m, rows, fit_days=90, test_days=45, with_regime=False, log=lambda *a: None)
        self.assertEqual(set(table["candidates"]), {"A_btc_trend", "B_momentum_floor", "C_fear_greed", "C_fear_greed__verified"})
        for n, r in table["candidates"].items():
            self.assertTrue(r["outcome"].split(" (")[0] in R2.OUTCOMES, (n, r["outcome"]))
            self.assertFalse(r.get("research_accepted")); self.assertIn("provenance", r)
        ver, asm = table["candidates"]["C_fear_greed__verified"], table["candidates"]["C_fear_greed"]
        self.assertEqual(ver["evidence_class"], "verified"); self.assertEqual(ver["outcome"], "inconclusive"); self.assertIn("coverage", ver["reason"])
        self.assertEqual(asm["evidence_class"], S.ASSUMED_LAG_LABEL); self.assertFalse(asm["coverage"]["inconclusive"])
        a = table["candidates"]["A_btc_trend"]
        self.assertEqual(a["sizing"], R2.ONE_SLOT); self.assertIn("benchmark_btc_bh_100", a); self.assertIn("sensitivity_10_slot", a)
        b = table["candidates"]["B_momentum_floor"]
        self.assertIn("twin", b["falsifier"]); self.assertIn("cap_0.95", b["sensitivity"])
        self.assertEqual(table["trials_total"], sum(r["trials"] for k, r in table["candidates"].items() if k != "C_fear_greed__verified"))
        self.assertIn("btc_bh_100pct", table["benchmarks"]); self.assertIn("negative_control", table)
        md = R2.render(table); self.assertIn("A_btc_trend", md); self.assertRegex(md, "historical_|inconclusive"); self.assertNotIn("research_accepted", md.split("##")[0].replace("research_runs", ""))


if __name__ == "__main__":
    unittest.main()

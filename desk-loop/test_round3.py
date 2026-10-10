"""Round 3 runner-forensics tests — FROZEN v3 (R-AE) + Stage 0 manifest v2 (R-AH). Synthetic bars and synthetic DeFiLlama
snapshots only. Every feature has a look-ahead test: a spike in the bar OPENING at the formation close changes nothing."""
import datetime as dt, inspect, math, re, unittest, random
import numpy as np
from market_time import DAY
from bt.data import Bar, Market
from bt import round3 as R3

T0 = 1_609_459_200      # 2021-01-01 00:00 UTC


def bars_from(closes, t0=T0, vol=5000.0, vols=None):
    """Volume varies deterministically unless given: a constant volume makes vol_z_20 NaN (std 0) by the frozen rule."""
    out = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        v = vols[i] if vols else vol * (1 + 0.4 * math.sin(i / 3.0) + 0.2 * math.cos(i / 7.0))
        out.append(Bar(t0 + i * DAY, o, max(o, c) * 1.002, min(o, c) * 0.998, c, v))
    return out


def walk(seed, n, drift=0.0005, vol=0.03, start=10.0):
    rng = random.Random(seed); px, out = start, []
    for _ in range(n):
        px *= math.exp(rng.gauss(drift, vol)); out.append(px)
    return out


def mkt(n=1900, names=40, seed=1, plant=None):
    """BTC + names; dollar volume ~ 5000*px >> 250k floor for px >= 50; plant: {symbol: (start_bar, multiple)} forces a run."""
    bars = {"BTC": bars_from(walk(seed, n, start=30000.0), vol=100.0)}; L = {"BTC": (T0, None)}
    for j in range(names):
        c = walk(seed * 100 + j, n, start=100.0)
        if plant and f"S{j}" in plant:
            k0, mult = plant[f"S{j}"]; c = c[:k0] + [c[k0] * (1 + (mult - 1) * min(1.0, (i - k0) / 60)) for i in range(k0, n)]
        bars[f"S{j}"] = bars_from(c); L[f"S{j}"] = (T0, None)
    return Market(bars, L)


class Formation(unittest.TestCase):
    def test_first_decision_close_of_each_month(self):
        m = mkt(n=400, names=3)
        ts = R3.formation_times(m)
        self.assertEqual(ts[0], T0 + (31 + 28 + 1) * DAY)                   # 2021-03-01 bar completes at 03-02 00:00 UTC
        self.assertEqual(R3._month(ts[0] - DAY), (2021, 3))
        self.assertEqual(len({R3._month(t - DAY) for t in ts}), len(ts))     # one per month

    def test_candidate_set_rules(self):
        m = mkt(n=400, names=4)
        t = R3.formation_times(m)[3]                                          # June 2021
        self.assertEqual(set(R3.candidate_set(m, t)), {"BTC", "S0", "S1", "S2", "S3"})
        # 90 contiguous bars required; missing bar inside the window -> out that month
        hole = Market({s: [b for b in bs if not (s == "S1" and b.t == t - 10 * DAY)] for s, bs in m.bars.items()}, m.listings)
        self.assertNotIn("S1", R3.candidate_set(hole, t))
        # liquidity floor on 3-day median dollar volume
        thin = Market({**m.bars, "S2": bars_from([b.c for b in m.bars["S2"]], vol=1.0)}, m.listings)
        self.assertNotIn("S2", R3.candidate_set(thin, t))
        # executable next open required; delisted-later names kept while listed; exclusion map applied
        gap = Market({s: [b for b in bs if not (s == "S3" and b.t == t)] for s, bs in m.bars.items()}, m.listings)
        self.assertNotIn("S3", R3.candidate_set(gap, t))
        dl = Market(m.bars, {**m.listings, "S0": (T0, t + 20 * DAY)})
        self.assertIn("S0", R3.candidate_set(dl, t)); self.assertNotIn("S0", R3.candidate_set(dl, t + 30 * DAY))
        ex = Market({**m.bars, "USDC": m.bars["S0"]}, {**m.listings, "USDC": (T0, None)})
        self.assertNotIn("USDC", R3.candidate_set(ex, t))


class Labels(unittest.TestCase):
    def test_entry_reference_is_next_open_and_tiers(self):
        m = mkt(n=400, names=2, plant={"S0": (150, 3.2)})
        t = T0 + 150 * DAY
        lab = R3.labels(m, "S0", t)
        self.assertEqual(lab["entry_reference"], m.bar_opening_at("S0", t).o)      # the OPEN of the bar opening at t, not the formation close
        self.assertTrue(lab["runner_2x"] and lab["runner_3x"] and not lab["runner_5x"])
        self.assertEqual(lab["bars_in_window"], 180)
        self.assertFalse(R3.labels(m, "S1", t)["runner_2x"])

    def test_delisting_truncates_window_never_drops(self):
        m = mkt(n=400, names=1, plant={"S0": (150, 3.0)})
        short = Market({"BTC": m.bars["BTC"], "S0": m.bars["S0"][:170]}, {"BTC": (T0, None), "S0": (T0, T0 + 170 * DAY)})
        lab = R3.labels(short, "S0", T0 + 150 * DAY)
        self.assertEqual(lab["bars_in_window"], 20); self.assertFalse(lab["runner_2x"])   # ramp reaches 2x only after bar 180


class Features(unittest.TestCase):
    def setUp(self):
        self.m = mkt(n=500, names=6); self.t = R3.formation_times(self.m)[5]
        self.cands = R3.candidate_set(self.m, self.t)

    def btc(self, m):
        import bisect; i = bisect.bisect_right(m._ts["BTC"], self.t - DAY); return [b.c for b in m.bars["BTC"][:i]]

    def test_every_feature_is_finite_and_look_ahead_free(self):
        br = R3.breadth_of(self.m, self.t, self.cands)
        f = R3.verified_features(self.m, "S0", self.t, self.btc(self.m), br)
        self.assertEqual(set(f), set(R3.VERIFIED)); self.assertTrue(all(math.isfinite(v) for v in f.values()))
        # spike the bar OPENING at t (and BTC's) by 10x price and 100x volume: nothing may change
        spiked = {}
        for s, bs in self.m.bars.items():
            spiked[s] = [Bar(b.t, b.o * 10, b.h * 10, b.l * 10, b.c * 10, b.v * 100) if b.t == self.t else b for b in bs]
        ms = Market(spiked, self.m.listings)
        self.assertEqual(R3.candidate_set(ms, self.t), self.cands)
        self.assertEqual(R3.breadth_of(ms, self.t, self.cands), br)
        self.assertEqual(R3.verified_features(ms, "S0", self.t, self.btc(ms), br), f)
        # truncated market (nothing after t) gives the identical row
        trunc = Market({s: [b for b in bs if b.t + DAY <= self.t] for s, bs in self.m.bars.items()}, self.m.listings)
        self.assertEqual(R3.verified_features(trunc, "S0", self.t, self.btc(trunc), br), f)

    def test_nan_makes_ineligible_and_breadth_uses_pre_feature_set(self):
        flat = Market({**self.m.bars, "S1": bars_from([100.0] * 500, vols=[500000.0] * 500)}, self.m.listings)   # constant volume: vol_z std 0 -> NaN
        cands = R3.candidate_set(flat, self.t); self.assertIn("S1", cands)
        br = R3.breadth_of(flat, self.t, cands)
        self.assertIsNone(R3.verified_features(flat, "S1", self.t, self.btc(flat), br))
        rows, counts = R3.build_dataset(flat, log=lambda *a: None)
        rows_t = [r for r in rows if r["t"] == self.t]
        self.assertEqual(len(rows_t), len(cands))                              # S1 stays in the population (scored population = candidate set)
        self.assertTrue(any(r["symbol"] == "S1" and r["verified"] is None for r in rows_t)); self.assertGreater(counts["verified_ineligible"], 0)
        self.assertTrue(all(r["verified"] is None or r["verified"]["breadth_ctx"] == br for r in rows_t))

    def test_quintiles_and_91_closes(self):
        self.assertEqual(R3.quintiles([5, 1, 3, 2, 4]), [4, 0, 2, 1, 3])
        m = mkt(n=400, names=2); t = R3.formation_times(m)[4]                      # July 2021: > 90 bars exist
        k0, k1 = (t - 90 * DAY - T0) // DAY, (t - T0) // DAY
        exact90 = Market({**m.bars, "S1": m.bars["S1"][k0:k1 + 1]}, {**m.listings, "S1": (t - 90 * DAY, None)})   # exactly 90 completed bars + the bar opening at t
        self.assertIn("S1", R3.candidate_set(exact90, t))                       # enters the candidate set with exactly 90 bars
        br = R3.breadth_of(exact90, t, R3.candidate_set(exact90, t))
        import bisect; i = bisect.bisect_right(exact90._ts["BTC"], t - DAY)
        self.assertIsNone(R3.verified_features(exact90, "S1", t, [b.c for b in exact90.bars["BTC"][:i]], br))   # but ret_90 needs 91 closes


class Assumed(unittest.TestCase):
    def snap(self, listed="2021-01-01", fees=True, stable=True):
        days = [(dt.date(2021, 1, 1) + dt.timedelta(days=k)) for k in range(500)]
        ts = lambda d: int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())
        j = {"families": {"S0": {"slugs": ["p-a", "p-b"], "fees_slugs": ["p-a"], "earliest_listedAt": listed}},
             "tvl": {"p-a": [[ts(d), 100.0 + k] for k, d in enumerate(days)], "p-b": [[ts(d), 50.0] for d in days]},
             "fees": {"p-a": [[ts(d), 10.0 + (k % 7)] for k, d in enumerate(days)]} if fees else {}, "revenue": {"p-a": [[ts(d), 5.0] for d in days]} if fees else {},
             "stablecoins": [[ts(d), 1e9 * (1 + k / 1000)] for k, d in enumerate(days)] if stable else [], "hash": "x"}
        return R3.LlamaSnapshot(j)

    def test_lag_and_listedAt_rules(self):
        s = self.snap(); t = T0 + 200 * DAY                                        # formation close 2021-07-20 00:00
        f = R3.assumed_features(s, "S0", t)
        dmax = dt.date(2021, 7, 20) - dt.timedelta(days=8)
        self.assertEqual(f["has_family"], 1.0); self.assertTrue(math.isfinite(f["tvl_change_30"])); self.assertTrue(math.isfinite(f["fees_growth_30"]))
        self.assertTrue(math.isnan(f["rev_yield"]) and f["rev_yield_missing"] == 1.0)   # no point-in-time market cap exists: NaN by construction
        # the value dated Dmax+1 is not usable yet: changing it must not move any feature
        j2 = self.snap(); j2.tvl["p-a"][dmax + dt.timedelta(days=1)] = 1e9
        self.assertEqual(R3.assumed_features(j2, "S0", t)["tvl_change_30"], f["tvl_change_30"])
        j3 = self.snap(); j3.tvl["p-a"][dmax] = 1e9
        self.assertNotEqual(R3.assumed_features(j3, "S0", t)["tvl_change_30"], f["tvl_change_30"])
        # listedAt after the window start -> fundamentals NaN with indicators, family still flagged
        late = R3.assumed_features(self.snap(listed="2021-07-01"), "S0", t)
        self.assertTrue(math.isnan(late["fees_growth_30"]) and late["fees_growth_30_missing"] == 1.0 and late["has_family"] == 1.0)
        self.assertEqual(R3.assumed_features(s, "S9", t)["has_family"], 0.0)
        self.assertTrue(math.isnan(R3.assumed_features(self.snap(stable=False), "S0", t)["stable_supply_30"]))   # month will fail closed

    def test_missing_day_inside_window_is_nan_never_filled(self):
        s = self.snap(); t = T0 + 200 * DAY; dmax = dt.date(2021, 7, 20) - dt.timedelta(days=8)
        del s.fees["p-a"][dmax - dt.timedelta(days=3)]
        self.assertTrue(math.isnan(R3.assumed_features(s, "S0", t)["fees_growth_30"]))


class Model(unittest.TestCase):
    def test_standardiser_training_only_and_nan_to_zero(self):
        X = np.array([[1.0, float("nan")], [3.0, 2.0], [5.0, 4.0]]); sc = R3.Standardiser().fit(X)
        self.assertAlmostEqual(sc.mu[1], 3.0); Z = sc.transform(np.array([[3.0, float("nan")]])); self.assertEqual(Z[0, 0], 0.0); self.assertEqual(Z[0, 1], 0.0)

    def test_logistic_recovers_signal_and_precision_lift(self):
        rng = np.random.default_rng(0); X = rng.normal(size=(2000, 3)); y = (X[:, 0] + 0.3 * rng.normal(size=2000) > 1.0).astype(float)
        w = R3.fit_logistic(X, y, 1.0); self.assertGreater(w[1], 1.0); self.assertLess(abs(w[2]), 0.3)
        rows = [{"month": (2022, 1 + i % 12), "quintile": i % 5, "runner_2x": bool(y[i])} for i in range(2000)]
        r = R3.strata_precision(rows, list(R3.predict(w, X)))
        self.assertGreater(r["lift"], 2.0); self.assertGreater(r["positives"], 100)
        shuffled = rng.permutation(y); rows2 = [dict(r_, runner_2x=bool(shuffled[i])) for i, r_ in enumerate(rows)]
        self.assertLess(abs(R3.strata_precision(rows2, list(R3.predict(w, X)))["lift"] - 1.0), 0.35)

    def test_permutation_p_small_for_real_signal(self):
        rng = np.random.default_rng(1); sc = rng.normal(size=600); y = sc + rng.normal(size=600) * 0.5 > 0.8
        rows = [{"month": (2023, 1 + i % 6), "quintile": i % 5, "runner_2x": bool(y[i])} for i in range(600)]
        lift = R3.strata_precision(rows, list(sc))["lift"]
        self.assertLess(R3.permutation_p(rows, list(sc), lift, n=200), 0.05)


class Table(unittest.TestCase):
    def test_full_table_on_synthetic_with_planted_runners(self):
        R3_FM = R3.FORMATION_MONTHS
        m = mkt(n=1900, names=30, plant={f"S{j}": (300 + 40 * j, 2.5) for j in range(0, 30, 3)})
        table = R3.run_table(m, snap=None, log=lambda *a: None)
        v = table["pipelines"]["verified"]
        self.assertEqual(v["trials"], 8); self.assertEqual(set(v["picks"]) <= set(R3.TEST_YEARS), True)
        self.assertIn(v["outcome"], ("historical_survivor", "historical_rejected", "inconclusive", "invalid"))
        self.assertFalse(v["research_accepted"]); self.assertIn("negative_control", v); self.assertIn("permutation_p", v)
        self.assertEqual(set(v["checks"]), {"pooled_lift>=2", "years_lift>=1.5_in_3_of_4", "survives_without_top_liquidity_quintile", "survives_without_top3_months"})
        md = R3.render(table); self.assertIn("| verified |", md); self.assertNotIn("research_accepted", md.split("\n")[0])

    def test_frozen_constants_and_no_store(self):
        self.assertEqual(len(R3.FORMATION_MONTHS), 57); self.assertEqual((R3.MIN_BARS, R3.LIQ_FLOOR_USD, R3.HORIZON), (90, 250_000.0, 180))
        self.assertEqual(R3.TIERS, {"runner_2x": 2.0, "runner_3x": 3.0, "runner_5x": 5.0}); self.assertEqual(R3.C_GRID, (0.1, 1.0)); self.assertEqual(R3.TEST_YEARS, (2022, 2023, 2024, 2025))
        self.assertEqual((R3.TOP_SHARE, R3.MIN_POSITIVES_TOTAL, R3.MIN_POSITIVES_YEAR, R3.ASSUMED_LAG_DAYS), (0.10, 40, 5, 7))
        self.assertEqual(R3.GATE, {"pooled_lift": 2.0, "year_lift": 1.5, "years_needed": 3}); self.assertEqual(len(R3.VERIFIED), 16)
        src = inspect.getsource(R3) + open(__file__.replace("test_round3.py", "bt_round3.py")).read()
        self.assertIsNone(re.search(r"save_run|sb_upsert|sb_insert|research_accepted\s*=\s*True", src))


if __name__ == "__main__":
    unittest.main()

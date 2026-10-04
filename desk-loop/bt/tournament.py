"""Phase 4 strategy tournament — docs/desk/PHASE4-PREREGISTRATION.md v2, FROZEN (R-S FINAL). Nothing here is tunable
after results begin: candidates, grids, universe mechanics, exclusions, cost sets, sizing, robustness thresholds and
advancement booleans are constants of this module. Nothing is written to research_runs by this module."""
import bisect, dataclasses, datetime as dt, hashlib, json, statistics as st
from bt_costs import CostModel
from .engine import run
from .metrics import summarize
from . import research, strategies, regime as regime_mod

# ---------------------------------------------------------------- frozen constants (§1–§7)
EXCLUDE = frozenset("USDT USDC DAI PYUSD USDS FDUSD TUSD GUSD USDP EURC EUROC WBTC WETH CBETH CBBTC STETH RETH LSETH".split())
UNIVERSE_TOP, UNIVERSE_LOOKBACK = 20, 90
COSTS = {
    "canonical": CostModel(0.0025, 0.0040, venue="kraken", tier="Kraken Pro starter taker 0.40% ASSUMED until the live account tier is read (R-A); +0.05% half-spread +0.05% slippage", spread=0.0005, slippage=0.0005),
    "severe": CostModel(0.0095, 0.0095, venue="coinbase-daily", tier="legacy blended COST_SIDE per side (severe sensitivity only)"),
}
SIZING = {"canonical": {"max_positions": 10, "gross_cap": 1.0}, "cap_0.95": {"max_positions": 10, "gross_cap": 0.95}, "cap_0.90": {"max_positions": 10, "gross_cap": 0.90}}
FIT_DAYS, TEST_DAYS = 365, 90
START_CASH = (10_000.0, 100_000.0)
CANDIDATES = {   # name: (factory, grid, role)
    "sma_trend": (strategies.sma_trend, [{"fast": 20, "slow": 100}, {"fast": 50, "slow": 200}], "candidate"),
    "momentum_top": (strategies.momentum_top, [{"lookback": l, "n": n} for l in (60, 90) for n in (5, 10)], "candidate"),
    "mean_reversion": (strategies.mean_reversion, [{"dip": d, "n": n} for d in (0.08, 0.10) for n in (20, 30)], "candidate"),
    "breakout20": (strategies.breakout20, [{}], "negative_control"),
    "buy_and_hold_btc": (lambda **kw: strategies.buy_and_hold(["BTC"]), [{}], "benchmark"),
    "cash": (strategies.cash, [{}], "benchmark"),
}
MIN_OOS_TRADES = 100
DELIST = {"canonical": (10, 0.50), "mild": (5, 0.25), "tail": (20, 1.00)}     # (liquidity multiple of slot, recovery haircut)
DELIST_ABS_FLOOR, DELIST_TRIGGER = 50_000.0, 0.10
BOUNDARY_TOL = 0.20
SCALE_TOL = 1e-6
DAY = 86400


# ---------------------------------------------------------------- §1 universe schedule
class UniverseSchedule:
    """Frozen monthly top-N membership keyed by the decision time it was ranked at. `at(t)` = membership in force at t."""

    def __init__(self, times, members, meta):
        self.times, self.members, self.meta = times, members, meta

    def at(self, t):
        i = bisect.bisect_right(self.times, t) - 1
        return self.members[i] if i >= 0 else frozenset()

    def hash(self):
        return hashlib.sha256(json.dumps([(t, sorted(m)) for t, m in zip(self.times, self.members)]).encode()).hexdigest()[:16]

    def manifest(self):
        return {"top": UNIVERSE_TOP, "lookback_bars": UNIVERSE_LOOKBACK, "excluded": sorted(EXCLUDE), "rankings": len(self.times),
                "membership_hash": self.hash(), "months": [{"t": t, "members": sorted(m)} for t, m in zip(self.times, self.members)]}


def monthly_universe(market, top=UNIVERSE_TOP, lookback=UNIVERSE_LOOKBACK, exclude=EXCLUDE):
    """On the first decision close of each UTC calendar month rank listed, non-excluded names by mean(close×volume) over
    the preceding `lookback` completed bars (all present, contiguous); top N, ties by symbol asc; frozen until the next
    ranking; only data completed by that close; trades from the next open (the engine fills next open by construction)."""
    bar = market.bar_seconds
    dec_times = sorted({b.t + bar for bs in market.bars.values() for b in bs})
    times, members, last_month = [], [], None
    for t_dec in dec_times:
        ym = dt.datetime.fromtimestamp(t_dec - 1, dt.timezone.utc).strftime("%Y-%m")   # month of the completed bar
        if ym == last_month:
            continue
        scored = []
        for s, bs in market.bars.items():
            if s in exclude:
                continue
            a, d = market.listings.get(s, (None, None))
            if a is None or not (a <= t_dec and (d is None or t_dec < d)):
                continue
            i = market.completed_until(s, t_dec)
            if i < lookback or bs[i - lookback].t != t_dec - lookback * bar or bs[i - 1].t != t_dec - bar:
                continue                                                     # all `lookback` bars required, contiguous, fresh
            w = bs[i - lookback:i]
            if any(b.v is None for b in w):
                continue                                                     # no forward-filling of volume
            scored.append((-st.mean(b.c * b.v for b in w), s))
        if not scored:
            continue
        last_month = ym
        times.append(t_dec); members.append(frozenset(s for _, s in sorted(scored)[:top]))
    return UniverseSchedule(times, members, {"top": top, "lookback": lookback})


# ---------------------------------------------------------------- §4 continuous frozen-parameter OOS run
def _switching_strategy(factory, picks):
    """One strategy instance per distinct parameter set; the instance in force is the fold whose test window holds view.t.
    A switch never force-closes: the new instance sees the same portfolio and applies its own exit rule."""
    insts = {}
    def key(p): return json.dumps(p, sort_keys=True)
    windows = [(ts, te, key(p["params"]), p["params"]) for p in picks for ts, te in [p["test"]]]
    def s(view, pf):
        for ts, te, k, params in windows:
            if ts <= view.t < te:
                if k not in insts:
                    insts[k] = factory(**params)
                return insts[k](view, pf)
        return []
    return s


def continuous_oos(market, factory, picks, costs, sizing, start_cash, universe=None):
    ts0, te1 = picks[0]["test"][0], picks[-1]["test"][1]
    return run(market, _switching_strategy(factory, picks), costs, start_cash=start_cash, start_t=ts0, end_t=te1, universe=universe, **sizing)


def boundary_dependency(chained_oos, continuous_oos_metrics, per_fold_eod_exits):
    """Pre-registration §4: fold results are selection evidence; the continuous run is the verdict curve. Flag when the
    chained (boundary-liquidating) return differs from the continuous return by more than 20% of its size or in sign."""
    a, b = chained_oos.get("total_return"), continuous_oos_metrics.get("total_return")
    if a is None or b is None:
        return {"ok": False, "reason": "missing"}
    flip = (a > 0) != (b > 0)
    diff = abs(a - b) > BOUNDARY_TOL * max(abs(a), 1e-9)
    return {"ok": not (flip or diff), "chained_return": a, "continuous_return": b, "boundary_exits": per_fold_eod_exits, "sign_flip": flip, "diff_over_20pct": diff}


# ---------------------------------------------------------------- §7 advancement pieces
def thirds(equity):
    """Positive return in ≥ 2 of 3 chronological thirds of the continuous OOS curve."""
    if len(equity) < 6:
        return {"ok": False, "returns": []}
    n = len(equity); cuts = [0, n // 3, 2 * n // 3, n - 1]
    rets = [equity[cuts[i + 1]][1] / equity[cuts[i]][1] - 1 for i in range(3)]
    return {"ok": sum(1 for r in rets if r > 0) >= 2, "returns": rets}


def scale_invariance(curve_a, curve_b):
    na = [e / curve_a[0][1] for _, e in curve_a]; nb = [e / curve_b[0][1] for _, e in curve_b]
    if len(na) != len(nb):
        return {"ok": False, "max_abs_diff": None}
    d = max(abs(x - y) for x, y in zip(na, nb))
    return {"ok": d <= SCALE_TOL, "max_abs_diff": d}


def delisting_stress(market, trades, start_cash, slot_usd, equity_return):
    """Pre-registration §7.7 / R-J / R-K. Trades in names that are later delisted: exposure share by |P&L| and by count.
    If the share reaches the trigger, re-price every exit with reason 'delisted' at the last reliable executable bar
    (3-day median close×volume ≥ max($50k, k × slot)) with a recovery haircut, for the canonical, mild and tail cases.
    Adjusted return = OOS return + ΔP&L / start_cash (additive approximation, stated)."""
    bar = market.bar_seconds
    delisted = {s for s, (a, d) in market.listings.items() if d is not None}
    tot_abs = sum(abs(t.pnl) for t in trades) or 1e-9
    exp_pnl = sum(abs(t.pnl) for t in trades if t.symbol in delisted) / tot_abs
    exp_n = sum(1 for t in trades if t.symbol in delisted) / (len(trades) or 1)
    out = {"exposure_pnl_share": exp_pnl, "exposure_trade_share": exp_n, "triggered": max(exp_pnl, exp_n) >= DELIST_TRIGGER, "cases": {}}
    for name, (mult, haircut) in DELIST.items():
        floor = max(DELIST_ABS_FLOOR, mult * slot_usd); delta = 0.0; repriced = 0
        for t in trades:
            if t.reason != "delisted":
                continue
            bs = market.bars[t.symbol]
            px = None
            for i in range(len(bs) - 1, 1, -1):                         # walk back to the last bar with reliable 3-day median $volume
                if bs[i].t > t.exit_t:
                    continue
                med = st.median(b.c * b.v for b in bs[i - 2:i + 1])
                if med >= floor:
                    px = bs[i].c; break
            new_exit = (px if px is not None else 0.0) * (1 - haircut)      # no reliable bar at all → nothing recovered
            delta += t.units * (new_exit - t.exit_px); repriced += 1
        out["cases"][name] = {"multiple": mult, "haircut": haircut, "repriced_exits": repriced, "delta_pnl": delta, "adjusted_return": equity_return + delta / start_cash}
    out["canonical_ok"] = (not out["triggered"]) or out["cases"]["canonical"]["adjusted_return"] > 0
    return out


def per_state(trades, series):
    """P&L and count of OOS trades grouped by the regime label in force at entry (filter OFF, labels descriptive, R-R)."""
    out = {s: {"trades": 0, "pnl": 0.0} for s in regime_mod.STATES}
    for t in trades:
        lab = series.at(t.entry_t)[0]
        out[lab]["trades"] += 1; out[lab]["pnl"] += t.pnl
    return out


# ---------------------------------------------------------------- the table
def evaluate(market, name, universe, series, costs=None, sizing=None, fit_days=FIT_DAYS, test_days=TEST_DAYS):
    """One candidate under the frozen rules. Returns the manifest-ready record with explicit advancement booleans."""
    factory, grid, role = CANDIDATES[name]
    costs = costs or COSTS["canonical"]; sizing = sizing or SIZING["canonical"]
    make = lambda **kw: factory(**kw)
    wf = research.walk_forward(market, make, grid, costs, fit_days, test_days, sizing=sizing, universe=universe)   # selection, OOS and stress all on the frozen schedule
    rec = {"candidate": name, "role": role, "grid": grid, "trials": wf["trials"], "folds": wf["folds"], "oos_chained": wf["oos"], "oos_chained_fee_stress": wf["oos_fee_stress"]}
    if not wf["folds"]:
        rec["verdict"] = "inconclusive"; rec["reason"] = "no folds"; return rec
    # the per-fold runs liquidate at each boundary: count those exits
    eod = 0
    for p in wf["folds"]:
        r = run(market, make(**p["params"]), costs, start_t=p["test"][0], end_t=p["test"][1], universe=universe, **sizing)
        eod += sum(1 for t in r["trades"] if t.reason == "eod")
    # §4 continuous verdict curve, canonical costs, two start-cash levels; stress ×1.25 continuous as well
    stressed = dataclasses.replace(costs, maker_fee=min(0.099, costs.maker_fee * 1.25), taker_fee=min(0.099, costs.taker_fee * 1.25), tier=f"{costs.tier} x1.25")
    c10 = continuous_oos(market, make, wf["folds"], costs, sizing, START_CASH[0], universe)
    c100 = continuous_oos(market, make, wf["folds"], costs, sizing, START_CASH[1], universe)
    cst = continuous_oos(market, make, wf["folds"], stressed, sizing, START_CASH[0], universe)
    m10, mst = summarize(c10), summarize(cst)
    rob = research.robustness(market, make, wf["folds"][-1]["params"], costs, sizing=sizing, universe=universe)
    gate = research.gate(m10, rob, wf["trials"], oos_stress=mst)
    bd = boundary_dependency(wf["oos"], m10, eod)
    th = thirds(c10["equity"]); sc = scale_invariance(c10["equity"], c100["equity"])
    slot = START_CASH[0] * sizing["gross_cap"] / sizing["max_positions"]
    dl = delisting_stress(market, c10["trades"], START_CASH[0], slot, m10.get("total_return", 0.0))
    booleans = {
        "oos_positive": bool(gate["checks"].get("oos_positive")),
        "survives_fees_x1.25": bool(gate["checks"].get("survives_fees_x1.25")),
        "survives_fees_x1.25_oos": bool(gate["checks"].get("survives_fees_x1.25_oos")),
        "oos_trades>=100": m10.get("trades", 0) >= MIN_OOS_TRADES,
        "thirds_2_of_3": th["ok"], "scale_invariant": sc["ok"],
        "symbols>=min": bool(gate["checks"].get("symbols>=min")), "not_single_year": bool(gate["checks"].get("not_single_year")),
        "not_top3_dependent": bool(gate["checks"].get("not_top3_dependent")), "delisting_canonical": dl["canonical_ok"],
        "boundary_dependency_ok": bd["ok"],
    }
    if role != "candidate":
        verdict = "n/a (" + role + ")"
    elif not bd["ok"]:
        verdict = "inconclusive"
    else:
        verdict = "research_accepted_pending_review" if all(booleans.values()) else "rejected"
    rec.update({"oos_continuous": m10, "oos_continuous_fee_stress": mst, "gate_checks": gate["checks"], "advancement": booleans, "verdict": verdict,
                "boundary": bd, "thirds": th, "scale": sc, "delisting": dl, "no_fill_reasons": c10["no_fill_reasons"],
                "per_regime_state": per_state(c10["trades"], series) if series is not None else None,
                "monte_carlo": research.monte_carlo(c10), "pnl_by_year": m10.get("pnl_by_year"), "pnl_by_symbol_top": dict(sorted((m10.get("pnl_by_symbol") or {}).items(), key=lambda kv: -abs(kv[1]))[:10])})
    return rec


def run_table(market, names=None, with_sensitivities=True):
    universe = monthly_universe(market)
    series = regime_mod.compute_series(market)
    table = {"frozen_rules": "docs/desk/PHASE4-PREREGISTRATION.md v2 (R-S FINAL)", "data_hash": market.fingerprint(), "universe_hash": market.universe_fingerprint(),
             "universe_schedule": universe.manifest(), "costs": {k: v.as_record() for k, v in COSTS.items()}, "sizing": SIZING, "regime": series.manifest(market), "candidates": {}}
    for name in (names or list(CANDIDATES)):
        rec = evaluate(market, name, universe, series)
        if with_sensitivities and CANDIDATES[name][2] == "candidate" and rec.get("folds"):
            rec["sensitivity"] = {}
            for label, sz in (("cap_0.95", SIZING["cap_0.95"]), ("cap_0.90", SIZING["cap_0.90"])):
                c = continuous_oos(market, lambda **kw: CANDIDATES[name][0](**kw), rec["folds"], COSTS["canonical"], sz, START_CASH[0], universe)
                m = summarize(c); rec["sensitivity"][label] = {k: m.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}
            c = continuous_oos(market, lambda **kw: CANDIDATES[name][0](**kw), rec["folds"], COSTS["severe"], SIZING["canonical"], START_CASH[0], universe)
            m = summarize(c); rec["sensitivity"]["severe_costs"] = {k: m.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}
        table["candidates"][name] = rec
    return table

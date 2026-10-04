"""Walk-forward, robustness, Monte Carlo, the anti-overfit gate, and the run manifest."""
import dataclasses, hashlib, json, random, statistics as st, time
from .engine import run
from .metrics import summarize
from . import regime as regime_mod


def folds(start_t, end_t, fit_days, test_days, step_days=None):
    """Rolling (fit_start, fit_end, test_start, test_end) windows; test windows never overlap fit windows."""
    step = (step_days or test_days) * 86400
    out, a = [], start_t
    while a + (fit_days + test_days) * 86400 <= end_t:
        fe = a + fit_days * 86400
        out.append((a, fe, fe, min(fe + test_days * 86400, end_t)))
        a += step
    return out


def walk_forward(market, make_strategy, param_grid, costs, fit_days, test_days, select="sharpe", sizing=None, fee_stress=1.25, regime=None, gate_fn=None, universe=None):
    sizing = dict(sizing or {})
    if universe is not None:
        sizing["universe"] = universe      # Phase 4: the frozen monthly schedule applies to EVERY run below — fit, OOS, stress, filtered (R-U)
    stressed = dataclasses.replace(costs, maker_fee=min(0.099, costs.maker_fee * fee_stress), taker_fee=min(0.099, costs.taker_fee * fee_stress), tier=f"{costs.tier} x{fee_stress}")
    """For each fold: run every param set on the fit window, pick the best by `select`, run it on the test window.
    Returns per-fold picks and the concatenated out-of-sample trades/metrics. Trial count is recorded (multiple testing)."""
    times = sorted({b.t for s in market.symbols() for b in market.bars[s]})
    fs = folds(times[0], times[-1] + market.bar_seconds, fit_days, test_days)
    picks, oos_equity, oos_trades, trials = [], [], [], 0
    st_equity, st_trades = [], []            # the same OOS procedure under stressed fees (R-O): selection still on base costs
    f_equity, f_trades, fs_equity, fs_trades = [], [], [], []   # Phase 3: regime-filtered twin on the SAME picks and folds (design §8/§10)
    for (a, fe, ts, te) in fs:
        best = None
        for params in param_grid:
            trials += 1
            m = summarize(run(market, make_strategy(**params), costs, start_t=a, end_t=fe, **sizing))
            score = m.get(select) or -1e9
            if best is None or score > best[0]:
                best = (score, params)
        r = run(market, make_strategy(**best[1]), costs, start_t=ts, end_t=te, **sizing)
        picks.append({"fit": (a, fe), "test": (ts, te), "params": best[1], "fit_score": best[0]})
        oos_trades += r["trades"]
        # chain equity multiplicatively across folds
        scale = oos_equity[-1][1] / r["equity"][0][1] if oos_equity else 1.0
        oos_equity += [(t, e * scale) for t, e in r["equity"]]
        r2 = run(market, make_strategy(**best[1]), stressed, start_t=ts, end_t=te, **sizing)
        st_trades += r2["trades"]
        scale2 = st_equity[-1][1] / r2["equity"][0][1] if st_equity else 1.0
        st_equity += [(t, e * scale2) for t, e in r2["equity"]]
        if regime is not None:
            gated = (gate_fn or (lambda f: f))(make_strategy(**best[1]))
            r3 = run(market, gated, costs, start_t=ts, end_t=te, regime=regime, **sizing)
            f_trades += r3["trades"]; sc3 = f_equity[-1][1] / r3["equity"][0][1] if f_equity else 1.0
            f_equity += [(t, e * sc3) for t, e in r3["equity"]]
            r4 = run(market, (gate_fn or (lambda f: f))(make_strategy(**best[1])), stressed, start_t=ts, end_t=te, regime=regime, **sizing)
            fs_trades += r4["trades"]; sc4 = fs_equity[-1][1] / r4["equity"][0][1] if fs_equity else 1.0
            fs_equity += [(t, e * sc4) for t, e in r4["equity"]]
    oos = summarize({"equity": oos_equity, "trades": oos_trades}) if oos_equity else {"error": "no folds"}
    oos_stress = summarize({"equity": st_equity, "trades": st_trades}) if st_equity else {"error": "no folds"}
    out = {"folds": picks, "oos": oos, "oos_fee_stress": oos_stress, "fee_stress": fee_stress, "trials": trials, "test_windows": [(ts, te) for (_, _, ts, te) in fs]}
    if regime is not None:
        out["oos_filtered"] = summarize({"equity": f_equity, "trades": f_trades}) if f_equity else {"error": "no folds"}
        out["oos_filtered_fee_stress"] = summarize({"equity": fs_equity, "trades": fs_trades}) if fs_equity else {"error": "no folds"}
        out["regime"] = {"band": regime.band, "vol_pct": regime.vol_pct}
    return out


CORE_CHECKS = ("oos_positive", "survives_fees_x1.25", "survives_fees_x1.25_oos")
NON_CORE_CHECKS = ("symbols>=min", "not_single_year", "not_top3_dependent", "param_surface_smooth")


def overlay_eligible(gate_result):
    """Design §10 / R-Q: a filtered variant may be evaluated only if the UNFILTERED candidate passes every core check
    and misses at most one non-core check. A strategy that loses money unfiltered is never run filtered."""
    c = (gate_result or {}).get("checks", {})
    if not all(c.get(k) is True for k in CORE_CHECKS):
        return False, "fails a core check unfiltered (oos_positive / fee stress)"
    misses = [k for k in NON_CORE_CHECKS if c.get(k) is False]
    return (len(misses) <= 1), (f"non-core misses: {misses}" if misses else "passes")


def overlay_verdict(oos, oos_filtered, min_trades=100, min_trade_ratio=0.5):
    """Design §10 (a)–(e): filtered beats unfiltered only if ALL hold. Returns {"wins": bool, "checks": {...}}."""
    if not oos or not oos_filtered or "error" in oos or "error" in oos_filtered:
        return {"wins": False, "checks": {"evidence": "missing"}}
    pf = lambda m: m.get("profit_factor") if m.get("profit_factor") not in (None, float("inf")) else (float("inf") if m.get("profit_factor") == float("inf") else -1)
    checks = {
        "higher_oos_return": oos_filtered["total_return"] > oos["total_return"],
        "smaller_oos_drawdown": oos_filtered["max_drawdown"] > oos["max_drawdown"],
        "trade_ratio>=0.5": oos_filtered["trades"] >= min_trade_ratio * oos["trades"],
        "trades>=100": oos_filtered["trades"] >= min_trades,
        "exposure_independent_improvement": ((oos_filtered.get("avg_trade_ret") or -1) > (oos.get("avg_trade_ret") or -1)) or (pf(oos_filtered) > pf(oos)),
    }
    return {"wins": all(checks.values()), "checks": checks, "note": None if checks["exposure_independent_improvement"] else "filter wins only by sitting in cash: not evidence"}


def regime_sensitivity(market, make_strategy, params, costs, fit_days, test_days, sizing=None, gate_fn=None, pairs=None):
    """Design §4: the five non-canonical pairs, descriptive only; never used to choose anything."""
    out = {}
    for band, vol_pct in (pairs or regime_mod.PAIRS):
        if (band, vol_pct) == (regime_mod.CANONICAL["band"], regime_mod.CANONICAL["vol_pct"]):
            continue
        series = regime_mod.compute_series(market, band, vol_pct)
        wf = walk_forward(market, make_strategy, [params], costs, fit_days, test_days, sizing=sizing, regime=series, gate_fn=gate_fn)
        out[f"band={band},vol_pct={vol_pct}"] = {k: wf["oos_filtered"].get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")} if "error" not in wf["oos_filtered"] else wf["oos_filtered"]
    return out


def robustness(market, make_strategy, params, costs, perturb=0.2, sizing=None, universe=None):
    sizing = dict(sizing or {})
    if universe is not None:
        sizing["universe"] = universe      # same universe as the tournament verdict run (R-U)
    """Fee stress, parameter neighbourhood, top-winner exclusion — the shape of the metric surface."""
    base = summarize(run(market, make_strategy(**params), costs, **sizing))
    out = {"base": base, "fees_x1.25": None, "fees_x1.5": None, "neighbours": []}
    for k, mult in (("fees_x1.25", 1.25), ("fees_x1.5", 1.5)):
        c2 = dataclasses.replace(costs, maker_fee=min(0.099, costs.maker_fee * mult), taker_fee=min(0.099, costs.taker_fee * mult), tier=f"{costs.tier} x{mult}")
        out[k] = summarize(run(market, make_strategy(**params), c2, **sizing))
    for key, val in params.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            for f in (1 - perturb, 1 + perturb):
                p2 = dict(params); p2[key] = type(val)(val * f) if isinstance(val, int) else val * f
                try:
                    out["neighbours"].append({"param": key, "value": p2[key], "metrics": summarize(run(market, make_strategy(**p2), costs, **sizing))})
                except Exception as e:
                    out["neighbours"].append({"param": key, "value": p2[key], "error": str(e)})
    return out


def monte_carlo(result, n=500, block=20, seed=7):
    """Block bootstrap of the strategy's daily returns: distribution of terminal multiple and max drawdown."""
    vals = [e for _, e in result["equity"]]
    rets = [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1] > 0]
    if len(rets) < block * 2:
        return {"error": "too few returns"}
    rng = random.Random(seed)
    terms, mdds = [], []
    for _ in range(n):
        seq, eq, peak, mdd = [], 1.0, 1.0, 0.0
        while len(seq) < len(rets):
            i = rng.randrange(0, len(rets) - block); seq += rets[i:i + block]
        for r in seq[:len(rets)]:
            eq *= 1 + r; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
        terms.append(eq); mdds.append(mdd)
    terms.sort(); mdds.sort()
    q = lambda xs, p: xs[int(p * (len(xs) - 1))]
    return {"n": n, "block": block, "seed": seed, "terminal_p05": q(terms, .05), "terminal_p50": q(terms, .5), "terminal_p95": q(terms, .95), "mdd_p05": q(mdds, .05), "mdd_p50": q(mdds, .5)}


def gate(oos, rob, trials, min_symbols=3, oos_stress=None):
    """Anti-overfit rules (architecture §11). Any failing rule rejects; missing evidence is inconclusive.
    Fee stress must survive BOTH the full-sample robustness run and the OOS walk-forward under stressed fees (R-O);
    a missing OOS stress result fails the check, it never passes by omission."""
    checks = {}
    if not oos or "error" in oos:
        return {"verdict": "inconclusive", "checks": {"oos": "missing"}}
    checks["oos_positive"] = oos["total_return"] > 0
    checks["symbols>=min"] = oos.get("symbols_with_profit", 0) >= min_symbols
    yrs = [v for v in oos.get("pnl_by_year", {}).values()]
    checks["not_single_year"] = len(yrs) >= 2 and sum(1 for v in yrs if v > 0) >= 2 if yrs else False
    total_pnl = sum(yrs) if yrs else 0
    full_ok = bool(rob and rob.get("fees_x1.25") and rob["fees_x1.25"]["total_return"] > 0)
    oos_ok = bool(oos_stress and "error" not in oos_stress and oos_stress["total_return"] > 0)
    checks["survives_fees_x1.25"] = full_ok and oos_ok
    checks["survives_fees_x1.25_oos"] = oos_ok
    ex3 = oos.get("pnl_ex_top", {}).get(3)
    checks["not_top3_dependent"] = (ex3 is not None and total_pnl > 0 and ex3 > 0.5 * total_pnl)
    nb = [x["metrics"]["total_return"] for x in (rob or {}).get("neighbours", []) if "metrics" in x]
    checks["param_surface_smooth"] = (len(nb) == 0) or (sum(1 for r in nb if r > 0) >= len(nb) / 2)
    checks["trials_recorded"] = trials is not None
    failed = [k for k, v in checks.items() if v is False]
    return {"verdict": "rejected" if failed else "accepted", "checks": checks, "failed": failed, "trials": trials}


def manifest(strategy, params, market, costs, fill_rule, folds_info, seeds, metrics, rob, gate_result, code_sha=None, data_vintage=None, notes=None, sizing=None, regime=None):
    # sizing is part of the config hash: a 90% deployment strategy is economically different from a 100% one (R-H).
    sizing = sizing or {"rule": "slot", "gross_cap": 1.0, "max_positions": 10}
    cfg = {"strategy": strategy, "params": params, "costs": costs.as_record(), "fill_rule": fill_rule, "sizing": sizing, "regime": regime}
    config_hash = hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]
    run_id = f"{strategy}-{config_hash}-{market.fingerprint()}-{int(time.time())}"
    return {
        "run_id": run_id, "strategy": strategy, "params": params, "config_hash": config_hash, "code_sha": code_sha,
        "data_hash": market.fingerprint(), "universe_hash": market.universe_fingerprint(), "data_vintage": data_vintage,
        "costs": costs.as_record(), "fill_rule": fill_rule, "sizing": sizing, "regime": regime, "folds": folds_info, "seeds": seeds,
        "trial_count": (gate_result or {}).get("trials"), "metrics": metrics, "robustness": rob, "gate": gate_result,
        "verdict": (gate_result or {}).get("verdict", "inconclusive"), "notes": notes,
    }

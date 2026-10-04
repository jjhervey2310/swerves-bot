"""Phase 4 ROUND 2 — docs/desk/PHASE4-ROUND2-PREREGISTRATION.md v2, FROZEN (R-X). Post-Round-1 hypothesis screening:
outcomes are exactly historical_survivor / historical_rejected / inconclusive; nothing here can emit research_accepted.
Every constant a verdict depends on lives in this module; nothing is written to research_runs."""
import dataclasses, datetime as dt, statistics as st
from bt_costs import scaled
from .engine import run
from .metrics import summarize
from . import research, strategies, tournament as T, sentiment as S, regime as regime_mod

OUTCOMES = ("historical_survivor", "historical_rejected", "inconclusive")
FIT_DAYS, TEST_DAYS = T.FIT_DAYS, T.TEST_DAYS
COSTS = {"canonical": T.COSTS["canonical"], "stress": scaled(T.COSTS["canonical"], 1.25), "severe": T.COSTS["severe"]}
ONE_SLOT = {"max_positions": 1, "gross_cap": 1.0}            # declared deviation for single-asset rules (A, C)
TEN_SLOT = T.SIZING["canonical"]
START_CASH = T.START_CASH
A_FALSIFIER = {"return_share": 0.70, "dd_reduction": 0.30}   # R_A >= R_BH, or R_A >= 0.70*R_BH and |DD_A| <= 0.70*|DD_BH|
B_BREADTH_FLOOR, B_MEMBERS_REQUIRED = 0.50, 20
C_HOLD_BARS, C_HOLD_SENSITIVITY, C_HORIZON = 90, 30, 90
C_COVERAGE = {"min_share": 0.80, "max_gap_days": 30}
C_ASSUMED_LAG_DAYS = 1                                        # option (ii): reading dated D usable from the close of D+1

CANDIDATES = {
    "A_btc_trend": {"class": "S", "min_episodes": 10, "sizing": ONE_SLOT, "universe": False, "exog": False,
                    "factory": lambda **kw: strategies.sma_trend(["BTC"], **kw), "grid": [{"fast": 20, "slow": 100}, {"fast": 50, "slow": 200}],
                    "provenance": "post-Round-1 decomposition hypothesis (same SMA family and grid as the rejected broad-alt sma_trend, restricted to BTC)",
                    "falsifier": "R_A >= R_BH, or R_A >= 0.70*R_BH and max DD reduced by >= 30% relative; positive after canonical and x1.25 costs"},
    "B_momentum_floor": {"class": "X", "min_trades": T.MIN_OOS_TRADES, "sizing": TEN_SLOT, "universe": True, "exog": False,
                         "factory": lambda **kw: strategies.momentum_floor(breadth_floor=B_BREADTH_FLOOR, members_required=B_MEMBERS_REQUIRED, **kw),
                         "grid": [{"n": n, "lookback": l} for n in (3, 5) for l in (60, 90)],
                         "provenance": "post-Round-1 response (rejected momentum_top lost through 2022; the breadth cash floor is the hypothesis)",
                         "falsifier": "floor variant beats the no-floor twin (same per-fold picks) on continuous OOS return AND max DD AND profit factor"},
    "C_fear_greed": {"class": "S", "min_episodes": 8, "sizing": ONE_SLOT, "universe": False, "exog": True,
                     "factory": lambda **kw: strategies.fear_greed_timing(hold_bars=C_HOLD_BARS, **kw), "grid": [{"threshold": 20}, {"threshold": 25}],
                     "provenance": "architecture H-SWEEP-A as a hypothesis; written after round 1, so screening status applies",
                     "falsifier": "mean and hit rate of the 90-day forward BTC return after executed entries both exceed the unconditional 90-day mean and hit rate over the OOS span"},
}


# ---------------------------------------------------------------- shared machinery
def continuous(market, factory, picks, costs, sizing, start_cash, universe=None, exog=None):
    ts0, te1 = picks[0]["test"][0], picks[-1]["test"][1]
    return run(market, T._switching_strategy(factory, picks), costs, start_cash=start_cash, start_t=ts0, end_t=te1, universe=universe, exog=exog, **sizing)


def _common(market, factory, grid, sizing, universe, exog, fit_days, test_days):
    """Walk-forward selection (fit windows only), per-fold boundary exits, continuous verdict curves at $10k/$100k and
    under x1.25 stress, robustness surface, round-1 gate checks, boundary/thirds/scale/delisting blocks."""
    costs = COSTS["canonical"]
    wf = research.walk_forward(market, factory, grid, costs, fit_days, test_days, sizing=sizing, universe=universe, exog=exog, stress_costs=COSTS["stress"])
    if not wf["folds"]:
        return None
    eod = 0
    for p in wf["folds"]:
        r = run(market, factory(**p["params"]), costs, start_t=p["test"][0], end_t=p["test"][1], universe=universe, exog=exog, **sizing)
        eod += sum(1 for t in r["trades"] if t.reason == "eod")
    c10 = continuous(market, factory, wf["folds"], costs, sizing, START_CASH[0], universe, exog)
    c100 = continuous(market, factory, wf["folds"], costs, sizing, START_CASH[1], universe, exog)
    cst = continuous(market, factory, wf["folds"], COSTS["stress"], sizing, START_CASH[0], universe, exog)
    csev = continuous(market, factory, wf["folds"], COSTS["severe"], sizing, START_CASH[0], universe, exog)
    m10, mst, msev = summarize(c10), summarize(cst), summarize(csev)
    rob = research.robustness(market, factory, wf["folds"][-1]["params"], costs, sizing=sizing, universe=universe, exog=exog)
    gate = research.gate(m10, rob, wf["trials"], oos_stress=mst)
    slot = START_CASH[0] * sizing["gross_cap"] / sizing["max_positions"]
    return {"wf": wf, "eod": eod, "c10": c10, "c100": c100, "cst": cst, "m10": m10, "mst": mst, "msev": msev, "rob": rob, "gate": gate,
            "boundary": T.boundary_dependency(wf["oos"], m10, eod), "thirds": T.thirds(c10["equity"]), "scale": T.scale_invariance(c10["equity"], c100["equity"]),
            "delisting": T.delisting_stress(market, c10["trades"], START_CASH[0], slot, m10.get("total_return", 0.0)), "span": (wf["folds"][0]["test"][0], wf["folds"][-1]["test"][1])}


def completed_episodes(trades):
    """Round trips the rule itself closed; the forced end-of-sample liquidation is not an episode."""
    return [t for t in trades if t.reason != "eod"]


def class_s_booleans(x):
    m = x["m10"]; by_year = m.get("pnl_by_year") or {}; total = sum(by_year.values())
    ex3 = (m.get("pnl_ex_top") or {}).get(3)
    return {"oos_positive": m.get("total_return", 0) > 0, "positive_x1.25": x["mst"].get("total_return", 0) > 0,
            "thirds_2_of_3": x["thirds"]["ok"], "positive_years>=2": sum(1 for v in by_year.values() if v > 0) >= 2,
            "scale_invariant": x["scale"]["ok"], "boundary_dependency_ok": x["boundary"]["ok"],
            "ex_top3_trades>50%": ex3 is not None and total > 0 and ex3 > 0.5 * total}


def class_x_booleans(x):
    g = x["gate"]["checks"]; m = x["m10"]
    return {"oos_positive": bool(g.get("oos_positive")), "survives_fees_x1.25": bool(g.get("survives_fees_x1.25")), "survives_fees_x1.25_oos": bool(g.get("survives_fees_x1.25_oos")),
            f"oos_trades>={T.MIN_OOS_TRADES}": m.get("trades", 0) >= T.MIN_OOS_TRADES, "thirds_2_of_3": x["thirds"]["ok"], "scale_invariant": x["scale"]["ok"],
            "symbols>=min": bool(g.get("symbols>=min")), "not_single_year": bool(g.get("not_single_year")), "not_top3_dependent": bool(g.get("not_top3_dependent")),
            "delisting_canonical": x["delisting"]["canonical_ok"], "boundary_dependency_ok": x["boundary"]["ok"]}


def outcome(booleans, falsifier_ok, episodes, minimum, boundary_ok, extra_inconclusive=None):
    if extra_inconclusive:
        return "inconclusive", extra_inconclusive
    if not boundary_ok:
        return "inconclusive", "fold-boundary dependency (continuous run to be reviewed)"
    if episodes < minimum:
        return "inconclusive", f"episodes {episodes} < minimum {minimum}"
    if all(booleans.values()) and falsifier_ok:
        return "historical_survivor", None
    failed = [k for k, v in booleans.items() if not v] + ([] if falsifier_ok else ["falsifier"])
    return "historical_rejected", ", ".join(failed)


# ---------------------------------------------------------------- benchmarks and falsifiers
def btc_buy_and_hold(market, span, sizing, start_cash=START_CASH[0]):
    a, b = span
    r = run(market, strategies.buy_and_hold(["BTC"]), COSTS["canonical"], start_cash=start_cash, start_t=a, end_t=b, **sizing)
    return summarize(r)


def a_falsifier(m_a, m_bh):
    ra, rbh = m_a.get("total_return", 0.0), m_bh.get("total_return", 0.0)
    dda, ddbh = abs(m_a.get("max_drawdown", 0.0)), abs(m_bh.get("max_drawdown", 0.0))
    beats = ra >= rbh if rbh > 0 else ra > 0
    partial = rbh > 0 and ra >= A_FALSIFIER["return_share"] * rbh and dda <= (1 - A_FALSIFIER["dd_reduction"]) * ddbh
    return {"ok": bool(beats or partial), "R_A": ra, "R_BH": rbh, "DD_A": -dda, "DD_BH": -ddbh, "beats_return": beats, "partial_clause": partial}


def b_twin(market, picks, sizing, universe, start_cash=START_CASH[0]):
    """No-floor twin on the EXACT per-fold picks (R-W #4): same rule, same parameters, floor branch skipped."""
    twin = lambda **kw: strategies.momentum_floor(breadth_floor=B_BREADTH_FLOOR, members_required=B_MEMBERS_REQUIRED, floor=False, **kw)
    return summarize(continuous(market, twin, picks, COSTS["canonical"], sizing, start_cash, universe))


def b_falsifier(m_floor, m_twin):
    pf = lambda m: m.get("profit_factor") if m.get("profit_factor") is not None else -1.0
    checks = {"higher_return": m_floor.get("total_return", 0) > m_twin.get("total_return", 0),
              "smaller_drawdown": m_floor.get("max_drawdown", -1) > m_twin.get("max_drawdown", -1),
              "higher_profit_factor": pf(m_floor) > pf(m_twin)}
    return {"ok": all(checks.values()), "checks": checks, "twin": {k: m_twin.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}}


def forward_returns(market, span, horizon=C_HORIZON, btc="BTC"):
    """horizon-bar forward BTC close-to-close returns for every completed bar whose decision close lies in the span."""
    bs = market.bars[btc]; a, b = span; out = {}
    for k in range(len(bs) - horizon):
        t_dec = bs[k].t + market.bar_seconds
        if a <= t_dec < b and bs[k + horizon].t == bs[k].t + horizon * market.bar_seconds:
            out[t_dec] = bs[k + horizon].c / bs[k].c - 1
    return out


def c_falsifier(market, trades, span, horizon=C_HORIZON):
    """Same non-overlapping executed signals (entry decision = fill open) vs the unconditional base rate (R-W #3)."""
    fwd = forward_returns(market, span, horizon)
    sig = [fwd[t.entry_t] for t in trades if t.entry_t in fwd]
    base = list(fwd.values())
    stat = lambda xs: {"n": len(xs), "mean": st.mean(xs) if xs else None, "hit": (sum(1 for x in xs if x > 0) / len(xs)) if xs else None}
    s_, b_ = stat(sig), stat(base)
    ok = bool(sig) and s_["mean"] is not None and b_["mean"] is not None and s_["mean"] > b_["mean"] and s_["hit"] > b_["hit"]
    return {"ok": ok, "horizon": horizon, "signals": s_, "base_rate": b_}


def c_event_study(market, series, threshold, span, horizon=C_HORIZON):
    """Descriptive only (never the acceptance statistic): every day with a usable reading <= threshold, overlapping."""
    fwd = forward_returns(market, span, horizon); xs = []
    for t_dec, r in fwd.items():
        rd = series.at(t_dec)
        if rd is not None and rd["value"] <= threshold:
            xs.append(r)
    return {"n_days": len(xs), "mean": st.mean(xs) if xs else None, "hit": (sum(1 for x in xs if x > 0) / len(xs)) if xs else None, "note": "overlapping fear days are correlated; descriptive"}


# ---------------------------------------------------------------- per-candidate evaluation
def evaluate(market, name, universe, series, sentiment_rows=None, fit_days=FIT_DAYS, test_days=TEST_DAYS, evidence_class=None):
    spec = CANDIDATES[name]; sizing = spec["sizing"]; uni = universe if spec["universe"] else None
    rec = {"candidate": name, "class": spec["class"], "provenance": spec["provenance"], "falsifier_rule": spec["falsifier"], "grid": spec["grid"], "sizing": sizing}
    exog = None
    if spec["exog"]:
        if evidence_class == S.ASSUMED_LAG_LABEL:
            fg = S.assumed_availability(sentiment_rows or [], lag_days=C_ASSUMED_LAG_DAYS)
        else:
            fg = S.from_rows(sentiment_rows or [])
        exog = {"fear_greed": fg}; rec["evidence_class"] = fg.evidence_class; rec["sentiment"] = fg.manifest()
    x = _common(market, spec["factory"], spec["grid"], sizing, uni, exog, fit_days, test_days)
    if x is None:
        rec.update({"outcome": "inconclusive", "reason": "no folds"}); return rec
    m = x["m10"]; eps = completed_episodes(x["c10"]["trades"])
    rec.update({"trials": x["wf"]["trials"], "folds": x["wf"]["folds"], "oos_chained": x["wf"]["oos"], "oos_continuous": m, "oos_continuous_x1.25": x["mst"], "oos_continuous_severe": x["msev"],
                "boundary": x["boundary"], "thirds": x["thirds"], "scale": x["scale"], "delisting": x["delisting"], "gate_checks": x["gate"]["checks"],
                "episodes_completed": len(eps), "stale_marks": x["c10"]["stale_marks"], "no_fill_reasons": x["c10"]["no_fill_reasons"],
                "pnl_by_year": m.get("pnl_by_year"), "monte_carlo": research.monte_carlo(x["c10"]),
                "per_regime_state": T.per_state(x["c10"]["trades"], series) if series is not None else None, "span": x["span"]})
    extra_inc = None
    if spec["class"] == "S":
        booleans = class_s_booleans(x)
        if name == "A_btc_trend":
            bh = btc_buy_and_hold(market, x["span"], ONE_SLOT); rec["benchmark_btc_bh_100"] = {k: bh.get(k) for k in ("total_return", "max_drawdown", "trades")}
            fal = a_falsifier(m, bh)
        else:
            fal = c_falsifier(market, x["c10"]["trades"], x["span"])
            cov = exog["fear_greed"].coverage(x["span"][0], x["span"][1], **{"max_gap_days": C_COVERAGE["max_gap_days"], "min_share": C_COVERAGE["min_share"]})
            rec["coverage"] = cov
            if cov["inconclusive"]:
                extra_inc = f"F&G coverage share {cov['share']:.2f} / longest gap {cov['longest_gap_days']} d ({cov['evidence_class']})"
            picked = x["wf"]["folds"][-1]["params"]["threshold"]
            rec["event_study_all_fear_days"] = c_event_study(market, exog["fear_greed"], picked, x["span"])
            sens = lambda **kw: strategies.fear_greed_timing(hold_bars=C_HOLD_SENSITIVITY, **kw)
            ms = summarize(continuous(market, sens, x["wf"]["folds"], COSTS["canonical"], sizing, START_CASH[0], None, exog))
            rec["sensitivity_hold_30"] = {k: ms.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}
            rec["signals"] = {"executed_entries": len(x["c10"]["trades"])}
        ten = summarize(continuous(market, spec["factory"], x["wf"]["folds"], COSTS["canonical"], TEN_SLOT, START_CASH[0], None, exog))
        rec["sensitivity_10_slot"] = {k: ten.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}
        rec["falsifier"] = fal
        out, why = outcome(booleans, fal["ok"], len(eps), spec["min_episodes"], x["boundary"]["ok"], extra_inc)
    else:
        booleans = class_x_booleans(x)
        fal = b_falsifier(m, b_twin(market, x["wf"]["folds"], sizing, uni)); rec["falsifier"] = fal
        rec["sensitivity"] = {}
        for label, sz in (("cap_0.95", T.SIZING["cap_0.95"]), ("cap_0.90", T.SIZING["cap_0.90"])):
            mm = summarize(continuous(market, spec["factory"], x["wf"]["folds"], COSTS["canonical"], sz, START_CASH[0], uni))
            rec["sensitivity"][label] = {k: mm.get(k) for k in ("total_return", "max_drawdown", "trades", "profit_factor")}
        out, why = outcome(booleans, fal["ok"], m.get("trades", 0), spec["min_trades"], x["boundary"]["ok"])
        if out == "inconclusive" and why and why.startswith("episodes"):
            out, why = "historical_rejected", f"oos_trades {m.get('trades', 0)} < {spec['min_trades']}"      # class X keeps the round-1 trade hurdle as a gate, not an episode minimum
    if spec["exog"] and rec.get("evidence_class") == S.ASSUMED_LAG_LABEL and out == "historical_survivor":
        out = "historical_survivor (assumed availability)"
    rec.update({"booleans": booleans, "outcome": out, "reason": why, "research_accepted": False, "trade_approved": False})
    return rec


def run_table(market, sentiment_rows, names=None, fit_days=FIT_DAYS, test_days=TEST_DAYS, with_regime=True, log=print):
    universe = T.monthly_universe(market)
    series = regime_mod.compute_series(market) if with_regime else None
    table = {"frozen_rules": "docs/desk/PHASE4-ROUND2-PREREGISTRATION.md v2 (R-X FROZEN); round-1 rules inherited (R-S FINAL)",
             "status_rule": "post-Round-1 hypothesis screening: outcomes historical_survivor / historical_rejected / inconclusive; research_accepted only via the forward-validation stage",
             "data_hash": market.fingerprint(), "universe_hash": market.universe_fingerprint(), "universe_schedule": universe.manifest(),
             "costs": {k: v.as_record() for k, v in COSTS.items()}, "regime": series.manifest(market) if series is not None else None, "candidates": {}, "trials_total": 0}
    for name in (names or list(CANDIDATES)):
        log(f"round 2: {name} ...")
        if name == "C_fear_greed":
            ver = evaluate(market, name, universe, series, sentiment_rows, fit_days, test_days, evidence_class="verified")
            table["candidates"][name + "__verified"] = ver
            rec = evaluate(market, name, universe, series, sentiment_rows, fit_days, test_days, evidence_class=S.ASSUMED_LAG_LABEL)
        else:
            rec = evaluate(market, name, universe, series, sentiment_rows, fit_days, test_days)
        table["candidates"][name] = rec; table["trials_total"] += rec.get("trials") or 0
        log(f"  {rec['outcome']}  {rec.get('reason') or ''}  oos {rec.get('oos_continuous', {}).get('total_return')}")
    span = next((r["span"] for r in table["candidates"].values() if r.get("span")), None)
    if span:
        table["benchmarks"] = {"btc_bh_100pct": btc_buy_and_hold(market, span, ONE_SLOT), "btc_bh_10pct_slot": btc_buy_and_hold(market, span, TEN_SLOT),
                               "cash": summarize(run(market, strategies.cash(), COSTS["canonical"], start_t=span[0], end_t=span[1], **TEN_SLOT))}
        table["benchmarks"] = {k: {kk: v.get(kk) for kk in ("total_return", "max_drawdown", "trades", "profit_factor")} for k, v in table["benchmarks"].items()}
        table["negative_control"] = {k: v for k, v in T.evaluate(market, "breakout20", universe, series, fit_days=fit_days, test_days=test_days).items() if k in ("oos_continuous", "advancement", "verdict", "boundary")}
        table["oos_span"] = span
    return table


def render(table):
    pct = lambda x: "—" if x is None else f"{x * 100:+.1f}%"
    L = [f"# Phase 4 round 2 table — {dt.date.today()} (FROZEN v2, R-X; screening only; nothing in research_runs)", "",
         f"data_hash `{table['data_hash']}` · universe_hash `{table['universe_hash']}` · membership_hash `{table['universe_schedule']['membership_hash']}` · trials {table['trials_total']}", "",
         "| candidate | class | evidence | episodes/trades | OOS cont. | ×1.25 | severe | maxDD | PF | thirds | scale | boundary | falsifier | outcome |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for n, r in table["candidates"].items():
        if "oos_continuous" not in r:
            L.append(f"| {n} | {r.get('class')} | {r.get('evidence_class', '—')} | — | — | — | — | — | — | — | — | — | — | {r['outcome']} ({r.get('reason')}) |"); continue
        m = r["oos_continuous"]; ep = r.get("episodes_completed") if r["class"] == "S" else m.get("trades")
        L.append(f"| {n} | {r['class']} | {r.get('evidence_class', '—')} | {ep} | {pct(m.get('total_return'))} | {pct(r['oos_continuous_x1.25'].get('total_return'))} | {pct(r['oos_continuous_severe'].get('total_return'))} | {pct(m.get('max_drawdown'))} | "
                 f"{'—' if m.get('profit_factor') is None else round(m['profit_factor'], 2)} | {'✓' if r['thirds']['ok'] else '✗'} | {'✓' if r['scale']['ok'] else '✗'} | {'✓' if r['boundary']['ok'] else '✗'} | {'✓' if r['falsifier']['ok'] else '✗'} | **{r['outcome']}**{(' — ' + r['reason']) if r.get('reason') else ''} |")
    for k, v in (table.get("benchmarks") or {}).items():
        L.append(f"| {k} | benchmark | — | {v.get('trades')} | {pct(v.get('total_return'))} | — | — | {pct(v.get('max_drawdown'))} | — | — | — | — | — | n/a |")
    if table.get("negative_control"):
        c = table["negative_control"]; L.append(f"| breakout20 | negative_control | — | {c['oos_continuous'].get('trades')} | {pct(c['oos_continuous'].get('total_return'))} | — | — | {pct(c['oos_continuous'].get('max_drawdown'))} | — | — | — | {'✓' if c['boundary']['ok'] else '✗'} | — | n/a |")
    L += ["", "## Booleans, falsifiers, provenance", ""]
    for n, r in table["candidates"].items():
        if "booleans" in r:
            L.append(f"- **{n}** ({r['provenance']}): " + ", ".join(f"{k}={'T' if v else 'F'}" for k, v in r["booleans"].items()) + f"; falsifier {r['falsifier']}")
            for k in ("benchmark_btc_bh_100", "sensitivity_10_slot", "sensitivity", "sensitivity_hold_30", "coverage", "event_study_all_fear_days", "signals", "stale_marks", "delisting"):
                if r.get(k) is not None:
                    v = r[k]; L.append(f"  - {k}: {({kk: v[kk] for kk in v if kk != 'cases'} if isinstance(v, dict) else v)}")
    L += ["", "## Per regime state (filter OFF, descriptive)", ""]
    for n, r in table["candidates"].items():
        if r.get("per_regime_state"):
            L.append(f"- **{n}**: " + "; ".join(f"{k}: {v['trades']} trades, P&L {v['pnl']:+.0f}" for k, v in r["per_regime_state"].items()))
    return "\n".join(L)

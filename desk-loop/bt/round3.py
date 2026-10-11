"""Phase 4 ROUND 3 — runner forensics. FROZEN: pre-registration v3 (R-AE) and Stage 0 feature manifest v2 (R-AH).
Every definition here is a constant of the frozen documents; nothing is tuned after labels exist. Two separate pipelines
(verified / assumed) with separate outcomes; outcomes are historical_survivor / historical_rejected / inconclusive and
never research_accepted. Nothing is written to research_runs."""
import bisect, datetime as dt, json, math, statistics as st
import numpy as np
from . import tournament as T

DAY = 86400
FORMATION_MONTHS = [(y, m) for y in range(2021, 2026) for m in range(1, 13) if (y, m) >= (2021, 3) and (y, m) <= (2025, 11)]   # 57
MIN_BARS, LIQ_FLOOR_USD, HORIZON = 90, 250_000.0, 180
EXCLUDE = T.EXCLUDE
TIERS = {"runner_2x": 2.0, "runner_3x": 3.0, "runner_5x": 5.0}
TEST_YEARS = (2022, 2023, 2024, 2025)
C_GRID = (0.1, 1.0)
TOP_SHARE, MIN_POSITIVES_TOTAL, MIN_POSITIVES_YEAR = 0.10, 40, 5
GATE = {"pooled_lift": 2.0, "year_lift": 1.5, "years_needed": 3}
ASSUMED_LAG_DAYS = 7
CONTROL_TOL = 0.25            # negative control must sit at base rate: |lift - 1| <= tol, else the table is invalid
PERMUTATIONS = 1000
VERIFIED = ["ret_30", "ret_90", "rs_btc_7", "rs_btc_30", "rs_btc_90", "dv_accel_7_30", "dv_accel_30_90", "vol_z_20", "dist_hi_90", "dist_hi_365",
            "dd_listing_high", "rv_20", "rv_60", "age_bars", "log_dv_90", "breadth_ctx"]
FUNDAMENTAL = ["fees_growth_30", "rev_growth_30", "rev_yield", "tvl_change_30"]
ASSUMED = FUNDAMENTAL + ["stable_supply_30"] + [f + "_missing" for f in FUNDAMENTAL] + ["has_family"]


def _month(t):
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc); return (d.year, d.month)


def formation_times(market):
    """First decision close of each UTC month in FORMATION_MONTHS: the close of the month's first completed bar."""
    bar = market.bar_seconds
    dec = sorted({b.t + bar for bs in market.bars.values() for b in bs})
    out, seen = [], set()
    for t in dec:
        ym = _month(t - bar)
        if ym in FORMATION_MONTHS and ym not in seen:
            seen.add(ym); out.append(t)
    return out


def median3_dv(bars):
    return st.median(b.c * b.v for b in bars[-3:])


def candidate_set(market, t_dec):
    """FROZEN pre-feature candidate set: listed, >= MIN_BARS contiguous completed bars ending at the close, 3-day median
    dollar volume >= floor, not excluded, executable next open. Later-delisted names included. Returns [symbol]."""
    bar = market.bar_seconds; out = []
    for s in market.symbols():
        if s in EXCLUDE: continue
        a, d = market.listings.get(s, (None, None))
        if a is None or a > t_dec or (d is not None and t_dec >= d): continue
        ts = market._ts[s]; i = bisect.bisect_right(ts, t_dec - bar)
        if i < MIN_BARS or ts[i - 1] != t_dec - bar or ts[i - MIN_BARS] != t_dec - MIN_BARS * bar: continue
        bs = market.bars[s][:i]
        if median3_dv(bs) < LIQ_FLOOR_USD: continue
        if market.bar_opening_at(s, t_dec) is None: continue
        out.append(s)
    return out


def labels(market, s, t_dec):
    """FROZEN: entry_reference = open of the bar opening at t_dec; M = max completed close over the next HORIZON bars
    starting at that bar (fewer if delisted / sample end). Tiers at 2x / 3x / 5x; nothing is excluded by a future label."""
    bs = market.bars[s]; ts = market._ts[s]; i = bisect.bisect_left(ts, t_dec)
    ref = bs[i].o
    win = bs[i:i + HORIZON]
    M = max(b.c for b in win)
    return {"entry_reference": ref, "max_close": M, "bars_in_window": len(win), **{k: M >= v * ref for k, v in TIERS.items()}}


def _sma(xs, n): return sum(xs[-n:]) / n


def verified_features(market, s, t_dec, btc_closes, breadth):
    """FROZEN manifest §2. Returns dict or None when any feature is NaN (the name is verified-feature-ineligible)."""
    bar = market.bar_seconds; ts = market._ts[s]; i = bisect.bisect_right(ts, t_dec - bar)
    bs = market.bars[s][:i]; c = [b.c for b in bs]; v = [b.v for b in bs]; dv = [b.c * b.v for b in bs]
    n = len(c)
    if n < 91 or len(btc_closes) < 91: return None
    f = {}
    f["ret_30"] = c[-1] / c[-31] - 1; f["ret_90"] = c[-1] / c[-91] - 1
    for k, nm in ((7, "rs_btc_7"), (30, "rs_btc_30"), (90, "rs_btc_90")):
        f[nm] = (c[-1] / c[-k - 1]) / (btc_closes[-1] / btc_closes[-k - 1]) - 1
    m30, m90 = sum(dv[-30:]) / 30, sum(dv[-90:]) / 90
    f["dv_accel_7_30"] = (sum(dv[-7:]) / 7) / m30 - 1 if m30 > 0 else float("nan")
    f["dv_accel_30_90"] = m30 / m90 - 1 if m90 > 0 else float("nan")
    w = v[-21:-1]; sd = st.pstdev(w)
    f["vol_z_20"] = (v[-1] - st.mean(w)) / sd if sd > 0 else float("nan")
    f["dist_hi_90"] = c[-1] / max(c[-90:]) - 1; f["dist_hi_365"] = c[-1] / max(c[-365:]) - 1
    f["dd_listing_high"] = c[-1] / max(c) - 1
    lr = [math.log(c[j] / c[j - 1]) for j in range(1, n) if c[j - 1] > 0 and c[j] > 0]
    f["rv_20"] = st.pstdev(lr[-20:]) * math.sqrt(365) if len(lr) >= 20 else float("nan")
    f["rv_60"] = st.pstdev(lr[-60:]) * math.sqrt(365) if len(lr) >= 60 else float("nan")
    f["age_bars"] = math.log1p(n); f["log_dv_90"] = math.log(m90) if m90 > 0 else float("nan")
    f["breadth_ctx"] = breadth
    if any(not math.isfinite(x) for x in f.values()): return None
    return f


def breadth_of(market, t_dec, cands):
    bar = market.bar_seconds; above = 0
    for s in cands:
        i = bisect.bisect_right(market._ts[s], t_dec - bar); c = [b.c for b in market.bars[s][:i]]
        if c[-1] > _sma(c, 50): above += 1
    return above / len(cands) if cands else float("nan")


def quintiles(values):
    """Rank-based quintile 0..4 within a month over the pre-feature candidate set (ties by symbol order given)."""
    order = sorted(range(len(values)), key=lambda k: values[k]); q = [0] * len(values)
    for r, k in enumerate(order): q[k] = min(4, r * 5 // max(1, len(values)))
    return q


# ---------------------------------------------------------------- assumed pipeline inputs (snapshot from bt_round3_backfill)
def _series(points):
    """[[unix, value]] -> {date: value}; a day's value is the LAST point of that UTC date."""
    out = {}
    for t, v in points or []:
        out[dt.datetime.utcfromtimestamp(int(t)).date()] = float(v)
    return out


class LlamaSnapshot:
    def __init__(self, j):
        self.families = j["families"]; self.hash = j.get("hash")
        self.fees = {s: _series(v) for s, v in j["fees"].items()}; self.rev = {s: _series(v) for s, v in j["revenue"].items()}
        self.tvl = {s: _series(v) for s, v in j["tvl"].items()}; self.stable = _series(j["stablecoins"])

    def family(self, sym):
        return self.families.get(sym)

    def _sum(self, table, slugs, day):
        vals = [table[s][day] for s in slugs if s in table and day in table[s]]
        return sum(vals) if vals else None

    def window_sum(self, table, slugs, end, n, listed):
        """Sum over the n days ending `end`; None if ANY day is missing (no forward fill) or falls before listedAt."""
        tot = 0.0
        for k in range(n):
            day = end - dt.timedelta(days=k)
            if day < listed: return None
            x = self._sum(table, slugs, day)
            if x is None: return None
            tot += x
        return tot


def assumed_features(snap, sym, t_dec):
    """FROZEN manifest §3 under the declared lag: Dmax = date(t_dec) - (lag + 1) days, i.e. a value dated D is usable from
    the decision close of D + lag. rev_yield needs a point-in-time market cap that DeFiLlama does not provide -> NaN."""
    fam = snap.family(sym); dmax = (dt.datetime.utcfromtimestamp(t_dec).date() - dt.timedelta(days=ASSUMED_LAG_DAYS + 1))
    f = {k: float("nan") for k in FUNDAMENTAL}; f["has_family"] = 0.0
    if fam:
        f["has_family"] = 1.0; listed = dt.date.fromisoformat(fam["earliest_listedAt"]); fs, ts = fam["fees_slugs"], fam["slugs"]
        for key, table in (("fees_growth_30", snap.fees), ("rev_growth_30", snap.rev)):
            a = snap.window_sum(table, fs, dmax, 30, listed); b = snap.window_sum(table, fs, dmax - dt.timedelta(days=30), 30, listed)
            f[key] = a / b - 1 if a is not None and b is not None and b > 0 else float("nan")
        if dmax >= listed and (dmax - dt.timedelta(days=30)) >= listed:
            t1, t0 = snap._sum(snap.tvl, ts, dmax), snap._sum(snap.tvl, ts, dmax - dt.timedelta(days=30))
            f["tvl_change_30"] = t1 / t0 - 1 if t1 is not None and t0 not in (None, 0) else float("nan")
    s1, s0 = snap.stable.get(dmax), snap.stable.get(dmax - dt.timedelta(days=30))
    f["stable_supply_30"] = s1 / s0 - 1 if s1 is not None and s0 not in (None, 0) else float("nan")   # NaN => the month fails closed (handled by the caller)
    for k in FUNDAMENTAL: f[k + "_missing"] = 0.0 if math.isfinite(f[k]) else 1.0
    return f


# ---------------------------------------------------------------- dataset
def build_dataset(market, snap=None, btc="BTC", log=print):
    """One row per (formation month, candidate): labels, strata, verified features (or ineligible flag), assumed features."""
    bar = market.bar_seconds; rows = []; counts = {"candidates": 0, "verified_ineligible": 0, "no_label_window": 0}
    for t_dec in formation_times(market):
        cands = candidate_set(market, t_dec); counts["candidates"] += len(cands)
        if not cands: continue
        ib = bisect.bisect_right(market._ts[btc], t_dec - bar); btc_c = [b.c for b in market.bars[btc][:ib]]
        br = breadth_of(market, t_dec, cands)
        ldv = []
        for s in cands:
            i = bisect.bisect_right(market._ts[s], t_dec - bar); ldv.append(sum(b.c * b.v for b in market.bars[s][i - 90:i]) / 90)
        qs = quintiles(ldv)
        for s, q in zip(cands, qs):
            lab = labels(market, s, t_dec); vf = verified_features(market, s, t_dec, btc_c, br)
            if vf is None: counts["verified_ineligible"] += 1
            row = {"t": t_dec, "month": _month(t_dec - bar), "year": _month(t_dec - bar)[0], "symbol": s, "quintile": q, "verified": vf, **lab}
            if snap is not None: row["assumed"] = assumed_features(snap, s, t_dec)
            rows.append(row)
    log(f"dataset: {len(rows)} rows over {len(set(r['month'] for r in rows))} months; verified-ineligible {counts['verified_ineligible']}")
    return rows, counts


# ---------------------------------------------------------------- model
def fit_logistic(X, y, C, iters=50):
    """L2-regularised logistic regression (sklearn convention: minimise sum logloss + ||w||^2 / (2C); intercept unpenalised),
    Newton's method with a ridge safeguard. X standardised already."""
    n, d = X.shape; Xb = np.hstack([np.ones((n, 1)), X]); w = np.zeros(d + 1); lam = 1.0 / C
    reg = np.full(d + 1, lam); reg[0] = 0.0
    for _ in range(iters):
        z = Xb @ w; p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        g = Xb.T @ (p - y) + reg * w
        H = (Xb * (p * (1 - p))[:, None]).T @ Xb + np.diag(reg) + 1e-8 * np.eye(d + 1)
        step = np.linalg.solve(H, g); w = w - step
        if np.max(np.abs(step)) < 1e-8: break
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-np.clip(np.hstack([np.ones((len(X), 1)), X]) @ w, -30, 30)))


def logloss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9); return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


class Standardiser:
    """Training-only mean/std from OBSERVED values; NaN -> standardised 0 (assumed pipeline); std 0 -> column left at 0."""
    def fit(self, X):
        self.mu = np.nanmean(X, axis=0); self.sd = np.nanstd(X, axis=0)
        self.mu = np.where(np.isfinite(self.mu), self.mu, 0.0); self.sd = np.where(np.isfinite(self.sd) & (self.sd > 0), self.sd, 1.0)
        return self
    def transform(self, X):
        Z = (X - self.mu) / self.sd; return np.where(np.isfinite(Z), Z, 0.0)


# ---------------------------------------------------------------- statistics (FROZEN gate)
def strata_precision(rows, scores, label="runner_2x", top=TOP_SHARE, exclude_q=None, exclude_months=()):
    """Population precision@top within (month, quintile) strata on the FULL eligible population, base rate = positive share
    of the stratum; positive-count weighted average; also per-stratum contributions for the removal tests."""
    groups = {}
    for r, sc in zip(rows, scores):
        if exclude_q is not None and r["quintile"] == exclude_q: continue
        if r["month"] in exclude_months: continue
        groups.setdefault((r["month"], r["quintile"]), []).append((sc, 1.0 if r[label] else 0.0))
    wp = wb = wsum = 0.0; per_month = {}
    for (m, q), g in groups.items():
        n = len(g); pos = sum(y for _, y in g)
        if pos == 0: continue
        k = max(1, math.ceil(top * n)); topk = sorted(g, key=lambda x: -x[0])[:k]
        prec = sum(y for _, y in topk) / k; base = pos / n
        wp += pos * prec; wb += pos * base; wsum += pos
        pm = per_month.setdefault(m, {"excess": 0.0, "positives": 0.0}); pm["excess"] += pos * (prec - base); pm["positives"] += pos
    if wsum == 0: return {"precision": None, "base_rate": None, "lift": None, "positives": 0, "per_month": per_month}
    prec, base = wp / wsum, wb / wsum
    return {"precision": prec, "base_rate": base, "lift": prec / base if base > 0 else None, "positives": int(wsum), "per_month": per_month}


def enrichment(rows, scores, top):
    """Share of 3x / 5x runners in the top-`top` score bucket of each stratum vs their own full-population base rates."""
    out = {}
    for tier in ("runner_3x", "runner_5x"):
        r = strata_precision(rows, scores, label=tier, top=top); out[tier] = {k: r[k] for k in ("precision", "base_rate", "lift", "positives")}
    return out


def permutation_p(rows, scores, observed_lift, n=PERMUTATIONS, seed=7):
    """Within-stratum label permutations with the scores fixed: p = share of permutations with lift >= observed."""
    rng = np.random.default_rng(seed); groups = {}
    for idx, r in enumerate(rows): groups.setdefault((r["month"], r["quintile"]), []).append(idx)
    ys = np.array([1.0 if r["runner_2x"] else 0.0 for r in rows]); hits = 0
    for _ in range(n):
        yp = ys.copy()
        for g in groups.values():
            g = np.array(g); yp[g] = rng.permutation(ys[g])
        fake = [dict(r, runner_2x=bool(yp[i])) for i, r in enumerate(rows)]
        l = strata_precision(fake, scores)["lift"]
        if l is not None and observed_lift is not None and l >= observed_lift: hits += 1
    return (hits + 1) / (n + 1)


def run_pipeline(rows, feature_names, get_features, label="runner_2x", log=print, with_permutation=True):
    """Expanding-year walk-forward: for each test year fit on strictly earlier formation months, select C by in-fit log-loss,
    score EVERY eligible name of the test year. Returns the frozen statistics and outcome."""
    elig = [r for r in rows if get_features(r) is not None]
    years = {}; all_scores = []; all_rows = []; trials = 0; picks = {}
    for ty in TEST_YEARS:
        train = [r for r in elig if r["year"] < ty]; test = [r for r in elig if r["year"] == ty]
        if len(train) < 50 or not test: years[ty] = {"error": f"train {len(train)} / test {len(test)}"}; continue
        Xtr = np.array([[get_features(r)[k] for k in feature_names] for r in train], dtype=float); ytr = np.array([1.0 if r[label] else 0.0 for r in train])
        Xte = np.array([[get_features(r)[k] for k in feature_names] for r in test], dtype=float)
        sc = Standardiser().fit(Xtr); Ztr, Zte = sc.transform(Xtr), sc.transform(Xte)
        best = None
        for C in C_GRID:
            trials += 1; w = fit_logistic(Ztr, ytr, C); ll = logloss(predict(w, Ztr), ytr)
            if best is None or ll < best[0]: best = (ll, C, w)
        picks[ty] = {"C": best[1], "in_fit_logloss": best[0], "train_rows": len(train), "test_rows": len(test), "coef": dict(zip(["intercept"] + list(feature_names), [float(x) for x in best[2]]))}
        s = list(predict(best[2], Zte)); all_scores += s; all_rows += test
        yr = strata_precision(test, s, label=label); years[ty] = {k: yr[k] for k in ("precision", "base_rate", "lift", "positives")}
    pooled = strata_precision(all_rows, all_scores, label=label)
    contrib = sorted(pooled["per_month"].items(), key=lambda kv: -kv[1]["excess"])[:3]
    ex_liq = strata_precision(all_rows, all_scores, label=label, exclude_q=4)
    ex_months = strata_precision(all_rows, all_scores, label=label, exclude_months={m for m, _ in contrib})
    year_lifts = [y.get("lift") for y in years.values() if isinstance(y, dict) and y.get("lift") is not None]
    year_pos = [y.get("positives", 0) for y in years.values() if isinstance(y, dict) and "positives" in y]
    checks = {"pooled_lift>=2": (pooled["lift"] or 0) >= GATE["pooled_lift"],
              "years_lift>=1.5_in_3_of_4": sum(1 for l in year_lifts if l >= GATE["year_lift"]) >= GATE["years_needed"],
              "survives_without_top_liquidity_quintile": (ex_liq["lift"] or 0) >= GATE["pooled_lift"],
              "survives_without_top3_months": (ex_months["lift"] or 0) >= GATE["pooled_lift"]}
    enough = pooled["positives"] >= MIN_POSITIVES_TOTAL and len(year_pos) == len(TEST_YEARS) and all(p >= MIN_POSITIVES_YEAR for p in year_pos)
    out = {"label": label, "features": list(feature_names), "eligible_rows": len(elig), "trials": trials, "picks": picks, "years": years, "pooled": {k: pooled[k] for k in ("precision", "base_rate", "lift", "positives")},
           "top3_contributing_months": [f"{m[0]}-{m[1]:02d}" for m, _ in contrib], "without_top_liquidity_quintile": {k: ex_liq[k] for k in ("precision", "base_rate", "lift")},
           "without_top3_months": {k: ex_months[k] for k in ("precision", "base_rate", "lift")},
           "enrichment": {f"top{int(t*100)}%": enrichment(all_rows, all_scores, t) for t in (0.05, 0.10, 0.20)},
           "lift_top5%": strata_precision(all_rows, all_scores, label=label, top=0.05)["lift"], "lift_top20%": strata_precision(all_rows, all_scores, label=label, top=0.20)["lift"],
           "checks": checks, "minimum_evidence_ok": enough, "_rows": all_rows, "_scores": all_scores}
    if with_permutation and all_rows:
        out["permutation_p"] = permutation_p(all_rows, all_scores, pooled["lift"])
    if not enough: out["outcome"], out["reason"] = "inconclusive", f"positives {pooled['positives']} total / per year {year_pos} below minimum"
    elif all(checks.values()): out["outcome"], out["reason"] = "historical_survivor", None
    else: out["outcome"], out["reason"] = "historical_rejected", ", ".join(k for k, v in checks.items() if not v)
    return out


def negative_control(rows, feature_names, get_features, seed=11, log=print):
    """The same pipeline on runner_2x labels shuffled within (month, quintile) strata of the full population."""
    rng = np.random.default_rng(seed); groups = {}
    for idx, r in enumerate(rows): groups.setdefault((r["month"], r["quintile"]), []).append(idx)
    ys = np.array([1.0 if r["runner_2x"] else 0.0 for r in rows]); yp = ys.copy()
    for g in groups.values():
        g = np.array(g); yp[g] = rng.permutation(ys[g])
    fake = [dict(r, runner_2x=bool(yp[i])) for i, r in enumerate(rows)]
    res = run_pipeline(fake, feature_names, get_features, log=log, with_permutation=False)
    lift = res["pooled"]["lift"]
    return {"pooled_lift": lift, "years": res["years"], "ok": lift is not None and abs(lift - 1.0) <= CONTROL_TOL, "tolerance": CONTROL_TOL}


def diagnostic_model(rows, feature_names, get_features, log=print):
    """3x vs <1.5x contrast model, scored on the full population, graded on 2x population precision. DIAGNOSTIC ONLY."""
    def is_diag_train(r): return r["runner_3x"] or (r["max_close"] < 1.5 * r["entry_reference"])
    elig = [r for r in rows if get_features(r) is not None]; all_scores, all_rows = [], []
    for ty in TEST_YEARS:
        train = [r for r in elig if r["year"] < ty and is_diag_train(r)]; test = [r for r in elig if r["year"] == ty]
        if len(train) < 50 or not test: continue
        Xtr = np.array([[get_features(r)[k] for k in feature_names] for r in train]); ytr = np.array([1.0 if r["runner_3x"] else 0.0 for r in train])
        sc = Standardiser().fit(Xtr); w = fit_logistic(sc.transform(Xtr), ytr, 1.0)
        all_scores += list(predict(w, sc.transform(np.array([[get_features(r)[k] for k in feature_names] for r in test])))); all_rows += test
    p = strata_precision(all_rows, all_scores) if all_rows else {"lift": None, "precision": None, "base_rate": None}
    return {"note": "diagnostic only; never gates", "pooled_2x": {k: p[k] for k in ("precision", "base_rate", "lift")}}


# ---------------------------------------------------------------- the table
def run_table(market, snap=None, log=print):
    rows, counts = build_dataset(market, snap, log=log)
    table = {"frozen_rules": "PHASE4-ROUND3-PREREGISTRATION.md v3 (R-AE) + STAGE0-FEATURES.md v2 (R-AH)", "data_hash": market.fingerprint(), "universe_hash": market.universe_fingerprint(),
             "llama_snapshot_hash": snap.hash if snap else None, "counts": counts, "months": sorted({f"{m[0]}-{m[1]:02d}" for m in {r["month"] for r in rows}}),
             "label_counts": {k: sum(1 for r in rows if r[k]) for k in TIERS}, "rows": len(rows), "pipelines": {}}
    gv = lambda r: r["verified"]
    log("verified pipeline ..."); ver = run_pipeline(rows, VERIFIED, gv, log=log)
    ver["negative_control"] = negative_control(rows, VERIFIED, gv, log=log); ver["diagnostic_3x_vs_lt1.5x"] = diagnostic_model(rows, VERIFIED, gv, log=log)
    if not ver["negative_control"]["ok"]: ver["outcome"], ver["reason"] = "invalid", "negative control off base rate: pipeline leaks"
    table["pipelines"]["verified"] = {k: v for k, v in ver.items() if not k.startswith("_")}
    if snap is not None:
        bad_months = {r["month"] for r in rows if r.get("assumed") and not math.isfinite(r["assumed"]["stable_supply_30"])}
        arows = [r for r in rows if r["month"] not in bad_months]
        ga = lambda r: ({**r["verified"], **r["assumed"]} if r["verified"] is not None else None)
        log(f"assumed pipeline ... (months failed closed for missing stablecoin context: {len(bad_months)})")
        asm = run_pipeline(arows, VERIFIED + ASSUMED, ga, log=log)
        asm["negative_control"] = negative_control(arows, VERIFIED + ASSUMED, ga, log=log)
        asm["months_failed_closed"] = sorted(f"{m[0]}-{m[1]:02d}" for m in bad_months)
        asm["fundamentals_coverage"] = {k: sum(1 for r in arows if r["verified"] is not None and math.isfinite(r["assumed"][k])) for k in FUNDAMENTAL}
        asm["has_family_rows"] = sum(1 for r in arows if r["assumed"]["has_family"] == 1.0)
        if not asm["negative_control"]["ok"]: asm["outcome"], asm["reason"] = "invalid", "negative control off base rate"
        elif asm["outcome"] == "historical_survivor": asm["outcome"] = "historical_survivor (assumed availability)"
        asm["evidence_class"] = "assumed_availability"; asm["subordinate"] = True
        table["pipelines"]["assumed"] = {k: v for k, v in asm.items() if not k.startswith("_")}
    for p in table["pipelines"].values(): p["research_accepted"] = False; p["trade_approved"] = False
    return table


def render(table):
    f = lambda x: "—" if x is None else f"{x:.3f}"
    L = [f"# Phase 4 round 3 — runner-forensics table ({dt.date.today()}; FROZEN v3 + Stage 0 v2; screening only; nothing in research_runs)", "",
         f"data_hash `{table['data_hash']}` · universe_hash `{table['universe_hash']}` · llama snapshot `{table['llama_snapshot_hash']}` · rows {table['rows']} over {len(table['months'])} months · labels {table['label_counts']} · verified-ineligible {table['counts']['verified_ineligible']}", "",
         "| pipeline | eligible rows | trials | OOS positives | precision@10% | base rate | lift | ex top-liquidity | ex top-3 months | years lift | perm p | neg. control lift | outcome |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, p in table["pipelines"].items():
        yl = " / ".join(f"{y}:{f(v.get('lift'))}" for y, v in p["years"].items() if isinstance(v, dict))
        L.append(f"| {name} | {p['eligible_rows']} | {p['trials']} | {p['pooled']['positives']} | {f(p['pooled']['precision'])} | {f(p['pooled']['base_rate'])} | {f(p['pooled']['lift'])} | {f(p['without_top_liquidity_quintile']['lift'])} | {f(p['without_top3_months']['lift'])} | {yl} | {f(p.get('permutation_p'))} | {f(p['negative_control']['pooled_lift'])} | **{p['outcome']}**{(' — ' + p['reason']) if p.get('reason') else ''} |")
    L += ["", "## Enrichment (reported, never gated): 3x / 5x share in top score buckets vs own base rate", ""]
    for name, p in table["pipelines"].items():
        for b, e in p["enrichment"].items():
            L.append(f"- {name} {b}: 3x lift {f(e['runner_3x']['lift'])} (base {f(e['runner_3x']['base_rate'])}); 5x lift {f(e['runner_5x']['lift'])} (base {f(e['runner_5x']['base_rate'])})")
    L += ["", "## Checks, picks, diagnostics", ""]
    for name, p in table["pipelines"].items():
        picks = ", ".join(f"{y}: {v['C']}" for y, v in p["picks"].items())
        L.append(f"- **{name}**: checks {p['checks']}; minimum evidence {p['minimum_evidence_ok']}; C picks {{{picks}}}; top-3 months {p['top3_contributing_months']}; lift top5% {f(p['lift_top5%'])}, top20% {f(p['lift_top20%'])}")
        if "diagnostic_3x_vs_lt1.5x" in p: L.append(f"  - diagnostic 3x-vs-<1.5x model graded on 2x: {p['diagnostic_3x_vs_lt1.5x']['pooled_2x']}")
        if "fundamentals_coverage" in p: L.append(f"  - fundamentals coverage (finite values): {p['fundamentals_coverage']}; has_family rows {p['has_family_rows']}; months failed closed {p['months_failed_closed']}")
    return "\n".join(L)

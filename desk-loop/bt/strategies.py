"""Baseline strategies for the tournament. Each is a callable (view, portfolio) -> [Order]. They see only the
AsOfView, so none can read a bar that had not closed at decision time. They never size: every buy is one engine
slot (review R-G), so Phase 4 compares entry/exit logic under identical capital rules; sizing overlays
(inverse-vol, ATR risk, confidence, Kelly caps) are a separate later study."""
from .engine import Order


def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None


def buy_and_hold(symbols):
    """At inception fill up to max_positions names (engine ranks by (priority, symbol)); then hold."""
    done = set()
    def s(view, pf):
        out = []
        for sym in symbols:
            if sym not in done and sym in view.universe():
                done.add(sym); out.append(Order(sym, "buy", tag="bh"))
        return out
    return s


def cash():
    return lambda view, pf: []


def dca(symbols, every_days=30):
    """On each DCA date, move toward the equal-slot target with available cash: request a slot for every name not
    held (all-or-none at the engine). No nominal-dollar contributions — those drift against equity-scaled peers."""
    state = {"last": 0}
    def s(view, pf):
        if view.t - state["last"] < every_days * 86400:
            return []
        state["last"] = view.t
        return [Order(sym, "buy", tag="dca") for sym in symbols if sym in view.universe() and sym not in pf.positions]
    return s


def _scope(symbols, view, pf):
    """Names a strategy evaluates: its fixed list, or the view's universe (Phase 4 monthly membership) — plus every
    held name, so a position whose symbol dropped out of the universe still runs its exit rule (pre-registration §1)."""
    return sorted(set(symbols or view.universe()) | set(pf.positions))


def sma_trend(symbols=None, fast=50, slow=200):
    def s(view, pf):
        out = []
        for sym in _scope(symbols, view, pf):
            c = view.closes(sym, slow + 1)
            f, sl = _sma(c, fast), _sma(c, slow)
            if f is None or sl is None:
                continue
            long = c[-1] > sl and f > sl
            if long and sym not in pf.positions and sym in view.universe():
                out.append(Order(sym, "buy", tag="trend"))
            elif not long and sym in pf.positions:
                out.append(Order(sym, "sell", tag="trend"))
        return out
    return s


def breakout20(lookback=20, vol_mult=1.5, max_ext=0.15, stop_pct=0.12, btc="BTC"):
    """The house breakout rule, on completed bars: close > prior 20d high, volume >= 1.5x prior 20d avg,
    7d RS > BTC, extension <= 15%. Fixed % stop; exit otherwise on close below the 20d low."""
    def s(view, pf):
        out = []
        bc = view.closes(btc, 8)
        btc7 = bc[-1] / bc[-8] - 1 if len(bc) >= 8 else None
        for sym in _scope(None, view, pf):
            bars = view.bars(sym, lookback + 8)
            if len(bars) < lookback + 8 or btc7 is None:
                continue
            c, v = bars[-1].c, bars[-1].v
            win = bars[-lookback - 1:-1]
            hi, lo = max(b.c for b in win), min(b.l for b in win)
            avgv = sum(b.v for b in win) / len(win) or 1
            r7 = c / bars[-8].c - 1
            if sym in pf.positions:
                if c < lo:
                    out.append(Order(sym, "sell", tag="brk"))
                continue
            if c > hi and v >= vol_mult * avgv and r7 > btc7 and c / hi - 1 <= max_ext:
                out.append(Order(sym, "buy", stop=c * (1 - stop_pct), priority=v / avgv, tag="brk"))   # rank by volume expansion
        return out
    return s


def momentum_top(n, lookback=90, rebalance_days=30):
    state = {"last": 0}
    def s(view, pf):
        if view.t - state["last"] < rebalance_days * 86400:
            return []
        state["last"] = view.t
        scores = []
        for sym in view.universe():
            c = view.closes(sym, lookback + 1)
            if len(c) >= lookback + 1 and c[-lookback - 1] > 0:
                scores.append((c[-1] / c[-lookback - 1] - 1, sym))
        top = {sym for _, sym in sorted(scores, reverse=True)[:n]}
        out = [Order(sym, "sell", tag="mom") for sym in pf.positions if sym not in top]
        rank = {sym: sc for sc, sym in scores}
        out += [Order(sym, "buy", priority=rank[sym], tag="mom") for sym in top if sym not in pf.positions]
        return out
    return s


def mean_reversion(symbols=None, n=20, dip=0.10, stop_pct=0.15):
    """n is the moving-average lookback (bars), never a count of names (pre-registration §5)."""
    def s(view, pf):
        out = []
        for sym in _scope(symbols, view, pf):
            c = view.closes(sym, n + 1)
            m = _sma(c, n)
            if m is None:
                continue
            if sym in pf.positions:
                if c[-1] >= m:
                    out.append(Order(sym, "sell", tag="mr"))
            elif c[-1] <= m * (1 - dip) and sym in view.universe():
                out.append(Order(sym, "buy", stop=c[-1] * (1 - stop_pct), target=m, priority=m / c[-1] - 1, tag="mr"))   # deeper dip first
        return out
    return s


def breakout_legacy(lookback=20, vol_mult=1.5, max_ext=0.15, trail_major=0.12, trail_other=0.18, per_week=2, btc="BTC", majors=("BTC", "ETH", "SOL")):
    """The house breakout rule EXACTLY as desk-loop/backtest_breakout_full.py ran it (variant 'no take-profit: trail
    12/18 only, 2/wk'), re-expressed on the AsOfView: entry close > prior 20d close-high, volume >= 1.5x prior 20d avg,
    7d return > BTC's, <= 15% above the high; stop = max(prior 20d low, entry*(1-trail)) ratcheting on closing highs;
    at most `per_week` new entries per ISO week (UTC), first-come by date then symbol; one open trade per symbol. The
    weekly cap counts TAKEN trades (fills reported by the engine in pf.last_fills at the next decision), attributed to the week of the
    signal bar, exactly as the legacy script counted; a refused proposal does not consume an opportunity (R-O).
    No partial take-profit (the engine has no partial sells; the legacy half-off variant is therefore out of scope)."""
    import datetime as dt
    taken, pending = {}, []                  # taken[week] = fills credited to that week; pending = (symbol, week) proposed last bar
    def s(view, pf):
        wk = dt.datetime.fromtimestamp(view.t - 1, dt.timezone.utc).isocalendar()[:2]   # the completed bar's week
        filled = set(getattr(pf, "last_fills", ()))
        for sym, w in pending:                 # a proposal that filled at this bar's open is a taken trade of its signal week, even if stopped the same bar
            if sym in filled:
                taken[w] = taken.get(w, 0) + 1
        pending.clear()
        bc = view.closes(btc, 8)
        if len(bc) < 8:
            return []
        btc7 = bc[-1] / bc[-8] - 1
        out = []
        for sym in sorted(view.universe()):
            if sym in pf.positions or taken.get(wk, 0) + sum(1 for _, w in pending if w == wk) >= per_week:
                continue
            bars = view.bars(sym, lookback + 8)
            if len(bars) < lookback + 8:
                continue
            c, v = bars[-1].c, bars[-1].v
            win = bars[-lookback - 1:-1]
            hi, lo = max(b.c for b in win), min(b.l for b in win)
            avgv = sum(b.v for b in win) / len(win) or 1
            r7 = c / bars[-8].c - 1
            if c > hi and v >= vol_mult * avgv and r7 > btc7 and c / hi - 1 <= max_ext:
                out.append(Order(sym, "buy", stop=lo, trail=trail_major if sym in majors else trail_other, tag="legacy"))
                pending.append((sym, wk))
        return out
    return s


def momentum_floor(n, lookback=90, rebalance_days=30, breadth_floor=0.50, floor=True, sma_n=50, members_required=20):
    """Round 2 candidate B (PHASE4-ROUND2-PREREGISTRATION v2, FROZEN R-X). At each rebalance close: breadth = frozen
    top-20 members with close > own SMA50 / members. Fail closed to cash when the membership has fewer than
    `members_required` names or any member's completed bar is missing (counted in state['fail_closed']). Breadth below the
    floor => cash (sell all, no buys). Otherwise rank members by `lookback`-day return and hold the top n. `floor=False`
    is the paired no-floor twin: identical rule, identical parameters, the breadth branch skipped (its breadth is still
    computed and logged so the twin is exactly paired)."""
    state = {"last": 0, "fail_closed": 0, "cash_rebalances": 0, "rebalances": 0, "breadth": []}
    def s(view, pf):
        if view.t - state["last"] < rebalance_days * 86400:
            return []
        state["last"] = view.t; state["rebalances"] += 1
        members = view.universe_members()
        if members is None:
            members = view.universe()
        present = set(view.universe())
        sell_all = [Order(sym, "sell", tag="momf") for sym in pf.positions]
        if len(members) < members_required or any(m not in present for m in members):
            state["fail_closed"] += 1; state["breadth"].append((view.t, None))
            return sell_all
        above = 0
        for sym in members:
            c = view.closes(sym, sma_n)
            if len(c) >= sma_n and c[-1] > sum(c) / sma_n:
                above += 1
        breadth = above / len(members)
        state["breadth"].append((view.t, breadth))
        if floor and breadth < breadth_floor:
            state["cash_rebalances"] += 1
            return sell_all
        scores = []
        for sym in members:
            c = view.closes(sym, lookback + 1)
            if len(c) >= lookback + 1 and c[-lookback - 1] > 0:
                scores.append((c[-1] / c[-lookback - 1] - 1, sym))
        top = {sym for _, sym in sorted(scores, reverse=True)[:n]}
        out = [Order(sym, "sell", tag="momf") for sym in pf.positions if sym not in top]
        rank = {sym: sc for sc, sym in scores}
        out += [Order(sym, "buy", priority=rank[sym], tag="momf") for sym in top if sym not in pf.positions]
        return out
    s.state = state
    return s


def fear_greed_timing(threshold=25, hold_bars=90, btc="BTC", series="fear_greed"):
    """Round 2 candidate C, Option I (FROZEN R-X): when FLAT and the usable reading for the completed day D (the bar that
    closed at view.t) is <= threshold, buy BTC at the next open; hold exactly `hold_bars` bars; sell at the open after
    the last holding bar; no stop; readings while holding are ignored. The engine materialises at most one reading into
    the view: available_at <= view.t and dated within the series' declared freshness (verified: dated D; the assumed-lag
    series: D or D-1); anything older is never carried forward, so view.exog() is None on a missing day."""
    state = {"signals": 0, "ignored_while_holding": 0, "episodes": []}
    def s(view, pf):
        if btc in pf.positions:
            p = pf.positions[btc]
            if view.t >= p.entry_t + hold_bars * 86400:
                return [Order(btc, "sell", tag="fng")]
            r = view.exog(series)
            if r is not None and r["value"] <= threshold:
                state["ignored_while_holding"] += 1
            return []
        r = view.exog(series)
        if r is None or r["value"] > threshold or btc not in view.universe():
            return []
        state["signals"] += 1; state["episodes"].append((view.t, r["value"]))
        return [Order(btc, "buy", tag="fng")]
    s.state = state
    return s


def regime_gate(strategy):
    """Canonical Phase 3 entry rule (design §1/§8): new long entries only when the published label is risk_on. Sells
    always pass. A run without a regime series attached (view.regime() is None) is unfiltered and unchanged."""
    def s(view, pf):
        out = list(strategy(view, pf) or [])
        r = view.regime()
        if r is None or r[0] == "risk_on":
            return out
        return [o for o in out if o.side == "sell"]
    return s


REGISTRY = {
    "breakout_legacy": breakout_legacy,"buy_and_hold": buy_and_hold, "cash": cash, "dca": dca, "sma_trend": sma_trend, "breakout20": breakout20, "momentum_top": momentum_top, "mean_reversion": mean_reversion,
    "momentum_floor": momentum_floor, "fear_greed_timing": fear_greed_timing}

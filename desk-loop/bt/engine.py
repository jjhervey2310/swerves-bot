"""Event-driven daily engine (v3: slot allocator, review R-G).
SIZING lives here, not in strategies: every buy is ONE SLOT = current_equity * gross_cap / max_positions, all-or-none.
Strategies only say WHICH names (and a priority for ranking when signals exceed free slots); Order.usd is ignored.
Capital starvation is therefore a strategy property (how it ranks), never an allocator artefact.
Chronology per bar opening at t:  (1) fill yesterday's decisions at this OPEN — sells first, then buys as a batch
with a deterministic allocation (priority desc, symbol asc), all-or-none, never partial; (2) stops/targets on this
bar's range INCLUDING the entry bar (stop before target; gap through a level fills at the open); (3) mark equity
at the close, stamped t + bar; (4) decide with as_of(t + bar). `end_t` bounds information: a bar is processed only
if t + bar <= end_t, so a fit window can never see its test window's first bar. Every non-fill is an event."""
import dataclasses
from bt_costs import CostModel


@dataclasses.dataclass
class Order:
    symbol: str
    side: str            # 'buy' | 'sell' (sell = close the position)
    usd: float = 0.0     # IGNORED since v3 — sizing is the engine's slot allocator
    stop: float = None
    target: float = None
    priority: float = 0.0  # higher fills first when capital/slots are scarce; ties by symbol
    tag: str = ""
    trail: float = None  # trailing stop fraction off the highest CLOSE since entry (ratchets up only; legacy house rule)


@dataclasses.dataclass
class Position:
    symbol: str
    units: float
    entry_px: float
    entry_t: int
    stop: float = None
    target: float = None
    high: float = 0.0
    tag: str = ""
    trail: float = None
    hc: float = 0.0      # highest close since entry (entry bar close at fill), drives `trail`
    last_mark: float = 0.0   # last known COMPLETED close; used to mark a held name whose bar is missing today (R-V hardening)


@dataclasses.dataclass
class Trade:
    symbol: str
    entry_t: int
    exit_t: int
    entry_px: float
    exit_px: float
    units: float
    ret: float
    pnl: float
    reason: str
    tag: str = ""


class Portfolio:
    def __init__(self, cash):
        self.cash = cash
        self.positions = {}
        self.last_fills = []     # symbols whose BUY filled at the most recent open (reset every bar; strategies may read it)

    def equity(self, prices):
        # a held name with no bar today is marked at its last known completed close, never at entry price (R-V hardening)
        return self.cash + sum(p.units * prices.get(s, p.last_mark or p.entry_px) for s, p in self.positions.items())


def run(market, strategy, costs: CostModel, start_cash=10_000.0, start_t=None, end_t=None, max_positions=10, gross_cap=1.0, fixed_usd=None, regime=None, universe=None, liquidate_at_end=True):
    """fixed_usd: DIAGNOSTIC ONLY (sizing attribution, review R-I). Every fill is exactly fixed_usd regardless of
    equity — the legacy house convention. Never a research configuration; results so sized are not evidence."""
    bar = market.bar_seconds
    times = sorted({t for s in market.symbols() for t in market._ts[s]})
    if start_t is not None:
        times = [t for t in times if t >= start_t]
    if end_t is not None:
        times = [t for t in times if t + bar <= end_t]      # information boundary, not a label filter (R-F #1)
    pf, trades, equity, events, cash_curve = Portfolio(start_cash), [], [], [], []
    stale = 0                                   # held-position bar-days marked at the last known close because today's bar is missing
    pending = []
    side_cost = costs.per_side(taker=True)
    for t in times:
        # (1) sells first, then buys as a batch against post-sell cash and slots
        slot_usd = fixed_usd if fixed_usd else (equity[-1][1] if equity else start_cash) * gross_cap / max_positions   # sized off the last close mark
        pf.last_fills = []
        sells = [o for o in pending if o.side == "sell"]
        buys = sorted((o for o in pending if o.side == "buy"), key=lambda o: (-o.priority, o.symbol))
        for o in sells:
            b = market.bar_opening_at(o.symbol, t)
            if b is None:
                events.append((t, o.symbol, "no_fill", "no bar", o.tag)); continue
            if o.symbol in pf.positions:
                _close(pf, trades, o.symbol, b.o * (1 - side_cost), t, "signal")
        for o in buys:
            b = market.bar_opening_at(o.symbol, t)
            if b is None:
                events.append((t, o.symbol, "no_fill", "no bar", o.tag)); continue
            if o.symbol in pf.positions:
                events.append((t, o.symbol, "no_fill", "already held", o.tag)); continue
            if len(pf.positions) >= max_positions:
                events.append((t, o.symbol, "no_fill", "slots", o.tag)); continue
            if slot_usd <= 0 or slot_usd > pf.cash + 1e-9:
                events.append((t, o.symbol, "no_fill", f"cash {pf.cash:.2f} < slot {slot_usd:.2f}", o.tag)); continue
            px = b.o * (1 + side_cost)
            pf.cash -= slot_usd
            stop = o.stop
            if o.trail:
                stop = max(stop if stop is not None else 0.0, px * (1 - o.trail))   # structural stop, never wider than the trail
            pf.positions[o.symbol] = Position(o.symbol, slot_usd / px, px, t, stop, o.target, b.o, o.tag, o.trail, b.c, b.c)
            events.append((t, o.symbol, "fill", f"{slot_usd:.2f}", o.tag)); pf.last_fills.append(o.symbol)
        pending = []
        # (2) stops / targets on this bar's range, entry bar included (R-F #2)
        for s in list(pf.positions):
            p = pf.positions[s]
            b = market.bar_opening_at(s, t)
            if b is None:
                d = market.listings.get(s, (None, None))[1]
                if d is not None and t >= d:                 # delisted while held: out at the last available close (legacy did the same)
                    _close(pf, trades, s, market.bars[s][-1].c * (1 - side_cost), t, "delisted")
                continue
            if p.stop is not None and b.l <= p.stop:
                _close(pf, trades, s, min(p.stop, b.o) * (1 - side_cost), t, "stop"); continue
            if p.target is not None and b.h >= p.target:
                _close(pf, trades, s, max(p.target, b.o) * (1 - side_cost), t, "target"); continue
            p.high = max(p.high, b.h); p.last_mark = b.c
            if p.trail and b.c > p.hc:                     # ratchet on a new closing high only; the entry bar's close is the seed
                p.hc = b.c; p.stop = max(p.stop, b.c * (1 - p.trail))
        # (3) mark at the close, stamped with the close time (R-F #7)
        prices = {}
        for s in pf.positions:
            b = market.bar_opening_at(s, t)
            if b is not None:
                prices[s] = b.c
            else:
                stale += 1; events.append((t, s, "stale_mark", f"{pf.positions[s].last_mark:.6g}", pf.positions[s].tag))   # surfaced, never silent
        equity.append((t + bar, pf.equity(prices))); cash_curve.append((t + bar, pf.cash))
        # (4) decide on the completed bar
        pending = list(strategy(market.as_of(t + bar, regime, universe), pf) or [])
    if times and liquidate_at_end:
        t = times[-1]
        for s in list(pf.positions):
            b = market.bar_opening_at(s, t)
            _close(pf, trades, s, (b.c if b else pf.positions[s].entry_px) * (1 - side_cost), t, "eod")
        equity[-1] = (t + bar, pf.cash); cash_curve[-1] = (t + bar, pf.cash)
    return {"equity": equity, "trades": trades, "events": events, "final_cash": pf.cash, "start_cash": start_cash, "cash_curve": cash_curve,
            "sizing": {"rule": "fixed-usd DIAGNOSTIC", "fixed_usd": fixed_usd} if fixed_usd else {"rule": "slot", "gross_cap": gross_cap, "max_positions": max_positions},
            "regime_filtered": regime is not None, "stale_marks": stale,
            "no_fills": sum(1 for e in events if e[2] == "no_fill"),
            "no_fill_reasons": _reason_counts(events)}


def _reason_counts(events):
    """no_fill breakdown by class: cash / slots / no bar / already held (the cash reason carries amounts; collapse it)."""
    out = {}
    for e in events:
        if e[2] == "no_fill":
            k = "cash" if e[3].startswith("cash") else e[3]
            out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def _close(pf, trades, s, px, t, reason):
    p = pf.positions.pop(s)
    pnl = p.units * (px - p.entry_px)
    pf.cash += p.units * px
    trades.append(Trade(s, p.entry_t, t, p.entry_px, px, p.units, px / p.entry_px - 1, pnl, reason, p.tag))

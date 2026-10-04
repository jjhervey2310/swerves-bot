import bisect, dataclasses, hashlib, json
from market_time import DAY, LookAheadError


@dataclasses.dataclass(frozen=True)
class Bar:
    t: int   # open time, UTC epoch seconds
    o: float
    h: float
    l: float
    c: float
    v: float

    def __getitem__(self, k):
        return getattr(self, k)


class Market:
    """In-memory bars + listing windows. `listings[sym] = (listed_at, delisted_at|None)` in epoch seconds.
    Listings are REQUIRED for research runs (R-F #6); `infer_listings=True` derives them from first/last bar and
    is for synthetic tests only. Strategies never touch this object; the engine hands them an AsOfView."""

    def __init__(self, bars, listings=None, bar_seconds=DAY, infer_listings=False):
        self.bar_seconds = bar_seconds
        self.bars = {s: sorted(b, key=lambda x: x.t) for s, b in bars.items()}
        self._ts = {s: [b.t for b in bs] for s, bs in self.bars.items()}
        if listings is None:
            if not infer_listings:
                raise ValueError("listings are required (listed_at, delisted_at) — pass infer_listings=True only for synthetic tests")
            listings = {s: (b[0].t, b[-1].t + bar_seconds) for s, b in self.bars.items() if b}
        self.listings = listings
        self._fp = None

    def symbols(self):
        return sorted(self.bars)

    def completed_until(self, sym, t):
        """Index one past the last bar completed by t (bars[:i] are visible at t)."""
        return bisect.bisect_right(self._ts.get(sym, []), t - self.bar_seconds)

    def as_of(self, t, regime=None, universe=None):
        return AsOfView.build(self, int(t), regime, universe)

    def bar_opening_at(self, sym, t):
        """The engine's fill bar: the bar whose open time is exactly t, else None. Not exposed to strategies."""
        ts = self._ts.get(sym, [])
        i = bisect.bisect_left(ts, t)
        return self.bars[sym][i] if i < len(ts) and ts[i] == t else None

    def fingerprint(self):
        """Canonical hash of every OHLCV row plus listings (R-F #8)."""
        if self._fp is None:
            h = hashlib.sha256()
            for s in self.symbols():
                for b in self.bars[s]:
                    h.update(f"{s}|{b.t}|{b.o!r}|{b.h!r}|{b.l!r}|{b.c!r}|{b.v!r}\n".encode())
            h.update(json.dumps(sorted((s, a, d) for s, (a, d) in self.listings.items())).encode())
            self._fp = h.hexdigest()[:16]
        return self._fp

    def universe_fingerprint(self):
        return hashlib.sha256(json.dumps(sorted((s, a, d) for s, (a, d) in self.listings.items())).encode()).hexdigest()[:16]


class AsOfView:
    """Everything a strategy may see at decision time `t`: per-symbol bar lists cut at the last bar COMPLETED by t,
    and the universe listed at t with a bar completed in the immediately preceding interval. Holds no reference to
    the Market (R-F #5): the visible slices are materialised as tuples. `test_bt.StrategyHygiene` additionally
    greps tournament strategies for raw-market references, because Python cannot forbid a closure."""

    __slots__ = ("t", "_bars", "_universe", "_bar_seconds", "_regime")

    @classmethod
    def build(cls, market, t, regime=None, universe=None):
        v = cls.__new__(cls)
        v.t, v._bar_seconds = t, market.bar_seconds
        v._regime = regime.at(t) if regime is not None else None      # Phase 3: the published label at the last decision time <= t, materialised (no series reference)
        v._bars = {}
        uni = []
        for s, bs in market.bars.items():
            i = market.completed_until(s, t)
            if i:
                v._bars[s] = (bs, i)                     # visibility-capped reference: the full series with cut `i`; the interface only serves bs[:i]. Not adversarially sealed (Python cannot) — the StrategyHygiene test is the guard
            a, d = market.listings.get(s, (None, None))
            fresh = i and bs[i - 1].t + market.bar_seconds > t - market.bar_seconds   # completed in the last interval
            if a is not None and a <= t and (d is None or t < d) and fresh:
                uni.append(s)
        if universe is not None:                                       # Phase 4: frozen monthly membership (tournament.UniverseSchedule)
            allowed = universe.at(t)
            uni = [s for s in uni if s in allowed]
        v._universe = tuple(sorted(uni))
        return v

    def bars(self, sym, n=None):
        bs, i = self._bars.get(sym, ((), 0))
        return list(bs[max(0, i - n) if n else 0:i])

    def closes(self, sym, n=None):
        return [b.c for b in self.bars(sym, n)]

    def universe(self):
        return list(self._universe)

    def regime(self):
        """Phase 3 label as (state, since_t, votes, vetoes), or None when the run has no regime series attached."""
        return self._regime

    def bar_at(self, sym, t):
        if t + self._bar_seconds > self.t:
            raise LookAheadError(f"bar {sym}@{t} not complete at {self.t}")
        for b in self.bars(sym):
            if b.t == t:
                return b
        return None


def market_from_rows(rows, bar_seconds=DAY, listings=None, *, infer_listings=False):
    """rows: iterable of dicts with symbol, bar_time (ISO or epoch s), open, high, low, close, volume.
    Listings are required; a research loader must never infer a universe from the bars (survivorship). Synthetic
    tests opt in with infer_listings=True."""
    import datetime as dt
    out = {}
    for r in rows:
        t = r["bar_time"]
        if isinstance(t, str):
            t = int(dt.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp())
        out.setdefault(r["symbol"], []).append(Bar(int(t), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"] or 0)))
    return Market(out, listings, bar_seconds, infer_listings=infer_listings)

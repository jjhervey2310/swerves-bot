"""Load bars from Supabase md_candles (paged, service key from env) or from a JSON export. Snapshot the result
to disk so a run's data_hash is reproducible even after the forward fill adds bars."""
import json, os
from common import sb_get
from .data import market_from_rows, DAY


def load_md_candles(symbols=None, venue="coinbase", interval_minutes=1440, start=None, page=1000, counts=None, end=None):
    # page must not exceed PostgREST db-max-rows (1000): a larger limit is silently capped and the loop would stop early
    """One request per symbol, ordered by bar_time: an index-range scan with no sort. (OFFSET paging over the whole
    table re-sorted 500k rows per page and spilled ~120 GB of temp files before failing with HTTP 500.)"""
    if not symbols:
        symbols = sorted({r["symbol"] for r in sb_get("universe_history", f"venue=eq.{venue}&select=symbol")})
    rows = []
    for sym in symbols:
        base = f"venue=eq.{venue}&interval_minutes=eq.{interval_minutes}&symbol=eq.{sym}&select=symbol,bar_time,open,high,low,close,volume&order=bar_time"
        if start:
            base += f"&bar_time=gte.{start}"
        if end:
            base += f"&bar_time=lte.{end}"          # reproduce a frozen snapshot after the forward fill has added bars (round 2: end=2026-10-01T23:59:59Z)
        off, n = 0, 0
        while True:
            chunk = sb_get("md_candles", f"{base}&limit={page}&offset={off}")
            rows += chunk; n += len(chunk)
            if len(chunk) < page:          # a full page means there may be more: keep going (R-M, silent PostgREST cap)
                break
            off += page
        if counts is not None:
            counts[sym] = n
    return rows


def load_universe(venue="coinbase"):
    """listed/delisted proxies from universe_history: first_bar (proxy for listing) and delisted_at (observed)."""
    import datetime as dt
    out = {}
    for r in sb_get("universe_history", f"venue=eq.{venue}&select=symbol,first_bar,delisted_at,first_seen"):
        a = r.get("first_bar") or r.get("first_seen")
        a_t = int(dt.datetime.fromisoformat(str(a).replace("Z", "+00:00")).timestamp()) if a else 0
        d = r.get("delisted_at")
        d_t = int(dt.datetime.fromisoformat(f"{d}T00:00:00+00:00").timestamp()) if d else None
        out[r["symbol"]] = (a_t, d_t)
    return out


def snapshot(rows, listings, path):
    with open(path, "w") as f:
        json.dump({"rows": rows, "listings": listings}, f)


def load_snapshot(path, bar_seconds=DAY):
    with open(path) as f:
        j = json.load(f)
    if not j.get("listings"):
        raise ValueError(f"{path}: snapshot has no listings (universe_history) — refusing to infer a universe from bars")
    listings = {k: tuple(v) for k, v in j["listings"].items()}
    return market_from_rows(j["rows"], bar_seconds, listings)


def load_sentiment(page=1000):
    """market_sentiment_daily with the point-in-time columns (round 2, R-W #3b). Publishable key + SELECT policy."""
    rows, off = [], 0
    while True:
        chunk = sb_get("market_sentiment_daily", f"select=snapshot_date,fear_greed,classification,source,observed_at,available_at&order=snapshot_date&limit={page}&offset={off}")
        rows += chunk
        if len(chunk) < page:
            return rows
        off += page


def snapshot_sentiment(rows, path):
    with open(path, "w") as f:
        json.dump({"sentiment": rows}, f)


def load_sentiment_snapshot(path):
    with open(path) as f:
        j = json.load(f)
    if "sentiment" not in j:
        raise ValueError(f"{path}: not a sentiment snapshot")
    return j["sentiment"]

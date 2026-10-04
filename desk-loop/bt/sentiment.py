"""Point-in-time exogenous daily readings (Phase 4 round 2, Fear & Greed; R-W #3b). A reading is a row
(observed_for_date, value, source, available_at) and a decision at time t may use it ONLY if available_at <= t.
Readings without a verified available_at are unusable. Missing days stay missing: nothing here forward-fills.
The strategy never sees this object; the engine materialises the one usable reading into the AsOfView."""
import bisect, datetime as dt, hashlib, json

DAY = 86400
ASSUMED_LAG_LABEL = "assumed_availability"


def _date(x):
    return x if isinstance(x, dt.date) else dt.date.fromisoformat(str(x)[:10])


def _ts(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    return int(dt.datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp())


def day_start(d):
    """UTC midnight that opens calendar day d, as epoch seconds."""
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


class PointInTimeSeries:
    """Readings sorted by available_at; at(t) returns the latest reading with available_at <= t (or None).
    `evidence_class` is 'verified' when every usable reading carries a collector timestamp, else the declared
    assumption label (round-2 §C option ii)."""

    def __init__(self, readings, name="fear_greed", evidence_class="verified", max_age_days=0):
        rs = [r for r in readings if r.get("available_at") is not None]
        rs.sort(key=lambda r: (r["available_at"], r["observed_for_date"]))
        self.name, self.evidence_class, self.max_age_days = name, evidence_class, max_age_days
        self._avail = [r["available_at"] for r in rs]
        self._rows = rs
        self.unusable = sum(1 for r in readings if r.get("available_at") is None)
        self.by_date = {r["observed_for_date"]: r for r in rs}

    def at(self, t):
        """The reading a decision at close t may use: the latest with available_at <= t, and only if it is dated within
        `max_age_days` of the day that completed at t (0 = must be dated that day; the declared lag otherwise). Older
        readings are stale, never carried forward: missing stays missing."""
        i = bisect.bisect_right(self._avail, t) - 1
        if i < 0:
            return None
        r = self._rows[i]
        completed = dt.datetime.fromtimestamp(t - DAY, dt.timezone.utc).date()
        return r if (completed - r["observed_for_date"]).days <= self.max_age_days else None

    def usable_for_day(self, day, t):
        """The reading observed for calendar `day` if it is usable at decision time t, else None."""
        r = self.by_date.get(day)
        return r if r is not None and r["available_at"] <= t else None

    def coverage(self, start_t, end_t, max_gap_days=30, min_share=0.80):
        """Round-2 §C coverage rule over decision closes in [start_t, end_t]: share of days whose reading was usable at
        that day's decision close, and the longest contiguous run of unusable days."""
        days = []
        t = start_t - start_t % DAY
        while t <= end_t:
            days.append(self.at(t) is not None)                                   # exactly what the strategy would see at that close
            t += DAY
        n = len(days); usable = sum(days)
        longest = cur = 0
        for ok in days:
            cur = 0 if ok else cur + 1; longest = max(longest, cur)
        share = usable / n if n else 0.0
        return {"days": n, "usable": usable, "share": share, "longest_gap_days": longest, "evidence_class": self.evidence_class,
                "unusable_rows": self.unusable, "inconclusive": share < min_share or longest > max_gap_days,
                "rule": f"inconclusive if share < {min_share} or any contiguous gap > {max_gap_days} days"}

    def fingerprint(self):
        h = hashlib.sha256(json.dumps([(str(r["observed_for_date"]), r["value"], r["available_at"], r.get("source")) for r in self._rows]).encode())
        return h.hexdigest()[:16]

    def manifest(self):
        return {"name": self.name, "evidence_class": self.evidence_class, "max_age_days": self.max_age_days, "rows_usable": len(self._rows), "rows_unusable": self.unusable,
                "first": str(self._rows[0]["observed_for_date"]) if self._rows else None, "last": str(self._rows[-1]["observed_for_date"]) if self._rows else None,
                "hash": self.fingerprint()}


def from_rows(rows, name="fear_greed"):
    """market_sentiment_daily rows (snapshot_date, fear_greed, source, available_at). Verified evidence class: only rows
    with a collector-stamped available_at are usable; backfilled rows (available_at NULL) are counted as unusable."""
    out = []
    for r in rows:
        v = r.get("fear_greed", r.get("value"))
        if v is None:
            continue
        out.append({"observed_for_date": _date(r.get("snapshot_date", r.get("observed_for_date"))), "value": int(v), "source": r.get("source"), "available_at": _ts(r.get("available_at"))})
    return PointInTimeSeries(out, name, "verified")


def assumed_availability(rows, name="fear_greed", lag_days=1):
    """Round-2 §C option (ii), accepted R-X: a backfilled reading dated D is treated as available at the decision close
    of D + lag_days (D+1 close = D+2 00:00 UTC), ~47 h beyond the observed live pattern. Rows that already carry a
    verified available_at keep it. Evidence class is the declared assumption, never 'verified'."""
    out = []
    for r in rows:
        v = r.get("fear_greed", r.get("value"))
        if v is None:
            continue
        d = _date(r.get("snapshot_date", r.get("observed_for_date")))
        a = _ts(r.get("available_at"))
        if a is None:
            a = day_start(d) + (lag_days + 1) * DAY
        out.append({"observed_for_date": d, "value": int(v), "source": r.get("source"), "available_at": a, "assumed": r.get("available_at") is None})
    return PointInTimeSeries(out, name, ASSUMED_LAG_LABEL, max_age_days=lag_days)

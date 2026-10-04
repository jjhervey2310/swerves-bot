#!/usr/bin/env python3
"""Phase 4 ROUND 2 runner (bt/round2.py, FROZEN R-X). Runs once on the frozen candle snapshot plus a sentiment snapshot and
writes <out>.json / <out>.md. Never writes research_runs. Export (publishable key, see HANDOFF): --export-sentiment PATH.
  python3 bt_round2.py --snapshot state/md_daily_2026-10-02.json --sentiment state/fng_2026-10-03.json --expect-data-hash 8df7990c93dcc632 --out ../docs/desk/PHASE4-ROUND2-TABLE-2026-10-03"""
import argparse, json, sys
from bt import load, round2

p = argparse.ArgumentParser()
p.add_argument("--snapshot")
p.add_argument("--sentiment", help="sentiment snapshot JSON from --export-sentiment")
p.add_argument("--export-sentiment", help="pull market_sentiment_daily (point-in-time columns) to this path and exit")
p.add_argument("--export-candles", help="pull md_candles + universe_history to this path and exit (same loader as bt_run --export)")
p.add_argument("--export-end", default=None, help="bar_time upper bound for --export-candles, e.g. 2026-10-01T23:59:59Z, to reproduce the frozen data_hash")
p.add_argument("--out")
p.add_argument("--only", default=None)
p.add_argument("--expect-data-hash", default=None)
p.add_argument("--fit-days", type=int, default=round2.FIT_DAYS)
p.add_argument("--test-days", type=int, default=round2.TEST_DAYS)
p.add_argument("--no-regime", action="store_true")
a = p.parse_args()
if a.export_candles:
    counts = {}
    rows = load.load_md_candles(end=a.export_end, counts=counts); load.snapshot(rows, load.load_universe(), a.export_candles)
    print("candle rows", len(rows), "symbols", len(counts), "->", a.export_candles); sys.exit(0)
if a.export_sentiment:
    rows = load.load_sentiment(); load.snapshot_sentiment(rows, a.export_sentiment); print("sentiment rows", len(rows), "->", a.export_sentiment); sys.exit(0)
if not (a.snapshot and a.sentiment and a.out):
    sys.exit("--snapshot, --sentiment and --out are required")
m = load.load_snapshot(a.snapshot)
if a.expect_data_hash and m.fingerprint() != a.expect_data_hash:
    sys.exit(f"refused: data_hash {m.fingerprint()} != {a.expect_data_hash}")
rows = load.load_sentiment_snapshot(a.sentiment)
if (a.fit_days, a.test_days) != (round2.FIT_DAYS, round2.TEST_DAYS):
    print("WARNING: non-pre-registered windows — not the table")
table = round2.run_table(m, rows, a.only.split(",") if a.only else None, a.fit_days, a.test_days, with_regime=not a.no_regime)
with open(a.out + ".json", "w") as f:
    json.dump(table, f, indent=1, default=str)
md = round2.render(table)
with open(a.out + ".md", "w") as f:
    f.write(md + "\n")
print(md); print("nothing stored to research_runs (independent review first)")

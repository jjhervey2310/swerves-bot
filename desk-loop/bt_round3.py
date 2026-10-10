#!/usr/bin/env python3
"""Round 3 runner (bt/round3.py, FROZEN R-AE + R-AH). One run on the frozen candle snapshot and the DeFiLlama backfill snapshot;
writes <out>.json / <out>.md. Never writes research_runs; no store option exists.
  python3 bt_round3.py --snapshot state/md_daily_2026-10-02.json --llama state/llama_2026-10-10.json --expect-data-hash 8df7990c93dcc632 --out ../docs/desk/PHASE4-ROUND3-TABLE-2026-10-10"""
import argparse, json, sys
from bt import load, round3

p = argparse.ArgumentParser(); p.add_argument("--snapshot", required=True); p.add_argument("--llama", default=None); p.add_argument("--out", required=True); p.add_argument("--expect-data-hash", default=None)
a = p.parse_args()
m = load.load_snapshot(a.snapshot)
if a.expect_data_hash and m.fingerprint() != a.expect_data_hash: sys.exit(f"refused: data_hash {m.fingerprint()} != {a.expect_data_hash}")
snap = round3.LlamaSnapshot(json.load(open(a.llama))) if a.llama else None
table = round3.run_table(m, snap)
json.dump(table, open(a.out + ".json", "w"), indent=1, default=str)
md = round3.render(table); open(a.out + ".md", "w").write(md + "\n"); print(md); print("nothing stored to research_runs (independent review first)")

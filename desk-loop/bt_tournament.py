#!/usr/bin/env python3
"""Phase 4 tournament runner. Runs the FROZEN table (bt/tournament.py) on a frozen snapshot and writes JSON + a Markdown
summary. Never writes research_runs. Usage: python3 bt_tournament.py --snapshot state/md_daily_2026-10-02.json --out ../docs/desk/PHASE4-TABLE-2026-10-03"""
import argparse, json, datetime as dt
from bt import load, tournament

p = argparse.ArgumentParser()
p.add_argument("--snapshot", required=True)
p.add_argument("--out", required=True, help="path prefix; writes <out>.json and <out>.md")
p.add_argument("--only", default=None, help="comma list of candidate names (default: the whole frozen table)")
a = p.parse_args()
m = load.load_snapshot(a.snapshot)
table = tournament.run_table(m, a.only.split(",") if a.only else None)
with open(a.out + ".json", "w") as f:
    json.dump(table, f, indent=1, default=str)
L = [f"# Phase 4 tournament table — {dt.date.today()} (FROZEN rules v2, R-S FINAL; nothing in research_runs)", "",
     f"data_hash `{table['data_hash']}` · universe_hash `{table['universe_hash']}` · membership_hash `{table['universe_schedule']['membership_hash']}` · monthly rankings {table['universe_schedule']['rankings']}", "",
     "| candidate | role | trials | OOS chained | OOS continuous | cont. ×1.25 | maxDD cont. | trades | PF | thirds | scale | delist | boundary | verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
pct = lambda x: "—" if x is None else f"{x*100:+.1f}%"
for n, r in table["candidates"].items():
    if "oos_continuous" not in r:
        L.append(f"| {n} | {r['role']} | {r.get('trials')} | — | — | — | — | — | — | — | — | — | — | {r['verdict']} |"); continue
    c, s_, b = r["oos_continuous"], r["oos_continuous_fee_stress"], r["advancement"]
    L.append(f"| {n} | {r['role']} | {r['trials']} | {pct(r['oos_chained'].get('total_return'))} | {pct(c.get('total_return'))} | {pct(s_.get('total_return'))} | {pct(c.get('max_drawdown'))} | {c.get('trades')} | {c.get('profit_factor') if c.get('profit_factor') is None else round(c['profit_factor'],2)} | {'✓' if b['thirds_2_of_3'] else '✗'} | {'✓' if b['scale_invariant'] else '✗'} | {'✓' if b['delisting_canonical'] else '✗'}{' (trig)' if r['delisting']['triggered'] else ''} | {'✓' if b['boundary_dependency_ok'] else '✗'} | {r['verdict']} |")
L += ["", "## Advancement booleans", ""]
for n, r in table["candidates"].items():
    if "advancement" in r:
        L.append(f"- **{n}**: " + ", ".join(f"{k}={'T' if v else 'F'}" for k, v in r["advancement"].items()))
L += ["", "## Per regime state (filter OFF, labels descriptive)", ""]
for n, r in table["candidates"].items():
    if r.get("per_regime_state"):
        L.append(f"- **{n}**: " + "; ".join(f"{k}: {v['trades']} trades, P&L {v['pnl']:+.0f}" for k, v in r["per_regime_state"].items()))
L += ["", "## Sensitivities (continuous OOS)", ""]
for n, r in table["candidates"].items():
    for k, v in (r.get("sensitivity") or {}).items():
        L.append(f"- {n} / {k}: return {pct(v.get('total_return'))}, maxDD {pct(v.get('max_drawdown'))}, trades {v.get('trades')}, PF {v.get('profit_factor')}")
with open(a.out + ".md", "w") as f:
    f.write("\n".join(L) + "\n")
print("\n".join(L))

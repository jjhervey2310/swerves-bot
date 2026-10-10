#!/usr/bin/env python3
"""Round 3 Stage 0 (FROZEN R-AH): DeFiLlama backfill for the frozen family slug sets in PHASE4-ROUND3-STAGE0-AUDIT.json.
Writes ONE snapshot file (daily fees, daily revenue, TVL per slug; the global stablecoin series) with `available_at` null on
every record and a content hash. Nothing is written to Supabase (Free-plan quota; a snapshot file is the frozen record,
as for candles). Usage: python3 bt_round3_backfill.py --audit ../docs/desk/PHASE4-ROUND3-STAGE0-AUDIT.json --out state/llama_2026-10-10.json"""
import argparse, json, hashlib, time, datetime as dt, urllib.request

p = argparse.ArgumentParser(); p.add_argument("--audit", required=True); p.add_argument("--out", required=True); a = p.parse_args()
audit = json.load(open(a.audit))["audit"]
usable = {s: v for s, v in audit.items() if v.get("family") and v.get("earliest_listedAt")}
tvl_slugs = sorted({x for v in usable.values() for x in v["family"]}); fee_slugs = sorted({x for v in usable.values() for x in v["fees_slugs"]})


def get(url, timeout=180):
    for k in range(3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            err = e; time.sleep(2 + 3 * k)
    print("FAILED", url, err); return None


out = {"generated_at": dt.datetime.utcnow().isoformat() + "Z", "rule": "FROZEN R-AH: family slug sets from the Stage 0 audit; every record available_at null (publication time unknown); usable only under the declared D+7 lag and >= family listedAt",
       "families": {s: {"slugs": v["family"], "fees_slugs": v["fees_slugs"], "earliest_listedAt": v["earliest_listedAt"]} for s, v in usable.items()},
       "tvl": {}, "fees": {}, "revenue": {}, "stablecoins": None, "listedAt": {}}
t0 = time.time()
for i, slug in enumerate(tvl_slugs):
    j = get(f"https://api.llama.fi/protocol/{slug}")
    if j is None: continue
    out["tvl"][slug] = [[int(x["date"]), float(x.get("totalLiquidityUSD") or 0)] for x in (j.get("tvl") or [])]
    out["listedAt"][slug] = j.get("listedAt")
    if i % 25 == 0: print(f"tvl {i}/{len(tvl_slugs)} {slug} {round(time.time()-t0)}s", flush=True)
for i, slug in enumerate(fee_slugs):
    for kind, key in (("dailyFees", "fees"), ("dailyRevenue", "revenue")):
        j = get(f"https://api.llama.fi/summary/fees/{slug}?dataType={kind}")
        if j is None: continue
        out[key][slug] = [[int(x[0]), float(x[1] or 0)] for x in (j.get("totalDataChart") or [])]
    if i % 25 == 0: print(f"fees {i}/{len(fee_slugs)} {slug} {round(time.time()-t0)}s", flush=True)
st = get("https://stablecoins.llama.fi/stablecoincharts/all")
out["stablecoins"] = [[int(x["date"]), float((x.get("totalCirculatingUSD") or {}).get("peggedUSD") or 0)] for x in (st or [])]
blob = json.dumps({k: out[k] for k in ("tvl", "fees", "revenue", "stablecoins", "listedAt", "families")}, sort_keys=True).encode()
out["hash"] = hashlib.sha256(blob).hexdigest()[:16]
json.dump(out, open(a.out, "w"))
print("done", a.out, "hash", out["hash"], "tvl", len(out["tvl"]), "fees", len(out["fees"]), "revenue", len(out["revenue"]), "stablecoin points", len(out["stablecoins"]), f"{round(time.time()-t0)}s")

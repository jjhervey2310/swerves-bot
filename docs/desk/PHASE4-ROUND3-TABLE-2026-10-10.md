# Phase 4 round 3 — runner-forensics table (2026-10-10; FROZEN v3 + Stage 0 v2; screening only; nothing in research_runs)

data_hash `8df7990c93dcc632` · universe_hash `64e00348d99bb713` · llama snapshot `e1a657594990b69e` · rows 5484 over 57 months · labels {'runner_2x': 993, 'runner_3x': 355, 'runner_5x': 107} · verified-ineligible 1

| pipeline | eligible rows | trials | OOS positives | precision@10% | base rate | lift | ex top-liquidity | ex top-3 months | years lift | perm p | neg. control lift | outcome |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| verified | 5483 | 8 | 909 | 0.481 | 0.456 | 1.056 | 1.085 | 1.008 | 2022:0.604 / 2023:1.055 / 2024:1.082 / 2025:1.099 | 0.160 | 0.984 | **historical_rejected** — pooled_lift>=2, years_lift>=1.5_in_3_of_4, survives_without_top_liquidity_quintile, survives_without_top3_months |
| assumed | 5483 | 8 | 909 | 0.500 | 0.456 | 1.097 | 1.095 | 1.044 | 2022:1.288 / 2023:0.983 / 2024:1.209 / 2025:1.029 | 0.043 | 1.041 | **historical_rejected** — pooled_lift>=2, years_lift>=1.5_in_3_of_4, survives_without_top_liquidity_quintile, survives_without_top3_months |

## Enrichment (reported, never gated): 3x / 5x share in top score buckets vs own base rate

- verified top5%: 3x lift 1.061 (base 0.242); 5x lift 1.438 (base 0.122)
- verified top10%: 3x lift 0.878 (base 0.242); 5x lift 1.163 (base 0.122)
- verified top20%: 3x lift 0.971 (base 0.242); 5x lift 1.055 (base 0.122)
- assumed top5%: 3x lift 1.148 (base 0.242); 5x lift 1.776 (base 0.122)
- assumed top10%: 3x lift 1.044 (base 0.242); 5x lift 1.311 (base 0.122)
- assumed top20%: 3x lift 0.849 (base 0.242); 5x lift 1.084 (base 0.122)

## Checks, picks, diagnostics

- **verified**: checks {'pooled_lift>=2': False, 'years_lift>=1.5_in_3_of_4': False, 'survives_without_top_liquidity_quintile': False, 'survives_without_top3_months': False}; minimum evidence True; C picks {2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0}; top-3 months ['2023-11', '2024-09', '2024-07']; lift top5% 1.063, top20% 1.063
  - diagnostic 3x-vs-<1.5x model graded on 2x: {'precision': 0.4802896956362302, 'base_rate': 0.45599021050979915, 'lift': 1.0532894886038542}
- **assumed**: checks {'pooled_lift>=2': False, 'years_lift>=1.5_in_3_of_4': False, 'survives_without_top_liquidity_quintile': False, 'survives_without_top3_months': False}; minimum evidence True; C picks {2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.0}; top-3 months ['2024-09', '2024-07', '2023-12']; lift top5% 1.124, top20% 1.059
  - fundamentals coverage (finite values): {'fees_growth_30': 401, 'rev_growth_30': 303, 'rev_yield': 0, 'tvl_change_30': 514}; has_family rows 1112; months failed closed []

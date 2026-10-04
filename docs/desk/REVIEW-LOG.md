# Desk review log

Every external review (ChatGPT, Codex, a human) gets answered here item by item: fixed, deferred with a reason, or
rejected with a reason. Disagreements that are empirical are settled by a backtest, named here, never by argument.
Newest review first.

---

## R-2026-10-02-A — ChatGPT review of PR #42 (Phase 0) and the PR #41 architecture

Reviewed heads: PR #42 `508a2a9`, PR #41 `4d09cce`. Response commit: see PR #42 history after this file lands.

### Code findings

| # | Severity (theirs) | Claim | Verdict | Action |
|---|---|---|---|---|
| 1 | BLOCKER (for any agent→live link) | `fund/buy` treats a shared header secret as authority to buy; no human identity bound to the order. | **Correct. Accepted as a design constraint, not a Phase 0 regression.** The route is a human tap endpoint and was the same before Phase 0; Phase 0's brief was "no secrets in query strings, server-side sizing", both done. | Recorded in §12b/§12 of the architecture (human approval binds proposal revision, venue, pair, side, cap, expiry; one-use; verified session). **No agent is ever given `ADMIN_SECRET`, exchange keys, or a service-role key** — written into CLAUDE.md. Phase 9 replaces this route; until then it stays a human-only tap. |
| 2 | HIGH | Concurrent requests can both pass the cash/holdings check and both place orders; no idempotency before the broker call. | **Correct.** | Fixed the cheap, honest part now: the tab sends one UUID per tap (`requestId`), the route passes it to Robinhood as `client_order_id` (broker-side idempotency — a retry cannot become a second fill), and a per-symbol in-flight guard serialises double-taps on the same instance. **Limit stated in code:** the guard is per serverless instance; a durable reservation row + reconciliation of unknown/timeout results is Phase 9 work and is listed there. Test: `clampOrderUsd` unchanged; the UUID pass-through is covered by the Robinhood adapter signature; a fake-broker concurrency test is scheduled with the Phase 9 reservation table (no point testing a guard we know is instance-local). |
| 3 | HIGH | Mixed clocks: breakout on completed closes, RS on CoinGecko's rolling intraday 7d. | **Correct — and it was on my own Phase 0 list (bug #4) and I had not fixed it.** | Fixed. `lib/desk/relative-strength.ts::rsCompletedPct` computes both 7-day returns from `cg_history` completed closes joined by timestamp; the timing route uses it for the signal *and* the tape input, and labels `rsSource`. CoinGecko rolling 7d remains only as a labelled fallback when no stored history exists. Test: `tests/relative-strength.test.ts` — adding today's partial point with a huge move does not change the result. |
| 4 | HIGH | `backtest.py` BTC end point timestamp-aligned but the 7-day start is still `bi - 7`; missing days shorten the window; no history → 0. | **Correct.** | Fixed. `market_time.ret_over()` finds both ends by timestamp (±half a bar for CoinGecko jitter) and returns `None` on any gap; `backtest.py` and `breakout_scan.py` treat `None` as "no signal on this bar" / "name unseen today", never as 0. Tests: `test_market_time.py::ReturnOver` (calendar days, missing start day, jitter). |
| 5 | HIGH | Legacy survivor-biased results are not approval evidence; first/last candles don't establish listing dates. | **Correct; already the architecture's position (§3 `universe_history`, §11).** | The `ASSUMPTIONS` stamp on every legacy result now says `universe=today's universe.json (survivorship-biased) — DIAGNOSTIC ONLY, not approval evidence`, and it is written **before** the first print so no copy of the output lacks it. `backtest_audit.py` (delisted pairs included) is the only legacy script that can feed evidence, and only after Phase 2 reruns it under the framework. |
| 6 | MEDIUM | `denverWeekStartIso` uses today's offset for Monday; wrong on a DST-transition Sunday. | **Correct.** | Fixed. Monday is found by calendar arithmetic, then its midnight is resolved with the offset sampled at *Monday's own noon* (`zonedMidnightUtc`). Tests added for Sun 2026-03-08 and Sun 2026-11-01. |
| 7 | MEDIUM | `bt_costs` lets NaN through, defaults venue/tier to "unspecified", and the scripts print before stamping. | **Correct on all three.** | Fixed. `CostModel` requires finite values and non-empty, non-"unspecified" `venue`/`tier` (now positional, no defaults); `--venue/--tier` and `BT_VENUE/BT_TIER` are required; stamp is applied before the first `print`. Tests: NaN/inf, missing provenance, stamp content. "Verify configured costs actually affect fills" — true for the legacy scripts only via their constants; the Phase 2 framework takes `CostModel` as the single cost input and will carry a test that changing it changes P&L. |

Also noted and agreed: the Robinhood adapter is live-capable; `Broker` is an execution contract, not a review tool. The
Kraken/Coinbase stubs are the only "safe" members, and only because they refuse everything.

### The governance bridge (15-file proposal)

**Rejected for now; adopted in a lighter form.** Reasons:

- The repo has **zero** backtest runs in the new framework. Fifteen files of JSON schemas, validators, state machines
  and a CI workflow to govern evidence that does not exist yet is the wrong order. The same risk the review is worried
  about — a model declaring its own work accepted — is covered today by: Jacob is the only merger; every review and
  response is in this log; backtests are the tiebreaker and none exist.
- What is adopted now: this log (append-only, per review); the rule that **no model sets a final status** (statuses here
  are "fixed / deferred / rejected", never "approved"); `research_accepted ≠ trade_approved` written into §12b.
- What is adopted in Phase 2, when `research_runs` exists: an evidence manifest per run (code SHA, data snapshot hash,
  universe hash, `CostModel`, fill rule, folds, seeds, metrics, trial count) — that is the `evidence.schema.json` idea,
  attached to the thing it describes instead of a parallel tree. Review JSON and a validator come with it if two models
  are actually reviewing runs by then.
- `AGENTS.md`: not created. CLAUDE.md is the single instruction file; the three rules the review wants both agents to
  follow (no model consensus authorises money; no agent holds secrets; log every review) are in CLAUDE.md.
- Private Supabase review tables, RLS roles per agent, an MCP review API: deferred to Phase 9 with the recommendation
  cards, which is where a second agent would first need write access.

### Architecture disputes seeded (to be settled by backtest, Phase 4/8)

| Dispute | Competing claims | Test |
|---|---|---|
| D-1 BTC sweep | H-SWEEP-A (extreme fear only) vs B (fixed %) vs C (hybrid) | Phase 8: P(5 BTC in 5y) on resampled 2021–26 paths, same growth-account equity curve, Monte Carlo |
| D-2 Milestone risk table | Proposed caps vs. "they still blow up under correlated gaps" | Phase 7: portfolio simulation with 2022-05 (LUNA), 2022-11 (FTX), 2025-02 gap days; report worst-case heat realised vs cap |
| D-3 Alt-first growth | Alt engine vs. BTC/ETH DCA + cash baseline | Phase 4 tournament: net return, max DD, excluding top-3 winners, per-year |
| D-4 Exit complexity | §8b distribution/exit engine vs. a single trend-break exit | Phase 6: capital preserved across every ≥30% drawdown since 2021, net of whipsaw; entries and exits tested together |

Standing rule added to §8b/§10: reserve BTC is never inventory for the spot reverse grid; the two live in separate
ledgers (`btc_reserve_ledger` vs. growth-account positions) and no code path moves between them without a
`HUMAN_REVIEW_REQUIRED` flag.

### Collector

Agreed: `docs/COLLECTOR-UNKNOWN.md` is a report, not verification. Unknown provenance blocks promotion of any `kr_*`
derived result to evidence. The Phase 1 ingest records source timestamps, ingestion timestamps, gaps and checksums
per snapshot, and freezes snapshots per run.

### Open items carried forward

- Phase 9: durable order reservation + reconciliation; human approval binding; fake-broker concurrency test.
- Phase 2: evidence manifest per run; "changing CostModel changes P&L" test.
- Phase 1: collector provenance fields; snapshot freezing.

---

## R-2026-10-02-B — ChatGPT review of the discretionary watchlist / shadow ledger

Core claim: a hand-picked watchlist whose outcomes inform the scanner becomes training data; a shadow ledger does not make it independent. **Correct.** Response:

| # | Claim | Verdict | Action |
|---|---|---|---|
| 1 | Separate discretionary research from scanner validation | Fixed | `desk_watchlist.source` ('discretionary' / 'scanner') + `used_in_scanner_dev` flag; DESK tab now shows two labelled panels, *Discretionary hypotheses* and *Scanner validation evidence*; promotion is never automatic (docs/desk/PAPER-RULES.md) |
| 2 | Freeze theses before outcomes arrive | Fixed | `desk_watchlist_revisions` written by trigger on every insert/update; deletes refused by trigger; originals and revisions graded separately |
| 3 | Record the selection denominator | Fixed | `desk_selection_log`: pool considered (27 Kraken-lake names), selected (4), rejected with reasons (23), criteria, holdings note — first pass logged |
| 4 | Separate thesis accuracy from trade profitability | Fixed (rules) | Three scores — claim / path / trade — defined in PAPER-RULES.md; grading tooling arrives with the daily job |
| 5 | Deterministic ledger | Fixed (rules) + labelled exception | Shared $1,000 book, 10%/name, 50% gross; fill = next completed 5m close after `decided_at`; Kraken base tier 0.40/0.80 + 0.1% slippage; ambiguous candle = stop first; horizon from creation; `rule_version` per position. The four positions opened 05:20Z used the *last* close at decision → tagged `v0-provisional`, never scanner evidence |
| — | Base rate must match the prediction; no invented confidence | Fixed | All `confidence` values set to NULL, shown as "unknown (no reference class yet)" until Phase 4 defines reference classes |
| — | Full required-fields schema | Partially adopted | `claim`, `decided_at`, `expires_at`, `fee_model`, `rule_version` added now; stable asset IDs / contract / candidate-universe hash come with `universe_history` + `token_map` as the Coinbase universe backfills |

---

## R-2026-10-02-C — ChatGPT review of PAPER-RULES v1 / R-B

| # | Claim | Verdict | Action |
|---|---|---|---|
| 1 | Add benchmark-relative performance (same dollars in BTC at the alt's entry, liquidated at the alt's exits, same fee methodology), separate from claim/path/trade; book-level vs BTC B&H and cash | **Correct** | PAPER-RULES v2 §Grading #4; columns `btc_entry_px, btc_exit_px, alt_net_return, btc_net_return, excess_return_pp, max_drawdown` added; alt % stops are never applied to BTC |
| 2 | Reference class = reproducible sampling rule with the listed minimum definition; store `reference_class_rate` separately from `thesis_probability`; adjustments are subjective and labelled | **Correct** | Columns added (`reference_class_rate`, `reference_class_ref`, `thesis_probability`, `probability_adjustment_note`); definition table in v2 §Probability |
| 3 | No arbitrary sample-count gate; account for dependence; unknown when the denominator is not reproducible | **Correct** | v2 §Probability; the "Phase 4" wording in R-B is withdrawn as the determining factor |
| 4 | v1 contradiction: close-based exits + intrabar touches, daily or 5m depending on availability; a close trigger needs a subsequent executable fill | **Correct** | v2 defines two conventions (`daily-close`, `intrabar-5m`), one per thesis fixed at creation; missing 5m data → `fill_unavailable`, never a silent switch; daily-close fills at the next completed 5m close |
| — | Keep the four provisional positions outside calibration and benchmark evidence | Agreed | `evidence_class = 'exploratory'` on all four; `btc_entry_px` recorded (86,359 at 05:20Z) for display only, not evidence |

Not verified by the reviewer and still open: the DB triggers themselves (verified here by `desk_watchlist_revisions` count = 2× rows after the confidence update).

### Codex (automated) on PR #44 — all five accepted
P1 intrabar fill moved to the next completed 5m bar after the trigger bar · `monitoring_convention` now defaulted, NOT NULL and CHECK-constrained on both tables · fractional exits recorded per fill in `desk_paper_fills` (position-level fields become aggregates; single `btc_exit_px` dropped) · `evidence_class` default is `discretionary` with a CHECK, the four provisional rows explicitly `exploratory` · `alt_max_drawdown` and `btc_max_drawdown` stored separately.


---

## R-2026-10-02-D — ChatGPT review of PR #44 @ 6af1d3f (trigger hardening, fill rule)

| # | Claim | Verdict | Action |
|---|---|---|---|
| 1 | Revision table itself unprotected | Correct | UPDATE/DELETE/TRUNCATE reject triggers on revisions and selection log; INSERT/UPDATE/DELETE/TRUNCATE revoked on revisions and UPDATE/DELETE/TRUNCATE on selection log from anon/authenticated/service_role; inserts only via the audit function |
| 2 | TRUNCATE bypasses BEFORE DELETE | Correct | BEFORE TRUNCATE FOR EACH STATEMENT reject triggers on watchlist, revisions, selection log; TRUNCATE revoked |
| 3 | No immutable thesis identity | Correct | `thesis_id` UUID (unique) on watchlist, revisions, paper ledger; BEFORE UPDATE guard rejects changes to `thesis_id` or `symbol` |
| 4 | `max(revision)+1` unconstrained | Correct | per-row `revision` counter set by the guard trigger (`OLD.revision + 1`, serialised by the row lock); `UNIQUE (thesis_id, revision)` |
| 5 | SECURITY DEFINER without fixed search_path | Correct | all desk trigger functions `SET search_path = public, pg_temp`, schema-qualified |
| 6 | Latency-based fill rule, not a midnight delay | Agreed | `eligible_at = max(signal_available, decision_completed) + 60 s`, first 5m close strictly after; frozen; no liquidity assumption |
| 7 | intrabar-5m same-bar fill | Already fixed in 1f53022 (next completed bar after the touch bar) | — |

Verification run (below in this log once executed): ordinary insert/update, rejected symbol and thesis_id mutation, DELETE, TRUNCATE, direct revision tampering, under `service_role` and `postgres`.

**R-D verification (desk_selftest(), 2026-10-02 06:1x UTC):** `update_audited:t symbol_change:rejected tid_change:rejected delete:rejected rev_update:rejected rev_delete:rejected svc_rev_insert:rejected svc_sel_delete:rejected` — the last two under `SET LOCAL ROLE service_role`. TRUNCATE rejection is enforced by trigger + revoke but was not exercised in the selftest (no safe way to attempt it inside a function without a savepoint on a DDL-class statement); open item. Concurrency/rollback tests: open item for the Phase 2 test harness.

---

## R-2026-10-02-E — ChatGPT: TRUNCATE and concurrency test designs
Adopted verbatim as `docs/desk/TEST-PLAN.md` T1 and T2. Attempted T1 through the Supabase MCP tool: the tool hangs on
explicit `BEGIN … ROLLBACK` blocks (three attempts), fingerprints before/after identical (rows untouched). Execution moves
to the Phase 2 harness via psql. The point that the service_role test proves the REVOKE and only the owner test proves
the trigger is recorded in T1.

---

## R-2026-10-02-F — ChatGPT review of the backtest engine (PR #46 @ eb1cc85)

All ten accepted; #1, #2, #3, #5 were Phase 2 blockers and are fixed in the same PR.

| # | Claim | Action |
|---|---|---|
| 1 BLOCKER | `end_t` filtered bar labels, letting a fit window decide on the bar that opens at the fold boundary | `end_t` now bounds information: a bar is processed only if `t + bar <= end_t`. Test: a 50× spike in the bar opening exactly at the boundary cannot change the fit run |
| 2 HIGH | stops skipped on the entry bar | Stops/targets live from the fill; stop before target; gap below the stop at the open → entry at open+cost then stop at the open. Test: entry 100, low 80, stop 90, close 120 → stopped same bar |
| 3 HIGH | list-order capital/slot bias; buys processed before same-open sells | Sells first, then buys as a batch sorted by (priority desc, symbol asc). Test: reversed order → identical holdings and cash |
| 4 HIGH | silent partial fills | All-or-none; every refusal is an event (`no_fill`, reason cash/slots/no bar/already held); `no_fills` count in the result |
| 5 HIGH | `view._m` exposed the whole market | `AsOfView` is built with no Market reference (`__slots__`, materialised visibility cuts); plus a hygiene test that greps `strategies.py` for raw-market access. Claim softened in docs: enforced by interface + test, not by the language |
| 6 HIGH | ghost assets in the default universe | `listings` required (synthetic tests opt in with `infer_listings=True`); universe requires a bar completed in the immediately preceding interval. Test: stale DEAD excluded before its delisting date |
| 7 MEDIUM | equity stamped with the open time | Stamped `t + bar` (the close). Test added |
| 8 MEDIUM | fingerprint missed H/L/O/V | Hash over canonical OHLCV rows + listings. Test: a changed high changes the hash |
| 9 MEDIUM | missing fill bar silently lapsed | Recorded as `no_fill: no bar` event |
| 10 LOW | `next_bar` public | Renamed `bar_opening_at`, documented engine-only; covered by the hygiene test |

---

## R-2026-10-02-G — ChatGPT: slot allocator (PR #46)

Accepted verbatim. Strategies no longer size in dollars; the engine owns sizing.

| Requirement | Action |
|---|---|
| Equity-scaled equal slots, not fixed dollars | `slot_usd = equity_at_last_close × gross_cap / max_positions` (`run(..., max_positions=10, gross_cap=1.0)`; CLI `--max-positions`, `--gross-cap`). Result carries `sizing` |
| Keep all-or-none, `no_fill` events, starvation visible | Unchanged; a slot that does not fit cash is a `no_fill: cash` event, never a partial |
| Strategies rank simultaneous signals | `Order.priority` set by every house strategy (volume ratio, momentum score, dip depth); ties broken by symbol |
| $10k vs $100k regression | Test: identical price path, `sma_trend` from 10k and 100k → normalised equity curves equal to 1e-9; each fill = 10% of last-close equity |

Note for Phase 4: the slot is a baseline, not a claim. Volatility-scaled or conviction-weighted sizing is a Phase 4 study
run as an overlay against this baseline, not a change to the engine default.

---

## R-2026-10-02-H — ChatGPT review of PR #46 @ bd2979d (gross_cap default, fail-closed loader)

| # | Claim | Action |
|---|---|---|
| Q1 | Keep `gross_cap=1.0` as the tournament default; a `no_fill: cash` after a round trip is economic information (slot frozen at the prior close, executed at the next open), not a defect. Lowering the default hides turnover cost | Accepted. Default stays 1.0. 1.00/0.95/0.90 are Phase 4 cash-buffer overlays. `sizing` (rule, gross_cap, max_positions) is now in the manifest and in the config hash, so a 90% run can never share an id with a 100% run (test). The sells-first unit test uses 0.9 only to isolate slot release; it is not a default |
| BLOCKER | `market_from_rows()` inferred listings when a snapshot lacked them, reopening survivorship | `market_from_rows(rows, bar_seconds, listings=None, *, infer_listings=False)`; `load_snapshot` raises `ValueError` on a snapshot without listings. Tests: default raises; snapshot without listings refused; with listings loads |
| LOW | `AsOfView` comment overstated "materialised" | Reworded: visibility-capped reference, interface serves `bs[:i]`, guard is the StrategyHygiene test |
| Ask | Report the `no_fill` breakdown during the real-data reproduction | Engine result now carries `no_fill_reasons` {cash, slots, no bar, already held}; `bt_run.py` prints it with the run id |

Phase 2 gate as agreed: fail-closed loader (done, 42/42) → reproduce the house breakout rule on the frozen real dataset with the
`no_fill` breakdown reported → PASS/FAIL. The reproduction is blocked until `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` exist in the
cloud environment (read-only data pull; never pasted in chat).

---

## R-2026-10-02-I — ChatGPT: sizing-attribution protocol (one-off, before interpreting any changed edge)

Accepted as specified. Tool: `desk-loop/bt_attrib.py`, banner `NOT RESEARCH EVIDENCE — sizing attribution only`,
never imports `bt.store`, writes a text report only.

| Requirement | Action |
|---|---|
| Four cells on one frozen snapshot: legacy logic + legacy $ / honest engine + legacy $ / honest + slot 1.00 / honest + slot 0.95 (sensitivity) | Implemented. Legacy signals/trade/run ported verbatim from `backtest_breakout_full.py`; `run(fixed_usd=100)` is a diagnostic-only engine mode that never scales with equity |
| Same fees, dataset, universe, signal, stop rules, windows; only sizing differs | Costs fixed at the legacy 0.95%/side; same snapshot symbols; `strategies.breakout_legacy` = the legacy rule on the AsOfView (20d close-high, 1.5× volume, 7d RS > BTC, ≤15% ext, stop = max(20d low, entry×(1−trail)), trail 12/18 on closing highs, 2 entries per ISO week) |
| Freeze the dollar amount to the old house value | `SIZE = 100.0`, `COST_SIDE = 0.0095` copied from `backtest_house.py` |
| Output `trades | total | avg trade | max DD | win | PF | no_fill_reasons | exposure % | avg cash %` | All nine columns; exposure from a per-bar cash curve the engine now emits |
| Label clearly, never write `research_runs` | Banner at top and bottom of every report; no store import |

Deviation, stated: the legacy "half off at +25%" variant cannot be reproduced identically in the engine (no partial sells),
so ALL four cells run the legacy "no take-profit: trail 12/18 only, 2/wk" variant. Legacy counted taken trades toward the
weekly cap; the honest strategy counts proposals (differs only when a fill is refused, which the `no_fill` column shows).

Engine additions this review forced: `Order.trail` (ratchets on closing highs only, entry close is the seed), delisted
holdings close at the last available close with reason `delisted` (legacy did the same; the engine previously carried a
ghost mark), `cash_curve` in the result. Parity test: on a synthetic path where cash and listings never bind, cell 1 and
cell 2 agree on trades, win rate, average trade, profit factor and total return to 1e-6. 47/47.

Real-data run: blocked on `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` in the cloud environment (read-only pull for the frozen snapshot).

---

## R-2026-10-02-J — ChatGPT: delisting treatment stays constant in the attribution run

Accepted. No haircut in the Phase 2 reproduction or the attribution table: every cell exits a delisted holding at its
last available close minus one side of cost, exactly as the legacy script did. The report now carries the line
"delisting: legacy-symmetric treatment for attribution only". Reason recorded: one variable at a time — a harsher
terminal treatment introduced alongside the engine and allocator changes would make the #1→#2→#3 deltas unattributable.

Phase 4 robustness axis (committed, to be built when Phase 4 opens), run per strategy against the baseline:
1. legacy/symmetric (last close − cost) — the attribution reference
2. conservative forced exit at the last reliable executable price (last bar with volume above a liquidity floor, not the last print)
3. recovery haircuts from the last reliable mark: −25%, −50%, −100% (venue untradeable, no executable exit)
For any strategy whose edge depends materially on low-cap alts, cases 2–3 are part of the robustness GATE, not a footnote:
the manifest records the delisting treatment, and `research_runs` carries the edge that survives each case.

---

## R-2026-10-02-K — ChatGPT: liquidity floor for the conservative delisting exit (Phase 4 axis 2)

Accepted verbatim. Definition recorded for Phase 4 (not built yet; nothing in Phase 2 uses it):

- **Last reliable executable price** = close of the last completed bar before delisting whose **3-day median dollar
  volume** (close × volume, daily bars) ≥ **max($50,000, 10 × slot_usd)**. Dollar volume, never token volume; a rolling
  median, never a single print.
- slot_usd is the engine slot at that bar (equity × gross_cap / max_positions), so the floor scales with what we would
  actually have to sell: $1k or $5k slot → $50k/day; $10k slot → $100k/day; $50k slot → $500k/day.
- Robustness surface, not a single assumption: multiples **5× / 10× / 20×** slot_usd, crossed with the recovery
  haircuts from R-J (−25% / −50% / −100%). The manifest records multiple, absolute floor and haircut; `research_runs`
  carries the surviving edge per cell.
- Phase 2 attribution and reproduction remain legacy-symmetric (R-J); this rule is Phase 4 only.

---

## R-2026-10-02-L — ChatGPT: Phase 2 evidence chain and the no-store rule

Accepted. Research reads use the publishable key under explicit SELECT policies (`md_candles`, `universe_history`);
the service-role key stays out of every agent path. Jacob runs `export → frozen snapshot → bt_run breakout_legacy →
bt_attrib` in Terminal himself. The reproduction run uses `--no-store`: no `research_runs` row is written until the
reproduction is reviewed and accepted (the printed run_id is an identifier only). `PHASE2-REPRODUCTION.md` records:
snapshot data_hash, universe_hash, symbol count, delisted count, date span, fee model, fit/test windows, in-sample
metrics, OOS metrics, gate checks, trial count, no-fill breakdown, four-row attribution table. The repo/Vercel rename is
operationally separate from the verdict.

---

## R-2026-10-02-N — Phase 2 reproduction executed (PR #46 @ 3264acc)

Result in `docs/desk/PHASE2-REPRODUCTION.md` and `docs/desk/ATTRIBUTION-2026-10-02.txt`. Two invalid runs recorded and
excluded (truncated snapshot; stale listing proxies). Verified snapshot: 444,684 rows = DB count, 419 symbols, 88 delisted,
2020-03-08 → 2026-10-01, data_hash `8df7990c93dcc632`, universe_hash `64e00348d99bb713`. Framework reproduces the legacy
script within 2% (619 vs 607 trades, PF 0.83 vs 0.82). House breakout rule: rejected (OOS −84%, PF 0.81, 4/7 gate checks
fail). Allocator impact is exposure (4% → 38%), not edge. Nothing written to `research_runs`. Awaiting independent verdict.

---

## R-2026-10-03-O — ChatGPT independent verdict on the Phase 2 reproduction

> Independent R-N — Phase 2 framework PASS. House breakout REJECTED. Phase 3 may proceed. Before any Phase 4 strategy can
> receive an ACCEPTED verdict, move fee-stress gating to OOS walk-forward evidence and resolve/document proposal-vs-fill
> weekly-cap accounting.

Both notes implemented the same day (PR #46):

| # | Finding | Action |
|---|---|---|
| 1 | `breakout_legacy` weekly cap counted proposals; legacy counted taken trades, so a refused proposal could suppress a later signal | Cap now counts fills: a proposal is credited to its signal week when the symbol appears in `pf.positions` at the next decision; refused proposals consume nothing. Test: with `max_positions=1` refusals occur and later signals are still proposed. Synthetic parity test (cell 1 vs 2) still exact |
| 2 | `survives_fees_x1.25` used the full-sample robustness run only | `walk_forward` now also runs every OOS test window under ×1.25 fees (selection still on base costs) and returns `oos_fee_stress`; `gate` requires BOTH full-sample and OOS fee survival, and a missing OOS stress result fails the check. `bt_run` prints and records `oos_fee_stress`. Tests: OOS-negative under stress → rejected; missing → check False |

49/49 tests. Neither change alters the Phase 2 verdict (both cells were negative before sizing); the attribution table is
re-run below for the record.

---

## R-2026-10-03-P — ChatGPT review of the Phase 3 regime design v1 (PR #47)

All seven points accepted; design revised to v2 in `docs/desk/REGIME-DESIGN.md` before any code.

| # | Finding | v2 change |
|---|---|---|
| 1 BLOCKER | thresholds selected per strategy made regime a strategy parameter | one canonical pair frozen (band 0.02, vol_pct 0.90) shared by every strategy; other five pairs robustness-only, never chosen after seeing results (§4) |
| 2 BLOCKER | vol shock was a −1 vote, could be outvoted; fast-fail claim false | hard vetoes first (volpct ≥ vol_pct, dd ≤ −0.50 → raw risk_off), then trend + breadth classifier; breadth aggregates, not a veto (§3) |
| 3 HIGH | layer-pass rule "3 of 4" over six pairs; B&H a start-date test | B&H removed as acceptance test; layer described by strategy-independent OOS diagnostics (forward 1d/7d/30d BTC returns, forward DD, time in state) per label; Phase 4 decides per candidate (§9) |
| 4 HIGH | leaving `unknown` ambiguous | requires 3 consecutive fresh bars with the same raw state; counter resets to 1 on any change; hard veto fast-fails from `unknown` after 1 bar (§6) |
| 5 HIGH | breadth denominator/freshness undefined | `breadth_eligible` (listed, ≥50 bars), `fresh`, coverage; unknown if <20 eligible or coverage <60%; new listings never count as missing (§2a) |
| 6 MEDIUM | math not frozen | slope = SMA50_t/SMA50_{t−20} − 1 (0 non-positive); volpct includes current obs, (count ≤)/365; explicit 385-bar startup → unknown (§2) |
| 7 MEDIUM | "same order of magnitude" subjective | filtered trades ≥ 50% of unfiltered and ≥ 100 absolute; must also improve avg net trade return or profit factor (§10) |
| Q2 | `neutral_ok` | dropped; neutral blocks all entries in Phase 3; mean-reversion-in-neutral is a pre-registered Phase 4 overlay study (§1) |

---

## R-2026-10-03-Q — ChatGPT acceptance of the Phase 3 regime design v2

> R-Q — Phase 3 regime design ACCEPTED for implementation, subject to two final clarifications: filtered evaluation
> requires unfiltered OOS-positive + fee-stress survival; startup label is earliest-at-385, conditional on breadth
> readiness. No additional architecture changes required before coding.

Both clarifications applied in `REGIME-DESIGN.md` §10 and §12 before any code: filtered variants only for candidates
that pass `oos_positive` and both fee-stress checks unfiltered (at most one non-core miss); startup test is
"unknown before 385 BTC bars; non-unknown at 385+ only if breadth gates pass", with the ≥20-names-at-385 and
19-names-stays-unknown synthetic cases. Implementation starts from this revision.

---

## R-2026-10-03-R — Phase 3 implemented and run on the real snapshot (PR #47 @ 7b84ea7)

Engine: `desk-loop/bt/regime.py` (no Portfolio/Order/cost references, grep-tested), `AsOfView.regime()`,
`strategies.regime_gate`, `walk_forward(regime=…)` filtered twin on the same picks/folds, `overlay_eligible`,
`overlay_verdict` (a–e), `regime_sensitivity`, `forward_diagnostics`, `bt_run --regime`. 72/72 tests incl. the §12 list.
Result: `docs/desk/PHASE3-REGIME-RESULTS.md`. Canonical labels: risk_on 19.5% / neutral 14.8% / risk_off 49.6% /
unknown 16.1%, first label 2021-03-31, 62 transitions. OOS diagnostics do not support the layer: risk_on bars have the
weakest forward 30d BTC return (+0.45%, hit 44%) versus neutral (+2.40%) and risk_off (+1.92%); forward drawdowns equal
across states. Verdict: regime layer NOT EVIDENCED; Phase 4 runs unfiltered by default, labels recorded and reported per
state; no post-hoc threshold change (would be the forbidden optimisation). Overlay illustration on a losing sma_trend run
shows the hindsight rule rejecting a +8.8%-filtered / −30.2%-unfiltered rescue, as designed. Awaiting independent review.

---

## R-2026-10-03-R (verdict) — ChatGPT independent verdict on Phase 3

> R-R — Phase 3 PASS as engineering; canonical regime NOT EVIDENCED as a useful filter. Phase 4 proceeds unfiltered by
> default. Existing labels remain descriptive only. No post-hoc threshold/input changes permitted.

Recorded verbatim. Engine PASS (completed-bar inputs, exact breadth freshness, hard vetoes, deterministic hysteresis,
immediate unknown, shared series, label materialised into the view). Empirical PASS on "not evidenced; run unfiltered".

---

## R-2026-10-03-S — ChatGPT review of the Phase 4 pre-registration v1

All five changes accepted into `docs/desk/PHASE4-PREREGISTRATION.md` v2: (1) dynamic point-in-time top-20 dollar-volume
universe with frozen monthly mechanics and a frozen stablecoin/wrapped-asset exclusion map; (2) canonical cost = Kraken
taker tier + frozen spread/slippage (0.50%/side assumed until the live tier is read), stress ×1.25 full-sample and OOS,
legacy 0.95% as severe sensitivity only, Coinbase-history/Kraken-execution limitation in every manifest; (3) fold results
as selection evidence only, a continuous frozen-parameter OOS run as the verdict curve, boundary-exit count with a 20%/sign
inconclusive rule; (4) four-cell attribution dropped for Phase 4, gross_cap 0.95/0.90 as the only sizing sensitivities;
(5) eight-condition advancement rule, Phase 5 on research_accepted, Phase 10 additionally on Kraken paper reproduction;
canonical delisting case 10×/−50% triggered at ≥ 10% of OOS P&L or trades, mild and tail cases reported. mean_reversion
`n` confirmed as the MA lookback; breakout20 negative control never enters selection or trial accounting. Awaiting
acceptance to freeze.

---

## R-2026-10-03-S (acceptance) — Phase 4 pre-registration v2 FROZEN

> R-S — Phase 4 strategy-tournament pre-registration v2 ACCEPTED AND FROZEN at `0665068`. Implementation may begin. No
> candidate, parameter grid, universe rule, exclusion map, cost assumption, sizing rule, robustness threshold, or
> advancement criterion may change after tournament results begin. Any change requires a new pre-registration/version and
> cannot retroactively replace this tournament.

Implementation clarification (not a design change): the manifest persists the exact advancement booleans rather than a
recomputed "core" category — `oos_positive`, `survives_fees_x1.25`, `survives_fees_x1.25_oos`, `oos_trades>=100`,
`thirds_2_of_3`, `scale_invariant`, `symbols>=min`, `not_single_year`, `not_top3_dependent`, `delisting_canonical`
(with its trigger share), `boundary_dependency_ok`. Build order: universe builder → continuous OOS runner → cost sets →
delisting stress → manifest/gate fields → synthetic tests → one real frozen-snapshot tournament run → complete table to the
independent reviewer unchanged. Nothing is promoted to `research_accepted` before that review.

> **R-S FINAL — Phase 4 strategy-tournament pre-registration v2 ACCEPTED AND FROZEN after Phase 3 merge. Claude may build
> the tournament infrastructure. No candidate, parameter grid, universe rule, exclusion map, cost assumption, sizing rule,
> robustness threshold, or advancement criterion may change after tournament results begin. Any later change requires a new
> pre-registration/version and cannot retroactively replace this tournament. The first real frozen-snapshot tournament table
> must be sent unchanged to ChatGPT for independent review before any candidate is marked `research_accepted`.**

---

## R-2026-10-03-T — Phase 4 tournament, first frozen-snapshot run (UNREVIEWED; nothing promoted)

Table: `docs/desk/PHASE4-TABLE-2026-10-03.{md,json}` @ 65974d2. Snapshot data_hash `8df7990c93dcc632`, universe_hash
`64e00348d99bb713`, membership_hash `99c437c3e40dbb57`, 77 monthly rankings, OOS span 2021-03-08 → 2026-08-09 (22 folds).
All three candidates REJECTED on the frozen booleans: sma_trend continuous OOS −69.6% (×1.25 −71.4%, DD −89.2%, 289 trades,
PF 0.65); momentum_top −91.0% (−91.5%, DD −93.7%, 231, PF 0.43); mean_reversion −94.9% (−95.9%, DD −96.3%, 1,163, PF 0.73).
Every candidate fails oos_positive, both fee-stress checks, thirds, not_single_year and not_top3_dependent; all pass
scale invariance, ≥100 trades, delisting (not triggered) and boundary dependency. Negative control breakout20 −64.9%
(boundary-dependent). Benchmarks: BTC buy-and-hold +2.3% equity from a single 10% slot; BTC price itself +23.8% over the
span (52,415 → 64,909, peak 124,720); cash 0%. Sent unchanged to the independent reviewer. Observation for the reviewer,
not a rule change: under the frozen allocator the buy_and_hold benchmark deploys one engine slot, so its equity return
understates the asset's price return; both numbers are reported.

---

## R-2026-10-03-U — ChatGPT integrity review of the first Phase 4 table: FAIL, rerun required

Finding accepted: `evaluate()` passed the frozen monthly universe to the continuous verdict run but not to
`research.walk_forward` (parameter selection, chained OOS, OOS fee stress) nor to `research.robustness` (full-sample fee
gate), so those ran on the full listed universe. Implementation correction, not a rule change: `walk_forward` and
`robustness` now take `universe=` and apply it to every run; `evaluate()` passes it to both. Regression test
`UniverseThreading.test_outsider_cannot_influence_selection_or_gate`: a perfectly trending name with negligible volume
(never top-N) appears in the unthreaded run's P&L and never in the threaded selection, OOS, fee-stress, robustness or
continuous results. 82/82 tests. The first table (65974d2) is marked INVALID for integrity; provisional FAILs stand pending
the single corrected rerun on the same snapshot, costs, grids and rules.

---

## R-2026-10-03-V — Phase 4 tournament, corrected rerun (first VALID table; UNREVIEWED; nothing promoted)

Table: `docs/desk/PHASE4-TABLE-2026-10-03-rerun.{md,json}`. Same snapshot (data_hash `8df7990c93dcc632`, universe_hash
`64e00348d99bb713`), same membership_hash `99c437c3e40dbb57`, same costs, grids, sizing and rules; only change is R-U
(frozen universe threaded through selection, fee stress and robustness). Continuous OOS 2021-03-08 → 2026-08-09:
sma_trend −80.5% (×1.25 −81.7%, DD −92.9%, 305 trades, PF 0.53); momentum_top −90.5% (−90.9%, DD −91.8%, 219, PF 0.39);
mean_reversion −91.3% (−92.9%, DD −93.7%, 1,064, PF 0.75). All three fail oos_positive, both fee-stress checks, thirds,
not_single_year, not_top3_dependent; all pass ≥100 trades, scale invariance, delisting (exposure 3–8%, below the 10%
trigger) and boundary dependency (chained vs continuous within 20%, no sign flip). Negative control breakout20 −64.9%,
now boundary-clean. Benchmarks unchanged: BTC B&H +2.3% equity from one 10% slot (BTC price +23.8%), cash 0%. Verdicts per
frozen rules: three REJECTED. Sent unchanged for independent final verdicts.

> **R-V — Corrected Phase 4 tournament table VALID after R-U universe-threading fix. `sma_trend`, `momentum_top`, and
> `mean_reversion` are independently REJECTED. No candidate advances to Phase 5 or Phase 10. Round 2 design may begin
> under a new pre-registration. Before any future positive candidate can be accepted, held-position temporary missing
> bars must mark to the last known completed close rather than entry price, with stale marks surfaced in the evidence record.**

Nuances recorded with the table: `delisting_canonical=✓` in round 1 means the stress was not triggered (exposure 3–8%,
below 10%), not that the strategies survived the haircut. Hardening item implemented the same day: `Position.last_mark`
holds the last completed close; `Portfolio.equity()` marks a held name with no bar today at that close, never at entry
price; each such bar-day is an engine event `stale_mark` and the run result carries `stale_marks`. Test
`StaleMarks.test_missing_bar_marks_at_last_close_not_entry`. 83/83.

---

## R-2026-10-03-W — ChatGPT review of the round-2 pre-registration draft v1 (four blockers, one HIGH, two fixes, three answers)

All accepted; draft v2 written before any round-2 code (`PHASE4-ROUND2-PREREGISTRATION.md`). Fact found while answering
#3 that the reviewer must rule on: the F&G table holds 2 live rows (2026-10-02/03), no history over the OOS span.

| # | Severity | Claim | Verdict | Action in v2 |
|---|---|---|---|---|
| 1 | BLOCKER | A and B are responses to observed round-1 results; the 2021–2026 span is no longer untouched for them; round-2 historical results cannot confer `research_accepted` | **Correct.** | Evidence status rule at the top of v2: round 2 = post-Round-1 hypothesis screening; outcomes `historical_survivor` / `historical_rejected` / `inconclusive`; survivors advance only to a forward-validation stage on bars after the freeze; that stage is pre-registered and reviewed BEFORE the round-2 table is run; only it can confer `research_accepted`. A and B carry explicit provenance lines ("post-Round-1 decomposition hypothesis", "post-Round-1 response"). Heading rewritten as recommended. |
| 2 | BLOCKER | Inherited ≥100-trade, `symbols>=min` and symbol-concentration gates are structurally impossible for BTC-only A and C; pre-register candidate-class gates and an episode minimum now | **Correct.** | §0 classes: S (A, C) — positive continuous OOS, positive ×1.25, ≥2/3 thirds, positive P&L in ≥2 calendar years, scale invariant, no boundary dependency, P&L ex-top-3 trades > 50% of total, own falsifier; episode minimums frozen: A ≥ 10 completed round trips, C ≥ 8 completed non-overlapping episodes, fewer ⇒ `inconclusive`. X (B) keeps the full 11-boolean round-1 gate and ≥100 trades. Numbers offered for the reviewer to confirm or replace (Q1). |
| 3 | BLOCKER | C as written ("another slot every 7 days") cannot execute on a one-position-per-symbol engine; choose Option I (timing) or II (lot-aware accumulation) before coding | **Correct.** Option I adopted. | Rule: when flat and the usable reading ≤ threshold, buy next open, hold exactly 90 bars, sell next open, ignore readings while holding, no stop; verdict at 1 slot = 100%; Option II deferred to the accumulation phase. Falsifier uses the same non-overlapping executed signals; all-fear-days event study is descriptive only. |
| 3b | BLOCKER | "F&G dated D is known at D's close" cannot be assumed; store `observed_for_date`, `available_at`, `value`, `source`; a decision at t may use a reading only if `available_at ≤ t`; no provenance ⇒ not trustworthy | **Correct, and it bites harder than the draft knew.** `market_sentiment_daily` (snapshot_date, fear_greed, classification, source, observed_at) holds 2 rows, both live captures at 00:20 UTC of the dated day; there is no F&G history over 2021–2026 at all. A backfill from alternative.me gives date and value, not publication time. | v2 freezes the availability rule, `available_at` = collector capture for live rows, NULL (unusable) for backfilled rows, so C's verified-availability coverage of the OOS span is 0% ⇒ `inconclusive` by rule. Two pre-registered options for the reviewer (Q2): (i) C forward-only; (ii) a declared assumed-availability screening run (reading dated D usable from the close of D+1, ~47 h beyond the observed live lag, `evidence_class = assumed_availability`, best outcome `historical_survivor (assumed availability)`, still needing forward validation). Live collection continues daily meanwhile. |
| 4 | HIGH | B's floor/no-floor comparison must share the exact parameter picks per fold; select on the floor candidate; breadth from the contemporaneous top-20 only, not Phase-3 breadth; fail closed to cash on a missing constituent | **Correct.** | Paired twin runs the same selected parameters over the same OOS windows and continuous schedule; selection on the floor variant. Breadth = top-20 members above own SMA50 / members, computed at the rebalance close; fail closed to cash when membership < 20 or any member's bar is missing (`breadth_fail_closed` counted). Falsifier unchanged: return AND max DD AND PF. |
| Q1 | — | A at max_positions = 1? | Yes | Verdict run 100% BTC; 10-slot version is a sizing sensitivity; benchmarks 100% BTC B&H and cash (10%-slot B&H kept for continuity). |
| Q2 | — | B breadth source? | Top-20 only | As #4. |
| Q3 | — | C coverage < 80%? | Yes, plus any unexplained contiguous gap > 30 days; "usable" = verified `available_at ≤ decision close`; never forward-fill | Frozen verbatim. |
| fix | — | A's falsifier too loose | **Correct.** | R_A ≥ R_BH, or (R_A ≥ 0.70 × R_BH and DD_A ≤ 0.70 × DD_BH); positive after canonical and stress costs independently. |
| fix | — | C's hypothesis says 90 d but H includes 30 | **Correct.** | 90 d is the primary structural horizon and the only H in the grid; 30 d is a pre-registered sensitivity. |

No round-2 code written (handoff rule); build starts on `claude/phase-4-round2` after written acceptance of v2 and a
reviewed forward-validation pre-registration. Branch-keeping note: a parallel cloud session, unaware of PR #49, rebuilt
the round-1 infrastructure as PR #50; it was closed as superseded the same day, nothing from it is used.

---

## R-2026-10-03-X — ChatGPT acceptance of the round-2 pre-registration v2 (FROZEN)

> R-X — Phase 4 Round 2 pre-registration v2 ACCEPTED AND FROZEN at PR #51 @ `8a52e079`. Episode minimums A ≥10 and C ≥8
> accepted. Candidate C may run the pre-registered D+1 assumed-availability historical screening, explicitly labelled
> `assumed_availability`; it cannot confer research acceptance. Historical Round-2 results can only be
> `historical_survivor`, `historical_rejected`, or `inconclusive`. No Round-2 historical survivor may become
> `research_accepted` without the separately pre-registered fresh forward-validation stage.

Recorded verbatim; the three answers (Accept / ii / Freeze) are written into the frozen document's header. Reviewer's
procedural requirement applied: `docs/desk/PHASE4-FORWARD-VALIDATION.md` v1 is pre-registered and sent for review before
the round-2 historical table is run. Round-2 code build starts on `claude/phase-4-round2` (allowed from this acceptance);
the table is NOT run until the forward-validation stage is accepted.

---

## R-2026-10-04-Y — ChatGPT review of the forward-validation stage v1 (Revise / Accept / Freeze on revision)

> 1. Revise 2. Accept 3. Not yet. I found one internal contradiction in v1. The forward minimum of 4 class-S episodes cannot
> coexist sensibly with the frozen gate requiring P&L excluding the three best completed trades >50% of total P&L. With only
> four episodes, that leaves only the single worst episode after removing the best three; for a profitable strategy it is
> effectively impossible for that remainder to constitute >50% of total profit. Use the already-frozen candidate-specific
> Round-2 minimums forward as well: A ≥10 completed forward round trips; C ≥8 completed forward episodes. Keep the ≥365
> forward days requirement. For B, I accept ≥60 trades at first evaluation, ≥100 from the second onward. Everything else in
> the forward-validation document is acceptable, including two consecutive passes for `research_accepted`, any scheduled
> failure being final, fixed 90-day evaluation boundaries, forward-only gates, no historical pooling, and verified live
> `available_at` for C. So once §4 changes from generic `S ≥4` to A ≥10 / C ≥8, my answer to Q3 becomes Freeze.

| # | Claim | Verdict | Action |
|---|---|---|---|
| 1 | A 4-episode minimum makes the ex-top-3 > 50% gate unsatisfiable | **Correct.** | §4 now carries the frozen round-2 minimums forward: A ≥ 10 round trips, C ≥ 8 episodes, 365 days kept; B ≥ 60 at the first evaluation, ≥ 100 from the second. Document frozen as v1.1. |
| 2 | Two consecutive passes, any fail final | Accepted | Unchanged. |
| 3 | Freeze on the revision | Condition met verbatim | `PHASE4-FORWARD-VALIDATION.md` v1.1 FROZEN. The round-2 historical table now runs once on data_hash `8df7990c93dcc632` (re-exported this session with an end bound of 2026-10-01, hash reproduced exactly; sentiment snapshot `fng_2026-10-03.json`, 3,163 rows, 2 with verified `available_at`). |

---

## R-2026-10-04-Z — Phase 4 round 2 historical screening table, run once (UNREVIEWED; nothing promoted)

Table: `docs/desk/PHASE4-ROUND2-TABLE-2026-10-04.{md,json}` @ PR #51, run 2026-10-04 ~03:2x UTC after R-Y. Snapshot re-exported
this session with an end bound of 2026-10-01: data_hash `8df7990c93dcc632`, universe_hash `64e00348d99bb713`,
membership_hash `99c437c3e40dbb57` (identical to round 1). Sentiment snapshot: 3,163 rows, 2 with verified `available_at`.
Trials 176 (A 44 + B 88 + C 44; the control never counts). OOS span 2021-03-08 → 2026-08-09, 22 folds. Outcomes under the
frozen rules, sent unchanged:

| candidate | class | evidence | episodes / trades | OOS continuous | ×1.25 | severe | max DD | PF | falsifier | outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| A_btc_trend (100% BTC) | S | — | 26 round trips | −36.6% | −40.6% | −49.8% | −63.3% | 0.65 | fails (BTC B&H +22.6% / DD −76.7%; A has neither the return nor the 70%/30% clause) | **historical_rejected** |
| B_momentum_floor | X | — | 97 trades | −35.8% | −37.2% | −41.0% | −45.6% | 0.70 | **passes** (no-floor twin on the same picks −54.6% / DD −56.8% / PF 0.65) | **historical_rejected** (97 < 100 trades; also oos_positive, both fee-stress checks, thirds, not_top3 fail) |
| C_fear_greed, verified availability | S | verified | 0 | — | — | — | — | — | — | **inconclusive** (coverage 0%, gap 1,981 d — exactly as frozen) |
| C_fear_greed, assumed availability (D+1) | S | assumed_availability | 10 episodes (11 entries) | −58.5% | −59.6% | −62.4% | −77.7% | 0.33 | fails (signal 90 d mean −2.3%, hit 36%, vs base rate +5.8%, hit 52%) | **historical_rejected** |
| btc_bh_100pct / btc_bh_10pct_slot / cash | benchmarks | | | +22.6% / +2.3% / 0% | | | −76.7% / −11.1% / 0 | | | n/a |
| breakout20 | control | | 331 | −64.9% | | | −86.4% | | | n/a |

Readings, descriptive only: (1) the breadth cash floor is the one mechanism in two rounds that measurably helped — it
cut the no-floor twin's loss by 19 points and its drawdown by 11 — yet the floored rule still lost 36%; a mechanism that
loses less is not an edge. (2) Extreme Fear entries (D+1 lag) were followed by below-base-rate 90-day BTC returns on this
span (11 non-overlapping signals); the overlapping all-fear-days event study (263 days) shows +1.6% mean, 43% hit, also
below base rate; H-SWEEP-A as a timing rule is not supported here. (3) BTC-only trend lost 37% while 100% BTC B&H made
23% with a 77% drawdown; the 10-slot version lost 1.8%. (4) All candidates pass scale invariance and boundary dependency;
delisting exposure ≤ 3%; `stale_marks` 0 everywhere. Note on the printed reason for B: the outcome line names the trade
hurdle first; the boolean row lists every failing check. Nothing in `research_runs`. Awaiting the independent verdict
(outcomes are screening outcomes; no candidate enters forward validation unless the reviewer finds otherwise).

---

## R-2026-10-04-AA — ChatGPT independent verdict on the round-2 screening table (PR #51 @ 45cc49a)

> **R-AA — Phase 4 Round 2 historical screening table VALID. A_btc_trend = historical_rejected. B_momentum_floor =
> historical_rejected; its breadth cash-floor mechanism passes the paired falsifier but the strategy itself fails the
> frozen class-X gate. C_fear_greed verified = inconclusive for 0% verified historical coverage and is not
> forward-eligible because the shortfall is not episode-count-only. C_fear_greed assumed D+1 = historical_rejected. No
> Round-2 candidate advances to forward validation, Phase 5, or Phase 10. Nothing is promoted to research_accepted.**

Recorded verbatim. Table integrity PASS (hashes, stale marks 0, scale, boundary, delisting immaterial, evidence-status
rules applied). Zero entrants to the forward-validation stage; C-verified is retired (coverage, not episode shortfall).
Presentation note on B's outcome line acknowledged; no effect on the verdict, nothing edited after the run. Nothing in
`research_runs`. Reviewer: PR #51 ready for merge from the research-governance standpoint; merge is Jacob's call.

State after two rounds (for the next pre-registration, not a conclusion): six hypotheses tested under frozen rules on
2021-03 → 2026-08 (three generic alt rules, BTC-only trend, breadth-floored alt momentum, Extreme-Fear BTC timing); none
positive after costs; the only measurably helpful mechanism was the breadth cash floor (loss reduced, not eliminated);
100% BTC buy-and-hold made +22.6% with a −76.7% drawdown; cash 0%. The forward-validation stage exists and is frozen but
has no entrant; the live F&G collector keeps accumulating verified rows regardless.

---

## R-2026-10-04-AB — ChatGPT direction for round 3 and its falsifier; data audit; draft v1 for review

Direction received after R-AA: **round 3 — runner forensics**, falsifier verbatim: "if a point-in-time runner-forensics
model built from fundamentals, revenue/fees, tokenomics, liquidity/volume acceleration, relative strength, flows, and
catalysts cannot distinguish future 3x–5x runners from matched non-runners out-of-sample with materially better precision
than the base rate, after liquidity and survivorship controls, reject the entire Round-3 hypothesis."

Data audit before design (Supabase, 2026-10-04): point-in-time history over 2021–2026 exists only for price/volume
(`md_candles`, `universe_history`). `fund_snapshots_daily` (fees/revenue/TVL/DEX volume, 2,629 names) starts 2026-10-02
(3 days); `features_daily` 2026-09-30; `flow_radar` 10 days in September; no tokenomics or catalyst history anywhere.
Draft v1 (`docs/desk/PHASE4-ROUND3-PREREGISTRATION.md`) therefore: Stage 0 feature manifest reviewed before any label;
two studies (verified price-only; assumed-availability with backfilled DeFiLlama fundamentals at a 7-day lag); tokenomics
and catalysts excluded for lack of point-in-time sources; case-control with (month, liquidity-quintile) matching, delisted
names kept; L2 logistic regression, grid ≤ 4, expanding test years 2022–2025; precision@10% vs base rate with a frozen
"materially better" definition; shuffled-label negative control; minimum 40 runners. Awaiting review. No code, no label,
no feature computed. PRs #49 and #51 merged to main at Jacob's word (3d5ac5d, 7f88fb4).

---

## R-2026-10-04-AC — ChatGPT review of the round-3 draft v1 (Revise / Revise / Accept / Accept)

| # | Severity | Claim | Verdict | Action in v2 |
|---|---|---|---|---|
| 1 | serious (leakage) | Excluding 1.5×–<3× names from scoring uses a future label to shape the ranked population; precision@10% becomes artificially easy | **Correct.** | OOS model scores every eligible name at every formation date; primary metric is population precision (positive = 3×, non-positive = everything else incl. gray zone and delisted); gray-zone exclusion allowed only inside the binary fit; matched 3× vs <1.5× kept as a diagnostic that never gates; negative control on the full population. |
| 2 | metric | Label denominator must be the next executable open, not the formation close (overnight gap not capturable) | **Correct.** | `entry_reference` = next executable open after the formation close; `runner_3x` = max completed close during the next 180 bars ≥ 3 × entry_reference; same for 5× and 1.5×; no executable open ⇒ ineligible that month. |
| 3 | metric | Base rate must be the 3× share among ALL eligible candidates | **Correct.** | Frozen so, within (month, quintile) strata, positive-count weighted. |
| 4 | implementation | {verified, assumed} must not be a selectable hyperparameter | **Correct.** | Two separate pipelines, each selecting only C ∈ {0.1, 1.0}; 8 trials each; no step compares them. |
| Q3 | — | Run both studies now; assumed DeFiLlama study stays subordinate | Accepted | Subordination written into §3: a survivor can only generate a round-4 hypothesis, never a verified fundamental edge. |
| Q4 | — | Stage 0 before any labels | Accepted | Unchanged. |

v2 sent for review; no code, label or feature computed.

---

## R-2026-10-04-AD — ChatGPT review of the round-3 draft v2 (Revise / Revise / Accept / Not yet)

| # | Claim | Verdict | Action in v3 |
|---|---|---|---|
| 1 | 3× primary no longer matches the stated objective (2× and above is a win); hierarchy must be 2× primary / 3× secondary / 5× tail; non-positive = everything below 2× incl. delisted; no gray zone removed from scoring | **Correct.** | Labels rewritten; primary positive `runner_2x` = max completed close within 180 bars ≥ 2 × next executable open; 3× and 5× tiers defined identically; primary non-positive = M < 2×. |
| 2 | Do not train on 3× vs <1.5× and grade on another objective; the primary model learns 2× vs not-2×; the case-control contrast may remain a diagnostic model only | **Correct.** | Training population = scoring population, 2× vs not-2×; 3× vs <1.5× demoted to a labelled diagnostic that never gates. |
| 3 | Gate base rate and precision@10% become 2× population precision; keep the existing bar (≥ 2× pooled, ≥ 1.5× in 3 of 4 years, liquidity and top-month removals); report 3× and 5× lift as enrichment | **Correct.** | Statistic and gate rewritten on `runner_2x`; enrichment tests for 3×/5× in the top-10/5/20% buckets vs their own base rates, reported only; minimum evidence and negative control re-based on 2×. |
| Q3 | Separate verified / assumed pipelines | Accepted | Unchanged. |

v3 sent for review; no code, label or feature computed.


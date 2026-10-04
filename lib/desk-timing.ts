import type { Venue } from './rh-universe'
// TIMING GRADE — A/B/C/D/F for "is NOW a good moment to add this name", scored against the house
// laws (constitution v4/v4.1) and the tape. Deterministic, numbers only — never from thesis text.
// HARD bars (chase laws, RUNNING extension, drawdown halt) are an F that no button can override:
// the constitution says chase-bar exemptions are refused in any regime. An UNMEASURABLE law is a
// hard bar too (2026-09-10): without the 20-day high the RUNNING extension check cannot run, and a
// rate-limited chart fetch used to drop that law silently — leaving a name that might be 40% above
// its 20-day high grading D and buyable on override. Not proven safe is not the same as safe. PROCESS bars (cash floor,
// slots, weekly count, blackout) cap the grade at D — override territory, which the constitution allows
// Jacob per trade, and the override is logged. A / B / C = clear to buy at the ruled size.

export const ANCHOR = new Set(['BTC', 'SOL'])   // v4: ETH out of the anchor
export type Regime = 'BULL' | 'NEUTRAL' | 'BEAR'
// A9 §3 / A9.1 §1 (2026-09-06): the sleeve is an R&D budget — 15% of book, 10% per name, $50 flat entries; the
// 5% uncommitted-cash floor and the caps beat every target; a compliant size under $50 is a SKIP.
export const SLEEVE_CAP = 0.15, NAME_CAP = 0.10, CASH_FLOOR = 0.05, MIN_ENTRY = 50
// '?' = COULD NOT GRADE (no live price). It is NOT an F. An F is a judgement about the entry;
// '?' means the grader was blind. Conflating them made five B-scoring names look like rejects
// when CoinGecko rate-limited us (Jacob 2026-09-11: "why are they all ranked D or F").
export type Grade = 'A' | 'B' | 'C' | 'D' | 'F' | '?'

export interface TimingInput {
  symbol: string
  price: number
  d1: number | null; d7: number | null; d30: number | null       // % changes
  vol24h: number | null; avgVol20: number | null                 // USD
  hi20: number | null                                            // highest daily close of the prior 20 days
  tapeError?: string | null                                      // why the 30-day chart is missing, when it is
  rs7VsBtc: number | null                                        // 7d return minus BTC's, percentage points
  armed: { kind: string; level: number }[]                       // desk_triggers rows for the symbol
  cashUsd: number; bookUsd: number
  sleeveCount: number; slots: number; holdingsCount: number
  weeklyEntries: number                                          // sleeve buys since Monday 00:00 Denver
  blackout: string | null                                        // reason text when inside an entry blackout
  halted: boolean                                                // loop drawdown halt / kill switch off
  halfSize: boolean                                              // macro modifier active
  held: boolean
  priceStale?: { at: string } | null   // price came from cg_history, not a live quote
  // A9 (optional so older callers keep working): the tested breakout signal on the last completed close, the BTC
  // regime that conditions the chase bars, the sleeve breaker, and the exposure the caps are measured against.
  signal?: boolean | null; signalWhy?: string
  regime?: Regime; regimeWhy?: string
  breaker?: string | null                // ISO since-timestamp when the A9 sleeve breaker is tripped
  sleeveUsd?: number; nameUsd?: number
  // Venue (lib/rh-universe.ts). 'robinhood' = the agentic account can place the order; 'kraken' = Jacob
  // buys by hand; 'none' = watch only. Optional so older callers keep working. The venue NEVER touches the
  // grade — the first version made it a hard bar, which graded GRASS/DRV F and the C+ filter then hid the
  // very rows Jacob had asked to see (2026-10-03). It gates `buyable` and the pole seat only.
  venue?: Venue
}

export interface TimingResult {
  grade: Grade; score: number
  hard: string[]; soft: string[]; plus: string[]
  size: { usd: number; pctBook: number; halfSize: boolean; cappedBy: string | null; book: 'SLEEVE-RULE' | 'OWNER-BOOK' }
  stop: { price: number; source: string; pct: number }
  buyable: boolean            // no hard bar, score >= C, AND the agentic account has a pair for it
  overridable: boolean        // soft bars only, same venue condition
  venue: Venue                // where this name can actually be bought
  venueNote: string | null    // plain-English reason the button is off, when it is off for venue
}

const round2 = (n: number) => Math.round(n * 100) / 100

export function gradeTiming(i: TimingInput): TimingResult {
  const hard: string[] = [], soft: string[] = [], plus: string[] = []
  let score = 100
  let capC = false           // a required check could not run: visible, but never an A or B
  let capD = false            // a process bar (no slot, weekly cap, blackout, cash floor) caps the grade at D: override territory, never a clean buy
  const ded = (pts: number, why: string) => { score -= pts; soft.push(`−${pts} ${why}`) }
  const add = (pts: number, why: string) => { score = Math.min(100, score + pts); plus.push(`+${pts} ${why}`) }

  // ── HARD BARS (law) ──
  // A9 §4: the chase bars are REGIME-CONDITIONAL. In BULL the +70%/30d bar is off and a +15% day halves size
  // instead of barring; in NEUTRAL/BEAR (or when the regime is unknown) both bars stand in full.
  const bull = i.regime === 'BULL'
  if (!bull && i.d1 != null && i.d1 >= 15) hard.push(`chase law (${i.regime ?? 'regime unknown'}): +${i.d1.toFixed(1)}% in 24h (bar is +15%)`)
  if (!bull && i.d30 != null && i.d30 >= 70) hard.push(`chase law (${i.regime ?? 'regime unknown'}): +${i.d30.toFixed(0)}% in 30d (bar is +70%)`)
  if (i.breaker) hard.push(`A9 SLEEVE BREAKER tripped ${i.breaker.slice(0, 10)} — no new sleeve entries until it clears`)
  const ext = i.hi20 ? (i.price / i.hi20 - 1) * 100 : null
  if (ext != null && ext > 15) hard.push(`RUNNING: ${ext.toFixed(0)}% above its 20-day high (no-entry zone past +15%)`)
  if (i.hi20 == null) hard.push(`RUNNING law UNCHECKABLE: no 20-day high${i.tapeError ? ` — ${i.tapeError}` : ' — not enough daily history'}. Extension is unknown, so no entry is cleared.`)
  // The chase laws are the ones that keep us out of a name that has already run. If the 24h or 30d
  // change cannot be obtained from EITHER CoinGecko or cg_history, those laws cannot be evaluated and
  // the name must not clear. 2026-09-11: a rate limit nulled d30 and ARB — up 84% in 30 days and
  // hard-barred — graded A/100 and read as buyable. A check that cannot run is never a pass.
  if (i.d1 == null || i.d30 == null) hard.push(`CHASE LAWS UNCHECKABLE: ${i.d1 == null ? '24h' : ''}${i.d1 == null && i.d30 == null ? ' and ' : ''}${i.d30 == null ? '30d' : ''} change unavailable from every source. Cannot confirm the name has not already run.`)
  if (i.halted) hard.push('desk loop halted or paused — no new entries')
  if (i.held) hard.push('already held — adds go through the deposit basket, not the queue')
  // A rate-limited quote falls back to the last daily close so the grade is still readable, but an
  // order must never be sized or stopped off a stale mark (2026-09-10: CoinGecko 429s blanked the tab).
  if (i.priceStale) hard.push(`stale price — last close from ${i.priceStale.at.slice(0, 16).replace('T', ' ')}Z, no live quote. Refresh before any order.`)

  // ── A9 §3: the tested breakout rule is the ONLY sleeve entry. No signal = OWNER-BOOK, capped at D. ──
  if (i.signal === true) add(10, `A9 breakout signal on the last completed close (${i.signalWhy ?? ''})`)
  else if (i.signal === false) { ded(20, `no tested breakout signal (${i.signalWhy ?? ''}) — A9 entry rule; a buy here is OWNER-BOOK`); capD = true }
  if (bull && i.d1 != null && i.d1 >= 15) ded(10, `+${i.d1.toFixed(1)}% day in BULL — size HALVED instead of barred (A9 §4)`)
  if (i.regime && i.regime !== 'BULL') ded(5, `regime ${i.regime} (${i.regimeWhy ?? ''}) — both chase bars in force`)

  // ── TAPE ──
  if (ext != null) {
    if (ext > 0) ded(Math.round(ext * 1.5), `${ext.toFixed(1)}% above the 20-day high (fresh breakout territory)`)
    else if (ext < -25) ded(15, `${Math.abs(ext).toFixed(0)}% below the 20-day high — in a drawdown, no base yet`)
    else if (ext >= -3) add(10, `at the 20-day high with no extension — cleanest breakout point`)
  }
  if (i.d30 != null && i.d30 >= 40) ded(20, `+${i.d30.toFixed(0)}% in 30d — most of the move may be behind it`)
  else if (i.d30 != null && i.d30 >= 20) ded(8, `+${i.d30.toFixed(0)}% in 30d`)
  if (i.d7 != null && i.d7 >= 25) ded(10, `+${i.d7.toFixed(0)}% in 7d — hot week, expect a pullback`)
  if (i.d1 != null && i.d1 >= 8) ded(10, `+${i.d1.toFixed(1)}% today — buying strength intraday`)
  if (i.d1 != null && i.d1 <= -8) ded(8, `${i.d1.toFixed(1)}% today — catching a falling day`)
  if (i.rs7VsBtc != null) {
    if (i.rs7VsBtc < 0) ded(10, `weaker than BTC over 7d (${i.rs7VsBtc.toFixed(1)} pts)`)
    else if (i.rs7VsBtc >= 5) add(5, `outperforming BTC over 7d (+${i.rs7VsBtc.toFixed(1)} pts)`)
  }
  if (i.vol24h != null && i.avgVol20) {
    const x = i.vol24h / i.avgVol20
    if (x >= 1.5) add(8, `volume ${x.toFixed(1)}x its 20-day average — move is confirmed`)
    else if (x < 0.7) ded(10, `volume ${x.toFixed(1)}x its 20-day average — no participation`)
    // The 0.7-1.5 band scores neither way, but SAYING NOTHING reads as missing data (Jacob 2026-09-11:
    // "aster volume unconfirmed? ... actually all of them but eigen" — the numbers were there, the
    // grader was simply mute). State it: ordinary volume is a finding, not an absence.
    else soft.push(`volume ${x.toFixed(2)}x its 20-day average — ordinary, so the breakout's volume leg is NOT confirmed (needs 1.5x); this is measured, not missing`)
  } else {
    // ANY failure to compute the ratio lands here — not just a missing 20-day average. The guard above
    // needs BOTH today's volume and the average, so "have the average, missing today" previously fell
    // through both branches and no volume check ran at all: ONDO scored a clean A/100 on it (2026-09-11).
    // A check that could not run must never score the same as a check that passed. Volume is a REQUIRED
    // leg of the tested breakout, so an unmeasurable one costs 8 and caps the grade at C — the name
    // stays visible and overridable, it just cannot present as an A on the strength of a missing input.
    const which = i.avgVol20 == null && i.vol24h == null ? 'no 24h volume and no 20-day average'
      : i.avgVol20 == null ? 'no 20-day average' : 'no 24h volume'
    ded(8, `volume UNVERIFIED — ${which}${i.tapeError ? ` (${i.tapeError})` : ''}; the breakout's volume leg cannot be confirmed`)
    capC = true
  }
  const entryLines = i.armed.filter((a) => ['bid', 'entry', 'deep_rung', 'reclaim'].includes(a.kind))
  if (entryLines.length) {
    const nearest = entryLines.reduce((b, a) => Math.abs(a.level - i.price) < Math.abs(b.level - i.price) ? a : b)
    const away = (i.price / nearest.level - 1) * 100
    if (Math.abs(away) <= 3) add(10, `at the desk's armed ${nearest.kind} line ${nearest.level}`)
    else if (away > 10) ded(15, `${away.toFixed(0)}% above the desk's armed ${nearest.kind} line ${nearest.level} — paying up`)
  }

  // ── BOOK / PROCESS (soft, overridable) ──
  // A9 replaced the slot formula with caps; slots are reported for visibility but no longer gate (A9 §3, A9.1 §1).
  const floor = i.bookUsd * CASH_FLOOR
  // WEEKLY CAP REMOVED 2026-09-11 on Jacob's instruction ("there is no two entries per week cap if
  // there is take it out"). The rulebook contradicted itself: v3/3.1 listed "2 new entries/week" among
  // the process laws, a later amendment stated "weekly cap REPLACED by open slots", and a third clause
  // still said it applied. The grader was enforcing the retired half while the replacement (open sleeve
  // slots) was already live, so entries were being blocked twice by two versions of the same rule.
  // weeklyEntries is still reported for visibility; it no longer gates anything.
  if (i.blackout) { ded(40, `entry blackout: ${i.blackout}`); capD = true }
  if (i.holdingsCount >= 10) ded(15, `already at the ~10-holding target`)

  // ── SIZE — A9 §3 $50 flat; A9.1 §1: the 15% sleeve cap, 10% per-name cap and 5% uncommitted-cash floor take
  //    precedence; a compliant size under $50 is a SKIP (capped at D); half in the macro window or on a +15% BULL day ──
  const sleeveUsd = i.sleeveUsd ?? 0, nameUsd = i.nameUsd ?? 0
  let usd = MIN_ENTRY
  let cappedBy: string | null = null
  const limits: [number, string][] = [
    [i.bookUsd * SLEEVE_CAP - sleeveUsd, `sleeve cap 15% ($${(i.bookUsd * SLEEVE_CAP).toFixed(0)}, $${sleeveUsd.toFixed(0)} used)`],
    [i.bookUsd * NAME_CAP - nameUsd, 'per-name cap 10%'],
    [i.cashUsd - floor, `5% uncommitted-cash floor (cash $${i.cashUsd.toFixed(0)}, floor $${floor.toFixed(0)})`],
  ]
  for (const [room, why] of limits) if (room < usd) { usd = round2(Math.max(0, room)); cappedBy = why }
  if (usd < MIN_ENTRY) { ded(25, `compliant size $${usd.toFixed(0)} is under the $${MIN_ENTRY} minimum (${cappedBy}) — A9.1: SKIP`); capD = true }
  const halveDay = bull && i.d1 != null && i.d1 >= 15
  if (i.halfSize || halveDay) {
    usd = round2(usd / 2); cappedBy = i.halfSize ? 'macro half-size window (until the FOMC close 09-16 16:00 MT)' : 'A9 §4: +15% day in BULL = half size'
    if (usd < MIN_ENTRY) { ded(10, `half-size $${usd.toFixed(0)} is under the $${MIN_ENTRY} minimum — a $50 entry needs Jacob's per-trade override here`); capD = true }
  }
  if (usd > i.cashUsd) { usd = round2(Math.max(0, i.cashUsd)); cappedBy = 'buying power' }

  // ── STOP: the desk's armed stop row for the name, else −20% (v4 sleeve rule) ──
  const armedStop = i.armed.find((a) => a.kind === 'stop')
  const stop = armedStop && armedStop.level < i.price ? { price: armedStop.level, source: 'desk_triggers stop row', pct: (armedStop.level / i.price - 1) * 100 }
    : { price: round2(i.price * 0.80 * 1e6) / 1e6, source: 'v4 default −20% from fill', pct: -20 }

  score = Math.max(0, Math.min(100, Math.round(score)))
  // A stale price means UNGRADEABLE, not failed: report '?' and keep the merit score visible so a
  // data outage is never mistaken for a bad name. The hard bar still stands — '?' is never buyable.
  const blind = i.priceStale != null || i.hi20 == null || i.d1 == null || i.d30 == null
  const venue: Venue = i.venue ?? 'robinhood'
  const onRh = venue === 'robinhood'
  const meritHard = hard.filter((h) => !/^stale price|^RUNNING law UNCHECKABLE|^CHASE LAWS UNCHECKABLE/.test(h))
  let grade: Grade = blind && meritHard.length === 0 ? '?'
    : meritHard.length || hard.length ? 'F'
    : score >= 80 ? 'A' : score >= 65 ? 'B' : score >= 50 ? 'C' : score >= 35 ? 'D' : 'F'
  if (capC && (grade === 'A' || grade === 'B')) grade = 'C'
  if (capD && (grade === 'A' || grade === 'B' || grade === 'C')) grade = 'D'
  return {
    grade, score, hard, soft, plus,
    size: { usd, pctBook: i.bookUsd ? round2((usd / i.bookUsd) * 100) : 0, halfSize: i.halfSize || halveDay, cappedBy, book: i.signal ? 'SLEEVE-RULE' : 'OWNER-BOOK' },
    stop,
    buyable: onRh && hard.length === 0 && (grade === 'A' || grade === 'B' || grade === 'C') && usd > 0,   // D = override only, F = never
    overridable: onRh && hard.length === 0 && usd > 0,
    venue,
    venueNote: venue === 'kraken' ? 'Not on Robinhood. Buyable on Kraken by hand — this account cannot place the order.'
      : venue === 'none' ? 'Not on Robinhood or Kraken. Watch only.' : null,
  }
}

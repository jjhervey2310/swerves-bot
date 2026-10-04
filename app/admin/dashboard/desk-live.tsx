'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { venueFor } from '@/lib/rh-universe'
import { Panel } from './ui'
import HoldingChart from './holding-chart'
import PerfChart, { type PerfItem } from './perf-chart'

// ROBINHOOD tab, live half — v4 (Jacob 2026-09-06: "easily readable", "the crypto up in line", "one chart with
// all the holdings", "a button for up-to-date price + volume with an A–F timing rating", "buy right now if I click").
//   1. HOLDINGS as a proper table: price · 24h · qty · entry · value + weight · P&L vs entry · stop + distance · role.
//      Tap the symbol for its 1y chart; thesis + gate under a toggle. Then cash, account value, the deposit-adjusted
//      Trading P&L headline (build request #7) and the v4.1 structure strip.
//   2. UP NEXT — the queue (POLE → WATCH → VERIFYING from desk_theses, holdings excluded) with live numbers, the
//      armed entry lines, flow-radar and radar chips, a TIMING button (/api/fund/timing: live price, 24h volume,
//      A–F grade against the house laws + the tape, ruled size, stop) and a BUY button (/api/fund/buy: market order
//      for the ruled size + stop-limit on 100% of the units, only on a human tap, hard bars never overridable).
//      One PerfChart under it: every holding (solid) and every queue name (dashed), indexed to the window start.
//   3. Portfolio chart (server-rendered) + realized line.  4. Armed lines.  5. Collapsed panels.
// Numbers never come from thesis text. Everything re-fetches every 60s from /api/fund/state + CoinGecko.

interface Holding { symbol: string; qty: number; avg_cost: number; synced_at: string; basis_source?: string | null }
interface Trigger { symbol: string; kind: string; level: number; band_pct: number | null; spec: string | null }
interface Alert { at: string; symbol: string; kind: string; level: number | null; price: number | null; sent: boolean | null; queued: boolean | null; note: string | null }
interface Board { fact: string; updated_at: string }
export interface Thesis {
  symbol: string; status: string; thesis: string | null; gate: string | null; updated_at: string | null
  buy_rank?: number | null; entry_level?: number | null; entry_note?: string | null; sector?: string | null
}
/** One row of the NARRATIVE LEADERBOARD (build request #19), aggregated on the server. */
export interface SectorRow { sector: string; names: string[]; scanned: number; d7: number | null; d30: number | null; exposure_usd: number; exposure_pct: number | null; held: string[]; best_verified: string | null; gap: boolean }
/** NARRATIVE LEADERBOARD row — one of exactly ten seats. `rank` is the desk's evidence order (how much
 *  proof there is that money is already moving toward the coin), NOT momentum. `pick` is the one name
 *  we would buy if we chose this narrative, `entry` the level, and `verdict` the honesty field: a pick
 *  we could not verify reads UNVERIFIED on its face and must never look like a verified one.
 *  d7 / d30 / exposure are computed on the SERVER from the same radar scan and price chain as the
 *  sector table above, so the two boards can never print different numbers for the same names. */
export interface Narrative {
  rank: number; narrative: string; plain: string; evidence: string
  pick: string; pick_why: string; verdict: string; verified_on: string | null
  checked: string; against_it: string; entry: string | null; runner_up: string | null
  syms: string[] | null; sources: string; updated_at: string
  d7: number | null; d30: number | null; scanned: number; universe: number
  held: string[]; exposure_usd: number; exposure_pct: number | null
  // The rotation half. `turning` is 1..n on 7d strength RELATIVE TO BTC — which narrative is being
  // bought first right now — and is a different question from `rank`, which is how much proof there
  // is that money reaches the token. Neither is a forecast. null = not computable, sorts last.
  catalyst: string | null; catalyst_on: string | null; catalyst_kind: string | null; unlock_note: string | null
  rs7: number | null; rs30: number | null; breadth: number | null; breadth_of: number
  turnover_x: number | null; turning: number | null
}
/** A RESTING order at the broker (build request #14b). desk_triggers says what the desk meant to arm;
 *  this says what Robinhood is actually holding. */
export interface OpenOrder { order_id: string; symbol: string; side: string | null; order_type: string | null; level: number | null; qty: number | null; state: string | null; created_at: string | null; synced_at: string }
export interface RadarRow { symbol: string; stage: string; score: number; turnover: number; d1: number; d7: number; d30: number; price: number; scan_date: string }
export interface FlowRow { symbol: string; flow_score: number | null; stage: string | null; fees_wow: number | null; vol_wow: number | null; scan_date: string }
export interface DeskState {
  holdings: Holding[] | null; triggers: Trigger[] | null; alerts: Alert[] | null; board: Board | null; strategy: Board | null
  theses?: Thesis[] | null; radar?: RadarRow[] | null; flow?: FlowRow[] | null; loop_enabled?: boolean | null; at: string
  sectors?: SectorRow[] | null; unsectored_usd?: number | null
  narratives?: Narrative[] | null; narratives_error?: string | null
  narratives_benchmark?: { btc_d7: number | null; btc_d30: number | null; scan_turnover_median: number | null } | null
  orders?: OpenOrder[] | null; orders_synced_at?: string | null; orders_live?: boolean
  // Priced once on the SERVER, on the same chain as everything else. book is null when any position
  // could not be priced — unknown, never silently zero.
  book?: number | null; pos_value?: number | null; cash_usd?: number | null
  prices?: Record<string, number> | null; price_src?: Record<string, string> | null; unpriced?: string[] | null
}
export interface Realized { pnl: number; wins: number; losses: number; n: number }
export interface Capital {
  reachable: boolean
  baseline: { date: string; usd: number } | null
  net_flows: number                       // Σdeposits − Σwithdrawals since the baseline
  flows: { date: string; amount: number; kind: string; note: string | null }[]
}
interface Live { price: number; d1: number | null; d7: number | null; d30: number | null; vol: number | null }
interface Timing {
  symbol: string; at: string; price: number; vol24h: number | null; avgVol20: number | null; volX: number | null
  d1: number | null; d7: number | null; d30: number | null; hi20: number | null; extPct: number | null; rs7VsBtc: number | null
  tapeError: string | null; hi20Source: 'cg_history' | 'coingecko' | null
  book: number; cash: number; slots: number; sleeveCount: number; weeklyEntries: number; blackout: string | null; halfSize: boolean
  grade: 'A' | 'B' | 'C' | 'D' | 'F' | '?'; score: number; hard: string[]; soft: string[]; plus: string[]
  size: { usd: number; pctBook: number; halfSize: boolean; cappedBy: string | null }
  stop: { price: number; source: string; pct: number }
  buyable: boolean; overridable: boolean; rh_configured: boolean
  venue?: 'robinhood' | 'kraken' | 'none'; venueNote?: string | null
}
interface BuyResult { ok?: boolean; state?: string; order_id?: string; qty?: number; avg_price?: number; notional?: number; stop?: { order_id: string; stop: string; limit: string } | null; stop_error?: string | null; ledger_errors?: string[]; error?: string; message?: string }

const ANCHOR = new Set(['BTC', 'SOL'])   // v4: ETH out of the anchor (Jacob 09-05)
const fmt = (n: number) =>
  n >= 1000 ? `$${Math.round(n).toLocaleString('en-US')}`
  : n >= 1 ? `$${n.toFixed(2)}`
  : n >= 0.01 ? `$${n.toFixed(4)}`
  : n > 0 ? `$${n.toPrecision(3)}`
  : '$0'
const usd2 = (n: number) => `${n < 0 ? '−' : ''}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
// Buy-board prices (build request #17c): whole dollars above $1,000, cents between, four significant
// figures below a dollar with trailing zeros trimmed. Its own formatter rather than a change to `fmt`,
// which prices the holdings table, the queue and every timing panel.
const bfmt = (n: number) =>
  n >= 1000 ? `$${Math.round(n).toLocaleString('en-US')}`
  : n >= 1 ? `$${n.toFixed(2)}`
  : n > 0 ? `$${Number(n.toPrecision(4))}`
  : '$0'
const big = (n: number) => n >= 1e9 ? `$${(n / 1e9).toFixed(2)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `$${(n / 1e3).toFixed(0)}k` : `$${n.toFixed(0)}`
const denver = (iso: string) =>
  new Date(iso).toLocaleString('en-US', { timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
const hoursOld = (iso?: string | null) => iso ? (Date.now() - new Date(iso).getTime()) / 36e5 : Infinity
const Pct = ({ v, d = 1 }: { v: number | null | undefined; d?: number }) =>
  v == null ? <span className="text-neutral-400">—</span>
  : <span className={`font-mono tabular-nums ${v >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{v >= 0 ? '+' : ''}{v.toFixed(d)}%</span>
const GRADE: Record<string, string> = {
  A: 'bg-emerald-500 text-white', B: 'bg-green-500 text-white', C: 'bg-amber-400 text-black', D: 'bg-orange-500 text-white', F: 'bg-rose-600 text-white',
  '?': 'bg-neutral-400 text-white',   // could not grade (no live price) — never a judgement on the name
}
const STATUS: Record<string, string> = {
  POLE: 'bg-amber-100 text-amber-800 dark:bg-amber-400/20 dark:text-amber-200', WATCH: 'bg-sky-100 text-sky-800 dark:bg-sky-400/20 dark:text-sky-200',
  VERIFYING: 'bg-violet-100 text-violet-800 dark:bg-violet-400/20 dark:text-violet-200',
}

export default function DeskLive({ initial, secret, cg, chart, realized, capital, bottom }: {
  initial: DeskState
  secret: string
  cg: Record<string, string>
  chart: ReactNode
  realized: Realized | null
  capital: Capital
  bottom: ReactNode
}) {
  const [state, setState] = useState<DeskState>(initial)
  const [live, setLive] = useState<Record<string, Live>>({})
  const [degraded, setDegraded] = useState(false)
  const [toggling, setToggling] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  const [thesisOpen, setThesisOpen] = useState<Record<string, boolean>>({})
  const [showBelowC, setShowBelowC] = useState(false)
  const [priceMeta, setPriceMeta] = useState<{ at: string | null; stale: boolean; error: string | null; missing: string[] }>({ at: null, stale: true, error: null, missing: [] })
  const [nowTick, setNowTick] = useState(() => Date.now())
  const [showWatch, setShowWatch] = useState(false)
  // Which question the leaderboard is answering right now. 'proof' = how real is it (the default,
  // and the one that decides what we own). 'turning' = which one is being bought first today.
  const [narrOrder, setNarrOrder] = useState<'proof' | 'turning'>('proof')
  const [timing, setTiming] = useState<Record<string, Timing | { error: string } | 'loading' | undefined>>({})
  const [buying, setBuying] = useState<Record<string, BuyResult | 'working' | undefined>>({})

  const toggleLoop = async () => {
    if (toggling) return
    const on = state.loop_enabled !== false
    if (!confirm(on ? 'PAUSE the 24/7 desk loop? (stops at the broker stay in place)' : 'RESUME the 24/7 desk loop?')) return
    setToggling(true)
    try {
      const r = await fetch('/api/fund/loop-toggle', { method: 'POST', headers: { 'x-admin-secret': secret } })
      if (r.ok) { const j = await r.json(); setState((s) => ({ ...s, loop_enabled: j.loop_enabled })) }
    } finally { setToggling(false) }
  }

  // 60s: desk state (DB, authed, no-store).
  useEffect(() => {
    let dead = false
    const pull = async () => {
      try {
        const r = await fetch('/api/fund/state', { cache: 'no-store', headers: { 'x-admin-secret': secret } })
        if (!r.ok) { setDegraded(true); return }
        const j = (await r.json()) as DeskState
        if (!dead) { setState(j); setDegraded(false) }
      } catch { setDegraded(true) }
    }
    // PULL ON MOUNT, not only every 60s. The server component builds `initial` from its own queries,
    // and several fields are served ONLY by this route — narratives, sectors, the server-priced book.
    // Without this first call those fields stayed absent for a full minute after every page load, so
    // the narrative leaderboard and the sector table rendered their empty branch on arrival and then
    // silently filled in. Found on the live page 2026-09-15.
    pull()
    const iv = setInterval(pull, 60_000)
    return () => { dead = true; clearInterval(iv) }
  }, [secret])

  const theses = state.theses ?? []
  const holdings = state.holdings ?? []
  const positions = holdings.filter((h) => h.symbol !== 'USD' && Number(h.qty) > 0)
  const held = new Set(positions.map((p) => p.symbol))
  // BUILD REQUEST #15 — basis caveat, shown and never hidden. Robinhood reports direct_cost_basis 0 on
  // every crypto position in this account (the original units were transferred in from Kraken), so the
  // entry prices here are DESK-TRACKED unless a row says otherwise. Any figure built on them carries an
  // asterisk rather than an implied broker confirmation.
  const deskBasis = positions.filter((p) => (p.basis_source ?? 'desk') !== 'broker').map((p) => p.symbol)
  const RANK: Record<string, number> = { POLE: 0, WATCH: 1, VERIFYING: 2 }
  const queue = theses.filter((t) => t.status in RANK && !held.has(t.symbol)).sort((a, b) => RANK[a.status] - RANK[b.status] || a.symbol.localeCompare(b.symbol))
  // AUTO-GRADE THE QUEUE. The C+ filter was inert because a name is only graded when you tap Timing,
  // so an ungraded list showed everything (Jacob 2026-09-11, with a screenshot of the unfiltered list).
  // Grading is cheap now that prices come from Coinbase/Robinhood rather than a rate-limited CoinGecko.
  // Staggered so eighteen names do not arrive as one burst; failures are left ungraded, never hidden.
  const queueKey = queue.map((t) => t.symbol).join(',')
  useEffect(() => {
    const syms = queueKey ? queueKey.split(',') : []
    if (!syms.length) return
    let dead = false
    ;(async () => {
      for (const sym of syms) {
        if (dead) return
        const already = await new Promise<unknown>((res) => setTiming((t) => { res(t[sym]); return t }))
        if (already !== undefined) continue
        setTiming((t) => ({ ...t, [sym]: 'loading' }))
        try {
          const r = await fetch(`/api/fund/timing?symbol=${sym}`, { cache: 'no-store', headers: { 'x-admin-secret': secret } })
          const j = await r.json()
          if (!dead) setTiming((t) => ({ ...t, [sym]: r.ok ? (j as Timing) : { error: j.error ?? `HTTP ${r.status}` } }))
        } catch (e) {
          if (!dead) setTiming((t) => ({ ...t, [sym]: { error: e instanceof Error ? e.message : 'fetch failed' } }))
        }
        await new Promise((res) => setTimeout(res, 600))
      }
    })()
    return () => { dead = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueKey, secret])

  // RANK BY GRADE, NOT BY STATUS (Jacob 2026-09-11: "shouldnt the ones you gave 100 be at the top").
  // `queue` stays in its stable desk order so the auto-grade effect's key does not churn as grades
  // land; this is a separate view for rendering. Best score first, ungraded next (they are still
  // resolving, not rejected), then '?' which could not be graded, and D/F last — those collapse.
  // These row helpers are declared HERE, above convictionOf, because convictionOf calls flowFor
  // during render (the queue sort runs it immediately). They used to sit 100 lines lower, which
  // threw 'Cannot access flowFor before initialization' and blanked the whole tab — TypeScript
  // cannot catch it because the reference is inside a closure and only fails when that closure runs.
  // ── ARMED AT THE BROKER (build request #14b) ──────────────────────────────────────────────────
  // Three possible answers, and they must stay three: ARMED (an order is resting, here is its id and
  // level), NOT ARMED (we asked the broker and there is nothing), and UNKNOWN (we could not ask, or
  // the snapshot is too old to stand behind). Collapsing UNKNOWN into NOT ARMED would be the same
  // defect as a failed fetch rendering as a zero.
  const orderRows = state.orders ?? null
  const ordersAgeH = hoursOld(state.orders_synced_at ?? orderRows?.[0]?.synced_at ?? null)
  const ordersKnown = orderRows !== null && ordersAgeH <= 6
  // Buy-side resting orders are no longer rendered anywhere (#18 took the armed column off the board),
  // but they stay in the payload for the desk's own reconciliation. The stop side IS still shown, on
  // the holdings table, because a position with no resting stop is a fact he needs on the face.
  const restingStop = (sym: string) =>(orderRows ?? []).find((o) => o.symbol === sym && (o.side ?? '').toLowerCase() === 'sell' && o.level != null) ?? null

  const trig = (sym: string, kinds: string[]) => (state.triggers ?? []).filter((t) => t.symbol === sym && kinds.includes(t.kind))
  const thesisFor = (sym: string) => theses.find((t) => t.symbol === sym) ?? null
  const radarFor = (sym: string) => (state.radar ?? []).find((r) => r.symbol === sym) ?? null
  const flowFor = (sym: string) => (state.flow ?? []).find((r) => r.symbol === sym) ?? null

  // CONVICTION: WHAT WE THINK WILL RUN, AND WHY (Jacob 2026-09-11: "i want it ranked on what we think
  // is going to run with evidence"). The A-F grade answers a different question — MAY we buy this,
  // legally and at a sane moment. Ranking by it put names with no reason to move above ones with a
  // proven buyback. So the board now ranks on evidence of a coming move, and the grade stays as the
  // gate beside it. Every term below is a fact we hold, not an opinion:
  //   mechanism  the verify agent's dated verdict — is real money reaching holders, and is it big
  //   flow       volume expanding while price is flat or down = money arriving BEFORE price
  //   strength   outperforming BTC over 7d, and actually rising
  //   room       how far below its 20-day high — a name already extended has less left
  // HONESTY: this is a reasoned weighting, NOT a backtested edge. Every mechanical rule this desk has
  // tested came out negative. Treat it as an ordered argument, never as a prediction.
  // flowFor is declared HERE, above convictionOf, and must stay above it: convictionOf reads it,
  // and the queueRanked sort calls convictionOf further down. A `const` arrow is in the temporal
  // dead zone until its own line runs, so with this declaration below the sort the ROBINHOOD tab
  // threw "Cannot access 'flowFor' before initialization" on every render with two or more names
  // queued — which server-rendered into the crash panel and read as the whole dashboard going down
  // (2026-09-12). One name never tripped it, because a sort of one element never calls its comparator.

  const convictionOf = (sym: string) => {
    const th = theses.find((x) => x.symbol === sym)
    const txt = (th?.thesis ?? '').toUpperCase()
    const tm = timing[sym]
    const T = tm && tm !== 'loading' && !('error' in tm) ? tm : null
    const fl = flowFor(sym)
    const why: string[] = []
    let score = 0
    if (txt.includes('VERIFIED-MATERIAL') || txt.includes('MECHANISM VERIFIED —')) { score += 40; why.push('proven buyback, big enough to matter') }
    else if (txt.includes('VERIFIED-IMMATERIAL') || txt.includes('NOT YET MATERIAL')) { score += 8; why.push('mechanism real but too small yet') }
    else if (txt.includes('NO-MECHANISM')) { score -= 30; why.push('pays holders nothing') }
    else why.push('earnings unverified')
    const volx = T?.volX ?? null
    const d7 = T?.d7 ?? null
    if (volx != null && volx >= 1.5) { score += 18; why.push(`volume ${volx.toFixed(1)}x`) }
    else if (volx != null && volx >= 1.0 && d7 != null && d7 <= 0) { score += 14; why.push('volume holding while price dips — accumulation') }
    else if (volx != null && volx < 0.7) { score -= 10; why.push(`volume ${volx.toFixed(2)}x, nobody there`) }
    const rs = T?.rs7VsBtc ?? null
    if (rs != null && rs >= 5) { score += 15; why.push(`beating BTC by ${rs.toFixed(0)} pts`) }
    else if (rs != null && rs < -5) { score -= 8; why.push('lagging BTC') }
    if (d7 != null && d7 > 0) { score += 10; why.push(`up ${d7.toFixed(1)}% this week`) }
    const ext = T?.extPct ?? null
    if (ext != null && ext <= -25) { score -= 8; why.push('deep below its base') }
    else if (ext != null && ext > -10 && ext <= 0) { score += 8; why.push('near its high, coiled') }
    if (fl?.flow_score != null && fl.flow_score > 20) { score += 10; why.push(`flow scan +${fl.flow_score.toFixed(0)}`) }
    return { score, why }
  }

  // LETTER FIRST, THEN SCORE. Score alone put a 92-scoring C above a 90-scoring A, because a capped
  // grade keeps its high score (volume unverifiable costs 8 and caps at C). The letter is the verdict;
  // the score only orders names that share one.
  const LETTER: Record<string, number> = { A: 0, B: 1, C: 2 }
  const gradeRank = (sym: string) => {
    const tm = timing[sym]
    const T = tm && tm !== 'loading' && !('error' in tm) ? tm : null
    if (!T) return { tier: 1, letter: 9, score: 0 }                      // still grading
    if (T.grade === 'D' || T.grade === 'F') return { tier: 3, letter: 9, score: T.score }
    if (T.grade === '?') return { tier: 2, letter: 9, score: T.score }
    return { tier: 0, letter: LETTER[T.grade] ?? 9, score: T.score }
  }
  const queueRanked = [...queue].sort((a, b) => {
    const ca = convictionOf(a.symbol).score, cb = convictionOf(b.symbol).score
    if (cb !== ca) return cb - ca                       // conviction leads
    const ra = gradeRank(a.symbol), rb = gradeRank(b.symbol)
    return ra.tier - rb.tier || ra.letter - rb.letter || rb.score - ra.score || a.symbol.localeCompare(b.symbol)
  })
  // POLE IS THE BEST GRADE, FULL STOP (Jacob 2026-09-11: "pole should be best graded. its for pole
  // position"). I argued for requiring a verified mechanism too; he overruled it, and it is his book.
  // Pole position goes to whoever is fastest. The verification state is still SHOWN beside it, so an
  // unverified name can hold pole but can never look verified while doing so.
  const verified = (sym: string) => {
    const t = theses.find((x) => x.symbol === sym)
    if (!t) return false
    const txt = `${t.thesis ?? ''}`.toLowerCase(), gate = `${t.gate ?? ''}`.toLowerCase()
    return /(fee switch|buyback|revenue|burn|fee[- ]share|accru)/.test(txt) && !/(unverified|verify|unproven)/.test(txt + ' ' + gate)
  }
  const poleSym = queueRanked.find((t) => {
    const tm = timing[t.symbol]
    const T = tm && tm !== 'loading' && !('error' in tm) ? tm : null
    // A Kraken-only or no-venue name never takes the pole seat: the pole is a standing pre-approved buy
    // and this account has no executor for it. Grade and visibility are untouched.
    return T != null && ['A', 'B', 'C'].includes(T.grade) && (T.venue ?? 'robinhood') === 'robinhood'
  })?.symbol ?? null
  // Every name that needs a live number: held, queued, and anything the desk has ranked onto the buy board.
  const liveSyms = [...new Set([...positions.map((p) => p.symbol), ...queue.map((t) => t.symbol), ...theses.filter((t) => t.buy_rank != null).map((t) => t.symbol), ...(state.narratives ?? []).map((n) => n.pick)])]
  const liveKey = liveSyms.join(',')

  // 60s: live price + 24h/7d/30d + 24h volume for held and queued symbols.
  // BUILD REQUEST #14(a). This used to call CoinGecko straight from the browser, once per open tab,
  // which is what stopped the feed updating: every tab was its own anonymous client of a rate-limited
  // endpoint. Now it asks OUR route, which makes one keyed upstream call per 45s and shares it. The
  // route returns the age of the numbers it is serving, so the stamp below is the age of the DATA and
  // never of the request — a silent stale price is worse than no price.
  useEffect(() => {
    const syms = liveKey ? liveKey.split(',') : []
    if (!syms.length) return
    let dead = false
    const pull = async () => {
      try {
        const r = await fetch(`/api/fund/prices?symbols=${syms.join(',')}`, { cache: 'no-store', headers: { 'x-admin-secret': secret } })
        if (!r.ok) { if (!dead) setPriceMeta((m) => ({ ...m, error: `price route HTTP ${r.status}` })); return }
        const j = (await r.json()) as { at: string | null; stale: boolean; error: string | null; missing?: string[]; prices: Record<string, Live & { src?: string }> }
        if (dead) return
        setPriceMeta({ at: j.at, stale: j.stale, error: j.error, missing: j.missing ?? [] })
        setLive((prev) => {
          const next = { ...prev }
          for (const [sym, v] of Object.entries(j.prices ?? {})) if (v?.price) next[sym] = { price: v.price, d1: v.d1 ?? null, d7: v.d7 ?? null, d30: v.d30 ?? null, vol: v.vol ?? null }
          return next
        })
      } catch (e) { if (!dead) setPriceMeta((m) => ({ ...m, error: e instanceof Error ? e.message : 'price fetch failed' })) }
    }
    pull()
    const iv = setInterval(pull, 60_000)
    return () => { dead = true; clearInterval(iv) }
  }, [liveKey, secret])

  // Age of the prices on screen, recomputed every 15s so the banner appears without a refresh.
  useEffect(() => { const iv = setInterval(() => setNowTick(Date.now()), 15_000); return () => clearInterval(iv) }, [])
  const priceAgeMs = priceMeta.at ? nowTick - new Date(priceMeta.at).getTime() : null
  const pricesStale = priceMeta.at == null || (priceAgeMs != null && priceAgeMs > 180_000)
  const priceStamp = priceMeta.at
    ? new Date(priceMeta.at).toLocaleTimeString('en-US', { timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null

  const cash = Number(holdings.find((h) => h.symbol === 'USD')?.qty ?? 0)
  const board = state.board?.fact ?? ''
  const boardPoleSym = (board.split('\n').find((l) => l.trim().startsWith('★')) ?? '').match(/POLE:\s*([A-Z0-9]{2,10})/)?.[1] ?? null
  const oldestSync = positions.length ? Math.max(...positions.map((h) => hoursOld(h.synced_at))) : Infinity
  const boardAge = hoursOld(state.board?.updated_at)
  const stale = oldestSync > 12 || boardAge > 36
  const stopFor = (sym: string) => trig(sym, ['stop'])[0]?.level ?? null
  const heldPole = theses.find((t) => t.status === 'POLE' && held.has(t.symbol)) ?? null
  // THE SERVER'S NUMBER IS THE NUMBER. It prices on Robinhood -> Coinbase -> last close, the same
  // chain the grader uses, so the tab and the desk can never disagree. The client's own CoinGecko
  // prices are kept only for the per-row 24h moves. `?? 0` on a missing price is what used to shrink
  // the account silently (2026-09-11).
  const srvPrice = (sym: string) => state.prices?.[sym] ?? live[sym]?.price ?? null
  const val = (p: Holding) => { const px = srvPrice(p.symbol); return px == null ? 0 : Number(p.qty) * px }
  const serverBook = state.book ?? null
  const unpricedSyms = state.unpriced ?? []
  const allPriced = serverBook != null || positions.every((p) => srvPrice(p.symbol) != null)
  const posValue = state.pos_value ?? positions.reduce((s, p) => s + val(p), 0)
  const book = serverBook ?? (posValue + cash)
  const openPos = open ? positions.find((p) => p.symbol === open) ?? null : null
  const synced = positions.length ? [...positions].sort((a, b) => +new Date(b.synced_at) - +new Date(a.synced_at))[0].synced_at : null

  const checkTiming = async (sym: string) => {
    // A second tap CLOSES the panel (Jacob 2026-09-10: "when you click it again it should close it,
    // just refreshes right now"). Re-opening re-fetches, so nothing is lost by closing.
    if (timing[sym] && timing[sym] !== 'loading') { setTiming((t) => ({ ...t, [sym]: undefined })); return }
    setTiming((t) => ({ ...t, [sym]: 'loading' }))
    try {
      const r = await fetch(`/api/fund/timing?symbol=${sym}`, { cache: 'no-store', headers: { 'x-admin-secret': secret } })
      const j = await r.json()
      setTiming((t) => ({ ...t, [sym]: r.ok ? (j as Timing) : { error: j.error ?? `HTTP ${r.status}` } }))
    } catch (e) { setTiming((t) => ({ ...t, [sym]: { error: e instanceof Error ? e.message : 'fetch failed' } })) }
  }
  const buy = async (sym: string, t: Timing, override: boolean) => {
    const lines = [
      `BUY ${sym} at market — about $${t.size.usd.toFixed(2)} (${t.size.pctBook.toFixed(1)}% of the book${t.size.cappedBy ? `, capped by ${t.size.cappedBy}` : ''})`,
      `Live ${fmt(t.price)} · timing grade ${t.grade} (${t.score}/100)`,
      `A stop-limit on 100% of the units goes in at fill: ${fmt(t.stop.price)} (${t.stop.pct.toFixed(0)}%, ${t.stop.source})`,
      override ? `\nOVERRIDE of soft bars: ${t.soft.join('; ')}` : '',
      '\nThis places a real order on Robinhood. Continue?',
    ].join('\n')
    if (!confirm(lines)) return
    if (override && prompt('Type OVERRIDE to confirm you are overriding the desk rules for this trade:') !== 'OVERRIDE') return
    setBuying((b) => ({ ...b, [sym]: 'working' }))
    try {
      const r = await fetch('/api/fund/buy', { method: 'POST', headers: { 'Content-Type': 'application/json', 'x-admin-secret': secret }, body: JSON.stringify({ symbol: sym, override, requestId: crypto.randomUUID() }) })
      const j = (await r.json()) as BuyResult
      setBuying((b) => ({ ...b, [sym]: j }))
      if (j.ok) {
        const s = await fetch('/api/fund/state', { cache: 'no-store', headers: { 'x-admin-secret': secret } })
        if (s.ok) setState(await s.json())
      }
    } catch (e) { setBuying((b) => ({ ...b, [sym]: { error: 'network', message: e instanceof Error ? e.message : 'request failed' } })) }
  }

  const perfItems: PerfItem[] = [
    ...positions.map((p): PerfItem => ({ symbol: p.symbol, cgId: cg[p.symbol.toUpperCase()] ?? null, kind: 'held', entry: Number(p.avg_cost) > 0 ? Number(p.avg_cost) : null })),
    ...queue.map((t): PerfItem => ({ symbol: t.symbol, cgId: cg[t.symbol.toUpperCase()] ?? null, kind: 'queue', entry: null, status: t.status })),
  ]

  return (
    <div className="space-y-2">
      {openPos && (
        <HoldingChart symbol={openPos.symbol} cgId={cg[openPos.symbol.toUpperCase()] ?? null}
          entry={Number(openPos.avg_cost) > 0 ? Number(openPos.avg_cost) : null}
          stop={stopFor(openPos.symbol) != null ? Number(stopFor(openPos.symbol)) : null}
          others={perfItems.map((i) => ({ symbol: i.symbol, cgId: i.cgId }))}
          secret={secret}
          onClose={() => setOpen(null)} />
      )}

      {(stale || degraded) && (
        <div className="rounded-xl border border-amber-500 bg-amber-100 px-3 py-1.5 text-[12px] font-medium text-amber-900 dark:border-amber-400/60 dark:bg-amber-400/15 dark:text-amber-200">
          ⚠ {degraded ? 'Live refresh failing — numbers are from the last successful load. ' : ''}
          {stale ? `Data may be stale (holdings synced ${oldestSync.toFixed(0)}h ago${boardAge > 36 ? `, board ${boardAge.toFixed(0)}h old` : ''}).` : ''}
        </div>
      )}

      {/* PRICE FEED STATE (build request #14a). Loud when the prices on screen are older than three
          minutes: the failure this fixes was a feed that quietly froze while every number kept
          looking live. */}
      {pricesStale && (
        <div className="rounded-xl border border-rose-500 bg-rose-100 px-3 py-1.5 text-[12px] font-bold text-rose-900 dark:border-rose-400/60 dark:bg-rose-400/15 dark:text-rose-200">
          ⚠ PRICE FEED {priceMeta.at ? `STALE — last good ${priceStamp} (${Math.round((priceAgeMs ?? 0) / 60000)} min ago)` : 'UNAVAILABLE — no prices loaded yet'}
          {priceMeta.error ? ` · ${priceMeta.error}` : ''}. Every price below is from that moment, not from now.
        </div>
      )}
      {!pricesStale && priceMeta.missing.length > 0 && (
        <div className="rounded-xl border border-amber-400 bg-amber-50 px-3 py-1 text-[11px] text-amber-900 dark:border-amber-400/50 dark:bg-amber-400/10 dark:text-amber-200">
          No price for {priceMeta.missing.join(', ')} — shown as “…”, never as a zero.
        </div>
      )}

      {/* ── 1. HOLDINGS ── */}
      <Panel accent="rose" title="🔴 Holdings — Robinhood, live"
        right={<span className="flex items-center gap-2 text-[11px] text-neutral-500">
          {synced ? `synced ${denver(synced)}` : ''} · <span className={pricesStale ? 'font-bold text-rose-600 dark:text-rose-300' : ''}>prices as of {priceStamp ?? '—'}</span>
          <button type="button" onClick={toggleLoop} disabled={toggling || state.loop_enabled == null} title="24/7 desk loop"
            className={`rounded-md px-2 py-0.5 text-[10px] font-bold text-white ${state.loop_enabled === false ? 'bg-red-600' : 'bg-green-600'} disabled:opacity-50`}>
            {toggling ? '…' : state.loop_enabled == null ? 'LOOP ?' : state.loop_enabled ? '● LOOP ON' : '■ LOOP PAUSED'}
          </button>
        </span>}>
        {state.holdings === null ? (
          <span className="text-[13px] text-red-600">Holdings unreachable — fetch failed, not empty.</span>
        ) : positions.length === 0 ? (
          <span className="text-[13px] text-neutral-500">No open positions. Cash ${cash.toFixed(2)}.</span>
        ) : (
          <>
            <div className="mb-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl bg-neutral-50 px-3 py-2.5 dark:bg-white/5">
                <div className="text-[11px] uppercase tracking-wider text-neutral-500">Cash held</div>
                <div className="font-mono text-[28px] font-black leading-tight text-neutral-800 dark:text-neutral-100">{usd2(cash)}</div>
                <div className="text-[10px] text-neutral-500">{book > 0 ? `${((cash / book) * 100).toFixed(0)}% of book · floor 10%` : ''}</div>
              </div>
              <div className="rounded-xl bg-neutral-50 px-3 py-2.5 dark:bg-white/5">
                <div className="text-[11px] uppercase tracking-wider text-neutral-500">Account value</div>
                <div className="font-mono text-[28px] font-black leading-tight text-neutral-800 dark:text-neutral-100">{allPriced ? usd2(book) : '…'}</div>
                {allPriced && (() => {
                  // MARKET MOVE ONLY. Each position's value 24h ago = value / (1 + d1); cash is carried at its
                  // CURRENT level on both sides so a deposit cancels out and can never appear as a gain.
                  // Jacob 2026-09-11, on a $100 deposit that lifted the book $103: "that should never read as a gain".
                  const prev = positions.reduce((s, p) => { const d = live[p.symbol]?.d1; return s + (d == null ? val(p) : val(p) / (1 + d / 100)) }, 0) + cash
                  const chg = book - prev; const pct = prev > 0 ? (chg / prev) * 100 : 0
                  const today = new Date(Date.now() - 6 * 3600e3).toISOString().slice(0, 10)   // Denver date
                  const inToday = (capital.flows ?? []).filter((f) => f.date >= today)
                  const depToday = inToday.reduce((a, f) => a + (/deposit|transfer_in|in/i.test(f.kind) ? Number(f.amount) : -Number(f.amount)), 0)
                  return (
                    <>
                      <div className={`font-mono text-[13px] font-bold ${chg >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>
                        {chg >= 0 ? '\u25b2' : '\u25bc'} {usd2(Math.abs(chg))} ({pct >= 0 ? '+' : ''}{pct.toFixed(2)}%) <span className="font-normal text-neutral-500">market today</span>
                      </div>
                      {depToday !== 0 && (
                        <div className="mt-0.5 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] font-bold text-amber-900 dark:bg-amber-400/20 dark:text-amber-200">
                          {depToday > 0 ? '+' : '\u2212'}{usd2(Math.abs(depToday))} deposited today \u2014 YOUR money, not a gain
                        </div>
                      )}
                    </>
                  )
                })()}
                <div className="text-[10px] text-neutral-500">positions {allPriced ? usd2(posValue) : 'pricing…'} + cash · the headline number is size, not performance</div>
                {unpricedSyms.length > 0 && <div className="mt-0.5 text-[10px] font-bold text-red-600 dark:text-rose-300">⚠ no price for {unpricedSyms.join(', ')} — the total below excludes them, it is NOT your whole account</div>}
              </div>
              {/* BUILD REQUEST #15 (2) — TOTAL RETURN, the figure that should tie out to the Robinhood app:
                  open P&L on every position (live price − avg_cost) plus realized P&L from tax_events.
                  It is a DIFFERENT question from the challenge number beside it, and both are shown because
                  showing one and calling it "P&L" is what made the tab disagree with his phone. */}
              <div className="rounded-xl bg-neutral-50 px-3 py-2.5 dark:bg-white/5">
                <div className="text-[10px] uppercase tracking-wider text-neutral-500">Total return <span className="normal-case text-neutral-400">· matches Robinhood app</span></div>
                {!allPriced ? <div className="text-[12px] text-neutral-500">pricing…</div>
                : realized === null ? <div className="text-[12px] text-red-600 dark:text-rose-300">tax ledger unreachable — total return unknown, not zero</div>
                : (() => {
                    const priced = positions.filter((p) => srvPrice(p.symbol) != null && Number(p.avg_cost) > 0)
                    const noBasis = positions.filter((p) => !(Number(p.avg_cost) > 0)).map((p) => p.symbol)
                    const openPnl = priced.reduce((s, p) => s + (Number(p.qty) * (srvPrice(p.symbol) as number) - Number(p.qty) * Number(p.avg_cost)), 0)
                    const costIn = priced.reduce((s, p) => s + Number(p.qty) * Number(p.avg_cost), 0)
                    const totalRet = openPnl + realized.pnl
                    const pct = costIn > 0 ? (totalRet / costIn) * 100 : null
                    return (
                      <>
                        <div className={`font-mono text-[28px] font-black leading-tight ${totalRet >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>
                          {usd2(totalRet)}{deskBasis.length > 0 ? <span className="text-[16px]">*</span> : null}
                          {pct != null && <span className="text-[14px]"> ({totalRet >= 0 ? '+' : ''}{pct.toFixed(1)}%)</span>}
                        </div>
                        <div className="text-[10px] text-neutral-500">open {usd2(openPnl)} + realized {usd2(realized.pnl)} · vs cost {usd2(costIn)}</div>
                        {noBasis.length > 0 && <div className="text-[10px] font-bold text-amber-700 dark:text-amber-300">no cost basis for {noBasis.join(', ')} — excluded from this figure</div>}
                      </>
                    )
                  })()}
              </div>
              <div className="rounded-xl bg-neutral-50 px-3 py-2.5 dark:bg-white/5">
                <div className="text-[10px] uppercase tracking-wider text-neutral-500">Challenge P&L{capital.baseline ? ` · since ${new Date(capital.baseline.date + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}, excludes deposits` : ''}</div>
                {/* Build request #7: the ONLY headline P&L — deposit-adjusted. value − baseline − net flows since the baseline. */}
                {!capital.reachable ? <div className="text-[12px] text-red-600 dark:text-rose-300">capital_flows unreachable — unknown, not zero</div>
                : !capital.baseline ? <div className="text-[12px] text-amber-800 dark:text-amber-200">no baseline row in capital_flows</div>
                : allPriced ? (() => {
                    const capIn = capital.baseline.usd + capital.net_flows
                    const pnl = book - capIn
                    const pct = capIn > 0 ? (pnl / capIn) * 100 : 0
                    return (
                      <>
                        <div className={`font-mono text-[28px] font-black leading-tight ${pnl >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{usd2(pnl)} <span className="text-[14px]">({pnl >= 0 ? '+' : ''}{pct.toFixed(1)}%)</span></div>
                        <div className="text-[10px] text-neutral-500">capital in {usd2(capIn)} = baseline {usd2(capital.baseline.usd)} {capital.net_flows >= 0 ? '+' : '−'} {usd2(Math.abs(capital.net_flows))} deposits · deposit-adjusted</div>
                      </>
                    )
                  })()
                : <div className="text-[12px] text-neutral-500">pricing…</div>}
              </div>
            </div>

            {/* BUILD REQUEST #15 — the reconciliation line. The two P&L figures above answer different
                questions, so the gap between them is stated outright with the reason for it. */}
            {allPriced && realized !== null && capital.reachable && capital.baseline && (() => {
              const priced = positions.filter((p) => srvPrice(p.symbol) != null && Number(p.avg_cost) > 0)
              const totalRet = priced.reduce((s, p) => s + Number(p.qty) * ((srvPrice(p.symbol) as number) - Number(p.avg_cost)), 0) + realized.pnl
              const challenge = book - (capital.baseline.usd + capital.net_flows)
              const gap = totalRet - challenge
              return (
                <div className="mb-2 rounded-lg border border-neutral-200 px-2.5 py-1.5 text-[11px] leading-snug text-neutral-600 dark:border-white/10 dark:text-neutral-400">
                  <b>Reconciliation:</b> total return {usd2(totalRet)} − challenge P&L {usd2(challenge)} = <b className="font-mono">{usd2(gap)}</b>.
                  {' '}Total return measures every position against what it cost, over the whole life of the account; challenge P&L measures the account against{' '}
                  {usd2(capital.baseline.usd + capital.net_flows)} of capital put in since {new Date(capital.baseline.date + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}. The gap is the P&L that was already in the book at the baseline, plus anything the two treat differently.
                  {deskBasis.length > 0 && (
                    <div className="mt-0.5 text-amber-700 dark:text-amber-300">
                      * Cost basis for {deskBasis.join(', ')} is <b>desk-tracked, not broker-confirmed</b> — Robinhood reports no cost basis for these units (transferred in). Kraken export pending. Any figure marked * moves if that basis is wrong.
                    </div>
                  )}
                </div>
              )
            })()}

            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-[12px] tabular-nums">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-neutral-500">
                    <th className="py-1 pr-2">Asset</th><th className="pr-2 text-right">Price</th><th className="pr-2 text-right">24h</th><th className="pr-2 text-right">Qty</th>
                    <th className="pr-2 text-right">Entry</th><th className="pr-2 text-right">Value · weight</th><th className="pr-2 text-right">P&L vs entry</th><th className="pr-2 text-right">Stop</th><th className="text-right">Thesis</th>
                  </tr>
                </thead>
                <tbody>
                  {[...positions].sort((a, b) => val(b) - val(a)).map((p) => {
                    // ONE price for the row and the header (build request #15, last clause): the row used
                    // to price off the client feed while the tiles priced off the server, so the two could
                    // tell different stories about the same position.
                    const lv = live[p.symbol]; const now = srvPrice(p.symbol)
                    const value = now !== null ? Number(p.qty) * now : null
                    const entry = Number(p.avg_cost) > 0 ? Number(p.avg_cost) : null
                    const pnl = value !== null && entry ? value - Number(p.qty) * entry : null
                    const pct = now !== null && entry ? ((now - entry) / entry) * 100 : null
                    const stop = stopFor(p.symbol)
                    const weight = value !== null && book > 0 ? (value / book) * 100 : null
                    const th = thesisFor(p.symbol)
                    const role = ANCHOR.has(p.symbol) ? 'anchor' : 'sleeve'
                    return (
                      <>
                        <tr key={p.symbol} className="border-t border-neutral-100 dark:border-white/5">
                          <td className="py-1.5 pr-2">
                            <button type="button" onClick={() => setOpen(p.symbol)} className="text-left" title="1-year chart with entry and stop">
                              <span className="text-[15px] font-black text-rose-600 dark:text-rose-300">{p.symbol}</span>
                              <span className={`ml-1.5 rounded px-1 py-px text-[9px] font-bold uppercase tracking-wide ${role === 'anchor' ? 'bg-rose-100 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300' : 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200'}`}>{role}</span>
                            </button>
                          </td>
                          <td className="pr-2 text-right font-mono text-[13px] font-bold text-neutral-800 dark:text-neutral-100">{now !== null ? fmt(now) : '…'}</td>
                          <td className="pr-2 text-right"><Pct v={lv?.d1} /></td>
                          <td className="pr-2 text-right font-mono text-neutral-700 dark:text-neutral-300">{p.qty}</td>
                          <td className="pr-2 text-right font-mono text-neutral-700 dark:text-neutral-300">{entry ? fmt(entry) : 'n/a'}</td>
                          <td className="pr-2 text-right">
                            <span className="font-mono text-neutral-800 dark:text-neutral-100">{value !== null ? usd2(value) : '…'}</span>
                            {weight !== null && (
                              <span className="ml-1.5 inline-flex items-center gap-1 align-middle">
                                <span className="inline-block h-1.5 w-12 overflow-hidden rounded bg-neutral-100 dark:bg-white/10"><span className={`block h-full ${role === 'anchor' ? 'bg-rose-400' : 'bg-amber-400'}`} style={{ width: `${Math.min(100, weight)}%` }} /></span>
                                <span className="font-mono text-[10px] text-neutral-500">{weight.toFixed(0)}%</span>
                              </span>
                            )}
                          </td>
                          <td className="pr-2 text-right">
                            {pnl !== null && pct !== null ? (
                              <span className={`inline-block rounded-md px-1.5 py-px font-mono font-bold ${pnl >= 0 ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-400/15 dark:text-emerald-300' : 'bg-rose-50 text-rose-700 dark:bg-rose-400/15 dark:text-rose-300'}`}>{usd2(pnl)} · {pct >= 0 ? '+' : ''}{pct.toFixed(1)}%</span>
                            ) : <span className="text-neutral-400">—</span>}
                          </td>
                          {/* The broker's resting sell order is the only thing that proves a stop exists
                              (build request #14b). A level in desk_triggers with no order behind it is a
                              level somebody wrote down, and it is labelled as exactly that. */}
                          <td className="pr-2 text-right">
                            {(() => {
                              const bo = restingStop(p.symbol)
                              if (bo?.level != null) return (
                                <span className="font-mono text-amber-700 dark:text-amber-300" title={`order ${bo.order_id}`}>
                                  {fmt(Number(bo.level))}{now !== null && <span className="text-[10px] text-neutral-500"> ({(((Number(bo.level) - now) / now) * 100).toFixed(1)}%)</span>}
                                  <span className="ml-1 rounded bg-emerald-600 px-1 py-px text-[9px] font-bold text-white">ARMED</span>
                                </span>
                              )
                              if (!ordersKnown) return <span className="text-[10px] text-neutral-500">broker orders {orderRows === null ? 'unreachable' : `${ordersAgeH.toFixed(0)}h old`} — unknown</span>
                              if (stop !== null) return (
                                <span className="font-mono text-neutral-500">{fmt(Number(stop))}<span className="ml-1 rounded bg-amber-500 px-1 py-px text-[9px] font-bold text-white">WRITTEN, NOT ARMED</span></span>
                              )
                              return <span className="rounded bg-rose-600 px-1 py-px text-[10px] font-bold text-white">NO STOP</span>
                            })()}
                          </td>
                          <td className="text-right">
                            {th ? <button type="button" onClick={() => setThesisOpen((o) => ({ ...o, [p.symbol]: !o[p.symbol] }))} className="rounded-md bg-neutral-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-neutral-600 hover:bg-neutral-200 dark:bg-white/10 dark:text-neutral-300">{thesisOpen[p.symbol] ? 'hide' : th.status}</button>
                              : <span className="text-[10px] text-neutral-400">none</span>}
                          </td>
                        </tr>
                        {th && thesisOpen[p.symbol] && (
                          <tr key={`${p.symbol}-th`}>
                            <td colSpan={9} className="pb-1.5 text-[12px] leading-snug text-neutral-600 dark:text-neutral-400">{th.thesis}{th.gate && <span className="text-teal-700 dark:text-teal-300"> · gate → {th.gate}</span>}</td>
                          </tr>
                        )}
                      </>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {/* Constitution v4/v4.1 structure strip: anchor BTC+SOL ≥55% · sleeve ≤45% across min(7, floor(book/$150)) slots (≤10% each, $50 min) · cash floor 10% · anchor tilt */}
            {allPriced && book > 0 && (() => {
              const anchor = positions.filter((p) => ANCHOR.has(p.symbol)).reduce((s, p) => s + val(p), 0)
              const sleeve = positions.filter((p) => !ANCHOR.has(p.symbol))
              const sleeveV = sleeve.reduce((s, p) => s + val(p), 0)
              const aPct = (anchor / book) * 100, sPct = (sleeveV / book) * 100, cPct = (cash / book) * 100
              const slots = Math.min(7, Math.floor(book / 150))              // v4.1 §2 slot formula
              const minPos = book >= 500 ? 50 : null                          // minimum sleeve position once the book is ≥ $500
              const fat = sleeve.filter((p) => val(p) / book > 0.10).map((p) => p.symbol)
              const solD30 = live['SOL']?.d30 ?? null, btcD30 = live['BTC']?.d30 ?? null
              const tilt = solD30 != null && btcD30 != null ? (solD30 > btcD30 ? '60/40 SOL/BTC' : '50/50') : null   // v4.1 §4 anchor tilt on the 30d SOL/BTC ratio
              const flags = [
                aPct < 55 ? `anchor ${aPct.toFixed(0)}% < 55%` : '',
                cPct < 10 ? `cash ${cPct.toFixed(0)}% < 10% floor — no new sleeve entries` : '',
                sleeve.length > slots ? `sleeve ${sleeve.length} names > ${slots} slots` : '',
                fat.length ? `over 10%: ${fat.join(', ')}` : '',
              ].filter(Boolean)
              return (
                <div className="mt-2">
                  <div className="flex h-2 w-full overflow-hidden rounded bg-neutral-100 dark:bg-white/10" title="anchor · sleeve · cash">
                    <div className="bg-rose-400/80" style={{ width: `${aPct}%` }} />
                    <div className="bg-amber-400/80" style={{ width: `${sPct}%` }} />
                    <div className="bg-neutral-400/60" style={{ width: `${cPct}%` }} />
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-neutral-600 dark:text-neutral-400">
                    <span>v4.1 structure:</span>
                    <span><b className="text-rose-600 dark:text-rose-300">anchor</b> BTC/SOL <span className="font-mono">{aPct.toFixed(0)}%</span> <span className="text-neutral-400">(≥55%{tilt ? ` · basket ${tilt}` : ''})</span></span>
                    <span><b className="text-amber-700 dark:text-amber-300">sleeve</b> <span className="font-mono">{sPct.toFixed(0)}%</span> · slots <span className="font-mono">{sleeve.length}/{slots}</span> <span className="text-neutral-400">(≤45%, ≤10% each{minPos ? `, $${minPos} min` : ''})</span></span>
                    <span><b>cash</b> <span className="font-mono">{cPct.toFixed(0)}%</span> <span className="text-neutral-400">(floor 10%)</span></span>
                    <span className="text-neutral-400">holdings {positions.length}/10</span>
                  </div>
                  {flags.length > 0 && <div className="mt-0.5 text-[11px] font-medium text-amber-800 dark:text-amber-200">⚠ {flags.join(' · ')}</div>}
                </div>
              )
            })()}
          </>
        )}
      </Panel>

      {/* ── 2. NARRATIVE LEADERBOARD — TEN SEATS, A PICK IN EVERY ONE ────────────────────────────────
          ORDER (Jacob 2026-09-22): "i want robinhood first clickable tabs and the next picks and
          thesis and hwy". So the picks, the thesis and the reasoning sit directly under holdings,
          ABOVE the four-column buy board. The board is the terse version of the same names; this is
          the one that says WHY. Do not reorder these two again without an instruction.
          Jacob 2026-09-15: "why is the narrative leaderboard not working and listed 1-10 / you need to
          have a pick for every spot verified and would be our next buy if we chose that narrative".

          What was wrong. Build request #19 shipped the sector table (now collapsed at the foot of this
          panel) and it does work — 12 sectors off desk_theses.sector, ranked by median 7d. But five of
          those twelve resolved to "none verified", i.e. a seat on the board with no name in it, and
          "best verified" was really just the top buy_rank rather than anything that had been checked.
          A second, older reader in the research-brief panel read fund_research.content.narratives, a
          key no producer has EVER written — every row in that table carries only headline / verified /
          source / implications — so it rendered nothing and said nothing about it. That reader is gone.

          What this is. desk_narratives: exactly ten rows, each with ONE Robinhood-listed pick, the level
          we would buy it at, and a VERDICT stating what was actually checked and on what date. Ordered
          by EVIDENCE that money is already moving toward the coin, not by momentum — in a week where
          every sector is red, ranking on median 7d ranks "least down", which is not a reason to buy.
          The 7d / 30d / exposure figures are computed server-side off the SAME radar scan and price
          chain as the sector table, so the two can never disagree.

          A seat we could not verify says UNVERIFIED on its face. It is never allowed to read as one we did. */}
      {(() => {
        const all = [...(state.narratives ?? [])]
        const rows = narrOrder === 'proof'
          ? all.sort((a, b) => a.rank - b.rank)
          // null `turning` means it could not be computed; it sorts LAST rather than first.
          : all.sort((a, b) => (a.turning ?? 99) - (b.turning ?? 99))
        const bench = state.narratives_benchmark ?? null
        const daysTo = (d: string | null) => {
          if (!d) return null
          const ms = new Date(d + 'T00:00:00Z').getTime() - Date.now()
          return Math.ceil(ms / 86_400_000)
        }
        const pctCell = (v: number | null) => v == null
          ? <span className="text-neutral-400">—</span>
          : <span className={`font-mono font-bold ${v >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</span>
        // Verdict colours: green = we followed the money and it reaches a holder; amber = real but
        // conditional, deliberately throttled, or too small to matter; grey = supply only, nothing
        // earned; red = we could not confirm it.
        const chip = (v: string) =>
          /VERIFIED-MATERIAL/.test(v) ? 'bg-green-100 text-green-800 dark:bg-emerald-400/15 dark:text-emerald-200'
          : /UNVERIFIED|NO-MECHANISM/.test(v) ? 'bg-red-100 text-red-700 dark:bg-rose-400/15 dark:text-rose-200'
          : /SUPPLY-ONLY/.test(v) ? 'bg-neutral-200 text-neutral-700 dark:bg-white/10 dark:text-neutral-300'
          : 'bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-200'
        return (
          <Panel accent="cyan" title="🏁 Narrative leaderboard — 1 to 10"
            right={
              <span className="flex items-center gap-1 text-[11px] text-neutral-500">
                <button type="button" onClick={() => setNarrOrder('proof')}
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${narrOrder === 'proof' ? 'bg-cyan-600 text-white dark:bg-cyan-300 dark:text-neutral-900' : 'bg-neutral-100 text-neutral-500 dark:bg-white/10 dark:text-neutral-400'}`}>
                  Most real
                </button>
                <button type="button" onClick={() => setNarrOrder('turning')}
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${narrOrder === 'turning' ? 'bg-cyan-600 text-white dark:bg-cyan-300 dark:text-neutral-900' : 'bg-neutral-100 text-neutral-500 dark:bg-white/10 dark:text-neutral-400'}`}>
                  Turning first
                </button>
                <span className="ml-1">radar {state.radar?.[0]?.scan_date ?? '—'}</span>
              </span>
            }>
            {state.narratives === undefined ? (
              // FIRST PAINT. The server component does not query desk_narratives, so on the very first
              // render this field is absent and the 60s client refresh has not landed yet. "Not asked
              // yet" is not "asked and failed" — printing the red error here was the same defect this
              // whole board exists to kill, caught on the live page 2026-09-15 minutes after shipping.
              <span className="text-[13px] text-neutral-500">Loading the ten seats…</span>
            ) : state.narratives === null ? (
              <span className="text-[13px] text-red-600">
                Narrative table unreachable — the fetch failed. This is not an empty board.
                {state.narratives_error ? ` (${state.narratives_error})` : ''}
              </span>
            ) : rows.length === 0 ? (
              <span className="text-[13px] text-amber-800 dark:text-amber-200">desk_narratives is empty — ten empty seats, not ten passes.</span>
            ) : (
              <>
                <div className="divide-y divide-neutral-100 dark:divide-white/5">
                  {rows.map((n) => {
                    const price = srvPrice(n.pick)
                    const held = positions.some((p) => p.symbol === n.pick)
                    const thin = n.scanned < Math.min(2, n.universe)
                    return (
                      <div key={n.rank} className="py-2">
                        <div className="flex items-baseline gap-2">
                          <span className="w-5 shrink-0 text-right text-[15px] font-black tabular-nums text-neutral-400 dark:text-neutral-500">
                            {narrOrder === 'proof' ? n.rank : (n.turning ?? '–')}
                          </span>
                          <span className="flex-1 text-[13px] font-bold leading-snug text-neutral-800 dark:text-neutral-100">{n.narrative}</span>
                          <span className={`shrink-0 rounded px-1 text-[9px] font-bold uppercase tracking-wide ${chip(n.verdict)}`}>{n.verdict}</span>
                        </div>

                        {/* The buy line: the one name, its live price, and where we would buy it. */}
                        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 pl-7">
                          <span className="text-[10px] uppercase tracking-wider text-neutral-500">buy</span>
                          <span className="text-[15px] font-black text-amber-600 dark:text-amber-300">{n.pick}</span>
                          <span className="font-mono text-[13px] font-bold text-neutral-800 dark:text-neutral-100">{price != null ? bfmt(price) : '…'}</span>
                          {held && <span className="rounded bg-neutral-100 px-1 text-[9px] uppercase text-neutral-600 dark:bg-white/10 dark:text-neutral-300">held</span>}
                          <span className="text-[11px] text-neutral-400">7d {n.d7 == null ? '—' : `${n.d7 >= 0 ? '+' : ''}${n.d7.toFixed(1)}%`} · 30d {n.d30 == null ? '—' : `${n.d30 >= 0 ? '+' : ''}${n.d30.toFixed(1)}%`}</span>
                          <span className="text-[11px] text-neutral-400">ours {n.exposure_usd > 0 ? `${fmt(n.exposure_usd)}${n.exposure_pct != null ? ` (${n.exposure_pct.toFixed(0)}%)` : ''}` : '0'}</span>
                          {n.verified_on && <span className="text-[10px] text-neutral-400">checked {n.verified_on.slice(5)}</span>}
                        </div>

                        {/* THE ROTATION LINE — is this one being bought first, and is it the whole group
                            or one name? vs BTC, because in an all-red week a raw percentage says nothing. */}
                        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-1 pl-7">
                          <span className="text-[10px] uppercase tracking-wider text-neutral-500">vs btc 7d</span>
                          {n.rs7 == null
                            ? <span className="text-[11px] text-neutral-400">not computable</span>
                            : <span className={`font-mono text-[12px] font-bold ${n.rs7 >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{n.rs7 >= 0 ? '+' : ''}{n.rs7.toFixed(1)}%</span>}
                          <span className="text-[11px] text-neutral-400">
                            breadth {n.breadth == null ? '—' : `${n.breadth}/${n.breadth_of}`} beating BTC
                          </span>
                          {n.turnover_x != null && <span className="text-[11px] text-neutral-400">turnover {n.turnover_x.toFixed(1)}x the scan</span>}
                          <span className="text-[10px] text-neutral-400">
                            {narrOrder === 'proof'
                              ? `turning first: ${n.turning ?? '–'} of ${rows.length}`
                              : `most real: ${n.rank} of ${rows.length}`}
                          </span>
                        </div>

                        <p className="mt-1 pl-7 text-[12px] leading-relaxed text-neutral-700 dark:text-neutral-300">{n.plain}</p>
                        {n.entry && (
                          <p className="mt-1 pl-7 text-[12px] leading-relaxed">
                            <span className="text-[10px] uppercase tracking-wider text-neutral-500">where we would buy it </span>
                            <span className="text-neutral-800 dark:text-neutral-100">{n.entry}</span>
                          </p>
                        )}
                        {n.catalyst && (() => {
                          const dd = daysTo(n.catalyst_on)
                          const soon = dd != null && dd >= 0 && dd <= 30
                          return (
                            <p className={`mt-1 pl-7 text-[12px] leading-relaxed ${soon ? 'font-medium text-amber-800 dark:text-amber-200' : ''}`}>
                              <span className="text-[10px] uppercase tracking-wider text-neutral-500">what is coming </span>
                              {n.catalyst_on && <span className="mr-1 rounded bg-amber-500 px-1 text-[10px] font-black text-white">{n.catalyst_on.slice(5)}{dd != null && dd >= 0 ? ` · ${dd}d` : ''}</span>}
                              {!n.catalyst_on && n.catalyst_kind && <span className="mr-1 rounded bg-neutral-200 px-1 text-[9px] font-bold uppercase text-neutral-600 dark:bg-white/10 dark:text-neutral-300">{n.catalyst_kind}</span>}
                              <span className={soon ? '' : 'text-neutral-700 dark:text-neutral-300'}>{n.catalyst}</span>
                            </p>
                          )
                        })()}
                        {thin && <p className="mt-0.5 pl-7 text-[11px] text-amber-700 dark:text-amber-300">Only {n.scanned} of {n.universe} names in this narrative are in today&apos;s scan — the 7d and 30d figures above are thin, not wrong.</p>}

                        <details className="mt-1 pl-7">
                          <summary className="cursor-pointer text-[11px] uppercase tracking-wider text-neutral-500">The evidence, and the case against</summary>
                          <div className="mt-1 space-y-1 text-[12px] leading-relaxed">
                            <p><span className="font-bold text-cyan-700 dark:text-cyan-200">Evidence:</span> <span className="text-neutral-700 dark:text-neutral-300">{n.evidence}</span></p>
                            <p><span className="font-bold text-red-600 dark:text-rose-300">Against it:</span> <span className="text-neutral-700 dark:text-neutral-300">{n.against_it}</span></p>
                            <p><span className="font-bold text-neutral-600 dark:text-neutral-400">Why this name:</span> <span className="text-neutral-700 dark:text-neutral-300">{n.pick_why}{n.runner_up && n.runner_up !== 'none' ? ` Runner-up: ${n.runner_up}.` : ''}</span></p>
                            <p><span className="font-bold text-neutral-600 dark:text-neutral-400">What was checked:</span> <span className="text-neutral-700 dark:text-neutral-300">{n.checked}</span></p>
                            <p><span className="font-bold text-neutral-600 dark:text-neutral-400">Coins due to be released:</span> <span className="text-neutral-700 dark:text-neutral-300">{n.unlock_note || 'not recorded'}</span></p>
                            <p className="text-[11px] text-neutral-500">Names in this narrative: {(n.syms ?? []).join(', ') || '—'}{n.held.length ? ` · we hold ${n.held.join(', ')}` : ''}</p>
                            <p className="text-[11px] text-neutral-500">Sources: {n.sources}</p>
                          </div>
                        </details>
                      </div>
                    )
                  })}
                </div>
                <div className="mt-2 text-[11px] leading-relaxed text-neutral-500">
                  {narrOrder === 'proof'
                    ? 'MOST REAL: ranked on how much proof there is that money is already moving toward the coin, not on how far it has run. This is the order that decides what we own.'
                    : `TURNING FIRST: ranked on 7-day strength against BTC${bench?.btc_d7 != null ? ` (BTC ${bench.btc_d7 >= 0 ? '+' : ''}${bench.btc_d7.toFixed(1)}% this week)` : ''}, then on how many names in the group beat it. This measures what has ALREADY started being bought. It is not a forecast, and the desk's own breakout record is 30 signals at −5.0% average, so this order on its own loses money.`}
                  Green means we followed the money and it reaches a holder. Amber means real but conditional, turned down, or
                  too small to matter. Grey means supply only, with nothing earned. Red means we could not confirm it — and a
                  pick we could not confirm never counts as one we did. Every pick is Robinhood-listed. A seat is a candidate,
                  not an order: the entry still needs the tested signal and the cash to fill it.
                  {rows.length < 10 ? ` Only ${rows.length} of 10 seats are filled.` : ''}
                </div>

                {/* #19's sector momentum table, kept and collapsed. It answers a different question —
                    where is the tape moving and where are we thin — and it shares this panel's radar
                    scan and price chain, so the numbers always agree. */}
                <details className="mt-2 border-t border-neutral-100 pt-2 dark:border-white/5">
                  <summary className="cursor-pointer text-[11px] uppercase tracking-wider text-neutral-500">Sector momentum — where the tape is moving, and where we hold nothing</summary>
                  {state.sectors === undefined ? (
                    <span className="text-[13px] text-neutral-500">Loading…</span>
                  ) : state.theses === null || state.sectors === null ? (
                    <span className="text-[13px] text-red-600">Sector data unreachable — fetch failed, not empty.</span>
                  ) : state.sectors.length === 0 ? (
                    <span className="text-[13px] text-amber-800 dark:text-amber-200">No thesis row carries a sector yet — the desk tags sectors in desk_theses.</span>
                  ) : (
                    <div className="mt-1 overflow-x-auto">
                      <table className="w-full text-[13px] tabular-nums">
                        <thead><tr className="text-left text-[10px] uppercase tracking-wider text-neutral-500">
                          <th className="py-1 pr-2">Sector</th><th className="pr-2 text-right">7d</th><th className="pr-2 text-right">30d</th>
                          <th className="pr-2 text-right">Ours</th><th className="text-left">Top ranked</th>
                        </tr></thead>
                        <tbody>
                          {(state.sectors ?? []).map((r, i) => (
                            <tr key={r.sector} title={`${r.names.join(', ')} · ${r.scanned}/${r.names.length} in the scan${r.held.length ? ` · held: ${r.held.join(', ')}` : ''}`}
                              className={`border-t border-neutral-100 dark:border-white/5 ${r.gap ? 'bg-amber-50 dark:bg-amber-400/10' : ''}`}>
                              <td className="py-1.5 pr-2">
                                <span className="mr-1 text-[11px] text-neutral-400">{i + 1}</span>
                                <span className="font-bold text-neutral-800 dark:text-neutral-100">{r.sector}</span>
                                {r.gap && <span className="ml-1 rounded bg-amber-500 px-1 text-[10px] font-black text-white" title="top-3 momentum, zero exposure — research it, do not auto-buy">GAP</span>}
                                {r.scanned === 0 && <span className="ml-1 text-[10px] text-neutral-400" title="no name in this sector has a radar row (not Robinhood-listed or not scanned)">no scan</span>}
                              </td>
                              <td className="pr-2 text-right">{pctCell(r.d7)}</td>
                              <td className="pr-2 text-right">{pctCell(r.d30)}</td>
                              <td className="pr-2 text-right font-mono">
                                {r.exposure_usd > 0
                                  ? <span className="text-neutral-800 dark:text-neutral-100">{fmt(r.exposure_usd)}<span className="ml-1 text-[11px] text-neutral-500">{r.exposure_pct != null ? `${r.exposure_pct.toFixed(0)}%` : ''}</span></span>
                                  : <span className="text-neutral-400">0</span>}
                              </td>
                              <td className="text-left">
                                {r.best_verified
                                  ? <span className="font-bold text-neutral-800 dark:text-neutral-100">{r.best_verified}</span>
                                  : <span className="text-neutral-400">nothing ranked</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div className="mt-1 text-[11px] text-neutral-500">
                        Ranked by the sector&apos;s median 7d move. A GAP means the money is moving somewhere we hold nothing — research
                        instruction, not a buy. &quot;Top ranked&quot; is the desk&apos;s own buy_rank, which is a decision, not a verification;
                        the verified picks are the ten seats above.
                        {state.unsectored_usd ? ` ${fmt(state.unsectored_usd)} held in names with no sector tag.` : ''}
                      </div>
                    </div>
                  )}
                </details>
              </>
            )}
          </Panel>
        )
      })()}

      {/* ── 3. BUY BOARD ────────────────────────────────────────────────────────────────────────────
          Build request #16, display spec replaced by #18 (Jacob's final): FOUR columns and nothing
          else — symbol, live, entry, %. Rows in buy_rank order, at most ten, never by updated_at.
          ENTRY means two different things on purpose: for a name we hold it is OUR COST BASIS, so the
          % answers "are we up or down on it"; for a name we do not hold it is the written entry level,
          so the % answers "how far is the price from where we said we would buy". Both are the same
          question — is this worth money right now — which is why they share a column.
          The armed/not-armed state stays in the API payload for the desk's reconciliation (#18's own
          note) but is off the face: order status is in the Robinhood app, and this board is about
          what to buy, not about plumbing. The entry note moves to the row tooltip. */}
      {(() => {
        const board = [...(state.theses ?? [])].filter((t) => t.buy_rank != null).sort((a, b) => (a.buy_rank as number) - (b.buy_rank as number)).slice(0, 10)
        return (
          <Panel accent="amber" title="🎯 Buy board"
            right={<span className="text-[11px] text-neutral-500">desk rank · prices {priceStamp ?? '—'}</span>}>
            {state.theses === null ? (
              <span className="text-[13px] text-red-600">Theses unreachable — fetch failed, not empty.</span>
            ) : board.length === 0 ? (
              <span className="text-[13px] text-amber-800 dark:text-amber-200">No name carries a buy_rank — the desk has not ranked the board this session.</span>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px] tabular-nums">
                  <thead><tr className="text-left text-[10px] uppercase tracking-wider text-neutral-500">
                    <th className="py-1 pr-2">Symbol</th><th className="pr-2 text-right">Live</th>
                    <th className="pr-2 text-right">Entry</th><th className="text-right">%</th>
                  </tr></thead>
                  <tbody>
                    {board.map((t) => {
                      const price = srvPrice(t.symbol)
                      const pos = positions.find((p) => p.symbol === t.symbol) ?? null
                      const holdingBasis = pos && Number(pos.avg_cost) > 0 ? Number(pos.avg_cost) : null
                      const isHeld = holdingBasis != null
                      // Held: live vs our cost. Unheld: how far the price is from the written level,
                      // signed so that "at or below where we said we would buy" is the positive case.
                      const entry = isHeld ? holdingBasis : (t.entry_level != null ? Number(t.entry_level) : null)
                      const pct = price != null && entry != null && entry > 0 && price > 0
                        ? (isHeld ? ((price - entry) / entry) * 100 : ((entry - price) / price) * 100)
                        : null
                      const good = pct != null && pct >= 0
                      const near = !isHeld && pct != null && Math.abs(pct) <= 3
                      const tip = [t.entry_note, isHeld ? 'entry = our cost basis' : 'entry = the written level'].filter(Boolean).join(' · ')
                      return (
                        <tr key={t.symbol} title={tip} className={`border-t border-neutral-100 dark:border-white/5 ${near ? 'bg-emerald-50 dark:bg-emerald-400/10' : ''}`}>
                          <td className="py-1.5 pr-2">
                            <span className="text-[15px] font-black text-neutral-800 dark:text-neutral-100">{t.symbol}</span>
                            {t.buy_rank === 1 && <span className="ml-1 text-amber-500" title="pole seat">★</span>}
                          </td>
                          <td className="pr-2 text-right font-mono font-bold text-neutral-800 dark:text-neutral-100">{price != null ? bfmt(price) : '…'}</td>
                          <td className="pr-2 text-right font-mono text-neutral-700 dark:text-neutral-300">{entry != null ? bfmt(entry) : <span className="text-neutral-400">—</span>}</td>
                          <td className="text-right">
                            {pct != null
                              ? <span className={`font-mono font-bold ${good ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{pct >= 0 ? '+' : ''}{pct.toFixed(1)}%</span>
                              : <span className="text-neutral-400">—</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <div className="mt-1 text-[11px] text-neutral-500">
                  Held names show our cost basis and whether we are up on it. The rest show the written entry level
                  and how far the price is from it — green means at or below it. Tap and hold a row for the note.
                </div>
              </div>
            )}
          </Panel>
        )
      })()}

      {/* ── 4. THE FULL WATCH LIST — collapsed under the buy board (build request #16) ────────────── */}
      <details className="rounded-xl border border-neutral-200 px-1 py-1 dark:border-white/10" open={showWatch} onToggle={(e) => setShowWatch((e.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer px-2 py-1 text-[12px] font-bold uppercase tracking-wider text-neutral-500">
          Full watch list — {queue.length} name{queue.length === 1 ? '' : 's'} with timing grades and tap-to-buy
        </summary>
      <Panel accent="amber" title="★ Up next — in line to add"
        right={<span className="text-[11px] text-neutral-500">POLE → WATCH → VERIFYING · numbers live, never from thesis text · holdings excluded</span>}>
        {state.theses === null ? (
          <span className="text-[13px] text-red-600">Theses unreachable — fetch failed, not empty.</span>
        ) : queue.length === 0 ? (
          <span className="text-[13px] text-amber-800 dark:text-amber-200">Nothing in line{heldPole ? ` — desk_theses names ${heldPole.symbol} as POLE but it is held; desk must promote a candidate` : ''}.</span>
        ) : (
          <div className="divide-y divide-neutral-100 dark:divide-white/5">
            {heldPole && <div className="pb-1 text-[11px] text-amber-800 dark:text-amber-200">desk_theses POLE row is {heldPole.symbol}, which is held — suppressed; the first name below is not a pole until the desk promotes it.</div>}
            {/* Jacob 2026-09-11: "i only want things on that list that are a c+ or higher". D and F are
                collapsed, not deleted. A name that has not been checked yet, or that could not be graded
                for want of a live price ('?'), still shows — hiding those would hide the good ones, which
                is exactly what happened when a rate limit turned five B-scoring names into Fs. */}
            {queueRanked.map((t, rank) => {
              const lv = live[t.symbol]; const r = radarFor(t.symbol); const fl = flowFor(t.symbol)
              const lines = trig(t.symbol, ['bid', 'deep_rung', 'entry', 'dump', 'reclaim'])
              const tm = timing[t.symbol]; const br = buying[t.symbol]
              const T = tm && tm !== 'loading' && !('error' in tm) ? tm : null
              const belowC = T != null && (T.grade === 'D' || T.grade === 'F')   // '?' and errors stay visible on purpose
              if (belowC && !showBelowC) return null
              return (
                <div key={t.symbol} className="py-2">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px]">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-neutral-800 font-mono text-[11px] font-bold text-white dark:bg-white dark:text-black">{rank + 1}</span>
                    <span className="text-[16px] font-black text-neutral-800 dark:text-neutral-100">{t.symbol}</span>
                    <span className={`rounded px-1.5 py-px text-[9px] font-bold uppercase tracking-wide ${STATUS[t.status] ?? 'bg-neutral-100 text-neutral-600'}`}>{t.status}</span>
                    {venueFor(t.symbol) === 'kraken' && <span className="rounded bg-amber-100 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-400/15 dark:text-amber-200" title="Not on Robinhood. Buyable on Kraken by hand. The grade is real; the buy button is not, because this account cannot place the order.">kraken · buy by hand</span>}
                    {venueFor(t.symbol) === 'none' && <span className="rounded bg-rose-100 px-1.5 py-px text-[9px] font-bold uppercase tracking-wide text-rose-700 dark:bg-rose-400/15 dark:text-rose-200" title="Not on Robinhood or Kraken. On the list to be watched, not bought anywhere we trade.">no venue · watch only</span>}
                    <span className="font-mono text-[14px] font-bold tabular-nums text-neutral-800 dark:text-neutral-100">{lv ? fmt(lv.price) : '…'}</span>
                    <span className="text-neutral-500">24h <Pct v={lv?.d1} /> · 7d <Pct v={lv?.d7} /> · 30d <Pct v={lv?.d30} /></span>
                    {lv?.vol != null && <span className="text-neutral-500">vol {big(lv.vol)}</span>}
                    {lines.map((l, i) => (
                      <span key={i} className="text-teal-700 dark:text-teal-300">{l.kind} <b className="font-mono">{fmt(Number(l.level))}</b>{lv && <span className="text-neutral-500"> ({(((Number(l.level) - lv.price) / lv.price) * 100).toFixed(1)}% away)</span>}</span>
                    ))}
                    {fl && fl.flow_score != null && <span className={`rounded px-1.5 py-px text-[10px] font-bold ${fl.stage === 'PRE-EARLY' || fl.stage === 'RISING' ? 'bg-sky-100 text-sky-800 dark:bg-sky-400/20 dark:text-sky-200' : 'bg-neutral-100 text-neutral-600 dark:bg-white/10 dark:text-neutral-300'}`} title={`flow radar ${fl.scan_date}`}>flow {fl.flow_score >= 0 ? '+' : ''}{Number(fl.flow_score).toFixed(0)} · {fl.stage}</span>}
                    {r && <span className="text-[11px] text-neutral-500">radar {r.stage} · {Number(r.score).toFixed(0)} · turn {Number(r.turnover).toFixed(0)}%</span>}
                    <span className="ml-auto flex items-center gap-1.5">
                      <button type="button" onClick={() => checkTiming(t.symbol)} disabled={tm === 'loading'}
                        className="rounded-lg bg-neutral-800 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-neutral-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-neutral-200">
                        {tm === 'loading' ? 'checking…' : T ? `Timing ${T.grade} · hide` : 'Timing A–F'}
                      </button>
                      {T && T.rh_configured && T.buyable && (
                        <button type="button" onClick={() => buy(t.symbol, T, false)} disabled={br === 'working'}
                          className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[11px] font-bold text-white hover:bg-emerald-500 disabled:opacity-50">
                          {br === 'working' ? 'placing…' : `Buy $${T.size.usd.toFixed(0)}`}
                        </button>
                      )}
                      {T && T.rh_configured && !T.buyable && T.overridable && (
                        <button type="button" onClick={() => buy(t.symbol, T, true)} disabled={br === 'working'}
                          className="rounded-lg border border-amber-500 px-2.5 py-1 text-[11px] font-bold text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-400/10">
                          {br === 'working' ? 'placing…' : `Override · buy $${T.size.usd.toFixed(0)}`}
                        </button>
                      )}
                      {T && !T.rh_configured && (
                        <a href={`https://robinhood.com/crypto/${t.symbol}`} target="_blank" rel="noreferrer"
                          className="rounded-lg border border-emerald-600 px-2.5 py-1 text-[11px] font-bold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-400/10" title="Robinhood API keys are not set in Vercel — opens the app instead">
                          Open in Robinhood ↗
                        </a>
                      )}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[12px] leading-snug text-neutral-600 dark:text-neutral-400">{t.thesis}{t.gate && <span className="text-teal-700 dark:text-teal-300"> · gate → {t.gate}</span>}</div>

                  {tm && tm !== 'loading' && 'error' in tm && <div className="mt-1 text-[12px] text-red-600 dark:text-rose-300">Timing check failed: {tm.error}</div>}
                  {T?.tapeError && T.hi20 === null && (
                    <div className="mt-1 rounded-lg border border-rose-400/50 bg-rose-500/10 px-2 py-1 text-[12px] leading-snug text-rose-700 dark:text-rose-300">
                      <b>Tape unread — grade is not trustworthy.</b> {T.tapeError}. Without the
                      20-day high the RUNNING extension law cannot be checked, so the desk refuses
                      the entry rather than clearing it on data it does not have. Re-run the check.
                    </div>
                  )}
                  {T?.tapeError && T.hi20 !== null && (
                    <div className="mt-1 rounded-lg border border-amber-400/50 bg-amber-400/10 px-2 py-1 text-[12px] leading-snug text-amber-700 dark:text-amber-300">
                      <b>Volume unconfirmed.</b> {T.tapeError}. The 20-day high came from the
                      stored daily series, so the RUNNING law was still checked — only the
                      volume-vs-average test is missing from this grade.
                    </div>
                  )}
                  {T && (
                    <div className="mt-1.5 rounded-xl border border-neutral-200 bg-neutral-50 p-2.5 dark:border-white/10 dark:bg-white/5">
                      <div className="flex flex-wrap items-center gap-3">
                        <span className={`flex h-12 w-12 items-center justify-center rounded-xl text-[26px] font-black ${GRADE[T.grade]}`}>{T.grade}</span>
                        <div className="text-[12px] leading-snug">
                          <div className="font-bold text-neutral-800 dark:text-neutral-100">Timing {T.score}/100 · {T.hard.length ? 'BARRED by law' : T.venue === 'kraken' ? 'clear on the chart — Kraken, buy by hand' : T.venue === 'none' ? 'no venue — watch only' : T.buyable ? 'clear to buy' : 'soft bars — override only'}</div>
                          <div className="text-neutral-500">as of {denver(T.at)} · price <b className="font-mono text-neutral-700 dark:text-neutral-200">{fmt(T.price)}</b> · 24h volume <b className="font-mono text-neutral-700 dark:text-neutral-200">{T.vol24h != null ? big(T.vol24h) : '—'}</b>{T.volX != null && <span> ({T.volX.toFixed(1)}× its 20d avg)</span>}</div>
                          <div className="text-neutral-500">24h <Pct v={T.d1} /> · 7d <Pct v={T.d7} /> · 30d <Pct v={T.d30} /> · vs 20d high <Pct v={T.extPct} /> · vs BTC 7d <Pct v={T.rs7VsBtc} /></div>
                        </div>
                        <div className="ml-auto text-right text-[12px]">
                          <div className="text-neutral-500">ruled size</div>
                          <div className="font-mono text-[15px] font-bold text-neutral-800 dark:text-neutral-100">${T.size.usd.toFixed(2)} <span className="text-[11px] font-normal text-neutral-500">({T.size.pctBook.toFixed(1)}% of ${T.book.toFixed(0)}{T.size.halfSize ? ', half-size' : ''})</span></div>
                          <div className="text-neutral-500">stop at fill <b className="font-mono text-amber-700 dark:text-amber-300">{fmt(T.stop.price)}</b> ({T.stop.pct.toFixed(0)}%)</div>
                        </div>
                      </div>
                      <div className="mt-1.5 grid gap-x-4 gap-y-0.5 text-[11px] sm:grid-cols-2">
                        {T.hard.map((x, i) => <div key={`h${i}`} className="text-rose-700 dark:text-rose-300">⛔ {x}</div>)}
                        {T.plus.map((x, i) => <div key={`p${i}`} className="text-emerald-700 dark:text-emerald-300">{x}</div>)}
                        {T.soft.map((x, i) => <div key={`s${i}`} className="text-amber-800 dark:text-amber-200">{x}</div>)}
                        <div className="text-neutral-500">slots {T.sleeveCount}/{T.slots} · entries this week {T.weeklyEntries}/2 · cash ${T.cash.toFixed(0)}{T.blackout ? ` · ${T.blackout}` : ''}</div>
                      </div>
                      {!T.rh_configured && <div className="mt-1 text-[11px] text-neutral-500">Tap-to-buy needs Robinhood API credentials (RH_API_KEY + RH_PRIVATE_KEY) in Vercel env. Until then the button opens the Robinhood app; size and stop above are the order to place by hand.</div>}
                    </div>
                  )}
                  {br && br !== 'working' && (
                    <div className={`mt-1.5 rounded-xl border p-2 text-[12px] ${br.ok ? 'border-emerald-500 bg-emerald-50 text-emerald-900 dark:bg-emerald-400/10 dark:text-emerald-200' : 'border-rose-500 bg-rose-50 text-rose-900 dark:bg-rose-400/10 dark:text-rose-200'}`}>
                      {br.ok ? <>✅ Bought <b className="font-mono">{br.qty} {t.symbol}</b> @ <b className="font-mono">{fmt(br.avg_price ?? 0)}</b> (${(br.notional ?? 0).toFixed(2)}, order {br.order_id?.slice(0, 8)}). {br.stop ? <>Stop-limit <b className="font-mono">{br.stop.stop}/{br.stop.limit}</b> placed (order {br.stop.order_id.slice(0, 8)}).</> : <b>⚠ STOP NOT PLACED{br.stop_error ? `: ${br.stop_error}` : ''} — place it now in the app.</b>}{br.ledger_errors?.length ? <span> Ledger: {br.ledger_errors.join('; ')}</span> : ''}</>
                        : <>❌ {br.message ?? br.error ?? `order state ${br.state ?? 'unknown'}`}</>}
                    </div>
                  )}
                </div>
              )
            })}
            {/* The C+ filter hides names, so it must always say how many and let you look. A quiet
                filter that silently drops a name is the same failure as a zero standing in for a
                fetch that failed. */}
            {(() => {
              // Jacob 2026-09-11: "we should leave barred off the whole dashboard until they are a C or
              // above". They are off the board, not merely collapsed. A COUNT stays, because a list that
              // silently drops a name is the same defect as a zero standing in for a failed fetch — you
              // should always be able to see that something was withheld, and open it if you want.
              const below = queue.filter((t) => {
                const tm = timing[t.symbol]
                const T = tm && tm !== 'loading' && !('error' in tm) ? tm : null
                return T != null && (T.grade === 'D' || T.grade === 'F')
              })
              if (!below.length) return null
              return (
                <button type="button" onClick={() => setShowBelowC((v) => !v)}
                  className="w-full py-1 text-left text-[10px] uppercase tracking-wider text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300">
                  {showBelowC ? `▾ hide the ${below.length} barred` : `▸ ${below.length} barred / below C — off the board`}
                </button>
              )
            })()}
          </div>
        )}
        {poleSym && (
          <div className="mt-1 text-[11px] text-amber-800 dark:text-amber-200">
            ★ POLE is <b>{poleSym}</b> — the best live grade in the queue.
            {!verified(poleSym) && <> Mechanism NOT yet verified: nobody has confirmed value reaches the holder, so this is pole on timing alone.</>}
          </div>
        )}
        {!poleSym && (
          <div className="mt-1 text-[11px] text-amber-800 dark:text-amber-200">★ POLE is VACANT — nothing in the queue grades C or better right now.</div>
        )}
        {boardPoleSym && held.has(boardPoleSym) && (
          <div className="mt-1 text-[11px] text-amber-800 dark:text-amber-200">Session board still names {boardPoleSym} as pole but it is held — desk to refresh the board.</div>
        )}
        {perfItems.length > 0 && (
          <div className="mt-2 border-t border-neutral-100 pt-2 dark:border-white/5">
            <div className="mb-1 text-[11px] font-bold uppercase tracking-wider text-neutral-500">Where they are — every holding and every name in line, one chart</div>
            <PerfChart items={perfItems} secret={secret} />
          </div>
        )}
      </Panel>
      </details>

      {/* ── 4. PORTFOLIO CHART (server-rendered) + one realized line ── */}
      {chart}
      <div className="px-1 text-[12px] tabular-nums text-neutral-600 dark:text-neutral-400">
        {realized ? (
          <>Realized P&L to date <b className={`font-mono ${realized.pnl >= 0 ? 'text-green-600 dark:text-emerald-300' : 'text-red-600 dark:text-rose-300'}`}>{realized.pnl >= 0 ? '+' : '−'}${Math.abs(realized.pnl).toFixed(2)}</b> · {realized.n} closed trade{realized.n === 1 ? '' : 's'} <span className="font-mono">{realized.wins}W-{realized.losses}L</span> · full ledger below</>
        ) : <span className="text-red-600">Tax ledger unreachable — realized P&L unknown, not zero.</span>}
      </div>

      {/* ── 4. ARMED LINES ── */}
      <Panel accent="teal" title="⚡ Armed lines — watcher targets" right={<span className="text-[11px] text-neutral-500">every 15 min on the box</span>}>
        {state.triggers === null ? (
          <span className="text-[13px] text-red-600">Triggers unreachable — fetch failed, not empty.</span>
        ) : state.triggers.length === 0 ? (
          <span className="text-[13px] text-neutral-500">No armed lines.</span>
        ) : (
          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            {state.triggers.map((t, i) => (
              <div key={i} className="text-[12px] tabular-nums leading-snug">
                <span className="font-bold text-teal-700 dark:text-teal-300">{t.symbol}</span>
                <span className="ml-1.5 rounded bg-neutral-100 px-1 py-px text-[9px] uppercase tracking-wide text-neutral-600 dark:bg-white/10 dark:text-neutral-300">{t.kind}</span>
                <span className="ml-1.5 font-mono">{fmt(Number(t.level))}</span>
                {t.band_pct != null && <span className="ml-1 text-[10px] text-neutral-500">±{Number(t.band_pct)}%</span>}
                {t.spec && <span className="ml-1.5 text-[11px] text-neutral-500">{t.spec.length > 110 ? t.spec.slice(0, 110) + '…' : t.spec}</span>}
              </div>
            ))}
          </div>
        )}
      </Panel>

      {/* ── 5. COLLAPSED ── */}
      <details className="rounded-xl border border-neutral-200 px-3 py-1.5 dark:border-white/10">
        <summary className="cursor-pointer text-[12px] font-bold uppercase tracking-wider text-neutral-500">Watcher feed — latest 20</summary>
        {state.alerts === null ? <span className="text-[13px] text-red-600">Alert log unreachable.</span> : state.alerts.length === 0 ? <span className="text-[12px] text-neutral-500">No events yet.</span> : (
          <div className="mt-1 max-h-64 space-y-0.5 overflow-y-auto">
            {state.alerts.map((a, i) => (
              <div key={i} className="flex items-baseline gap-2 text-[12px] tabular-nums">
                <span className="whitespace-nowrap text-neutral-500">{denver(a.at)}</span>
                <span className="font-bold text-neutral-800 dark:text-neutral-200">{a.symbol}</span>
                <span className="text-neutral-500">{a.kind}{a.level != null ? ` @ ${fmt(Number(a.level))}` : ''}</span>
                {a.price != null && <span className="font-mono text-neutral-600 dark:text-neutral-400">{fmt(Number(a.price))}</span>}
                {a.sent ? <span className="text-green-600 dark:text-emerald-300">sent</span> : a.queued ? <span className="text-amber-600 dark:text-amber-300">queued</span> : null}
                {a.note && <span className="truncate text-neutral-500">{a.note}</span>}
              </div>
            ))}
          </div>
        )}
      </details>
      {board && (
        <details className="rounded-xl border border-neutral-200 px-3 py-1.5 dark:border-white/10">
          <summary className="cursor-pointer text-[12px] font-bold uppercase tracking-wider text-neutral-500">Rules — session board{state.board ? ` (${denver(state.board.updated_at)})` : ''} + house strategy</summary>
          <pre className="mt-1 max-h-72 overflow-y-auto whitespace-pre-wrap font-sans text-[12px] leading-relaxed tabular-nums text-neutral-700 dark:text-neutral-300">{board}</pre>
          {state.strategy && (
            <details className="mt-1 border-t border-neutral-100 pt-1 dark:border-white/5">
              <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-wider text-neutral-500">House strategy — as of {denver(state.strategy.updated_at)}</summary>
              <pre className="mt-1 max-h-72 overflow-y-auto whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-neutral-600 dark:text-neutral-400">{state.strategy.fact}</pre>
            </details>
          )}
        </details>
      )}
      {bottom}
    </div>
  )
}

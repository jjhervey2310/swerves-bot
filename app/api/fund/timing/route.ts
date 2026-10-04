import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'
import { resolveIds, cgFetch, lastKnownPrices, coinbaseSpot } from '@/lib/desk-cg'
import { gradeTiming, ANCHOR, type TimingInput, type Regime } from '@/lib/desk-timing'
import { rhConfigured, bestBidAsk } from '@/lib/robinhood'
import { venueFor } from '@/lib/rh-universe'
import { denverWeekStartIso } from '@/lib/desk/market-time'
import { rsCompletedPct } from '@/lib/desk/relative-strength'

// TIMING CHECK for one symbol: up-to-date price + 24h volume + an A–F grade against the house laws
// and the tape, plus the ruled size and the stop the buy would carry. Read-only; secret-gated.
// Numbers: CoinGecko (price, volume, 24h/7d/30d, 30 days of daily bars). Book: live_holdings,
// desk_triggers, live_trades, desk_config. Shared with /api/fund/buy so the button and the order
// are graded by the same code.

export const dynamic = 'force-dynamic'
export const revalidate = 0

export async function buildTiming(symbol: string) {
  const supabase = createServiceClient()
  if (!supabase) throw new Error('db unavailable')
  const sym = symbol.toUpperCase()
  const ids = await resolveIds([sym])
  const cgId = ids[sym]
  if (!cgId) throw new Error(`no CoinGecko id for ${sym}`)

  const weekStart = denverWeekStartIso()

  const [holdQ, trigQ, tradesQ, cfgQ, histQ, btcHistQ, mkt, chart] = await Promise.all([
    supabase.from('live_holdings').select('symbol, qty, avg_cost'),
    supabase.from('desk_triggers').select('symbol, kind, level').eq('active', true),
    supabase.from('live_trades').select('symbol, side, traded_at').gte('traded_at', weekStart).eq('side', 'buy'),
    supabase.from('desk_config').select('key, value').in('key', ['loop_enabled', 'macro_half_size', 'entry_blackout', 'sleeve_breaker', 'regime']),
    // The droplet already syncs a year of daily closes per id into cg_history, so
    // the 20-day high does not need a CoinGecko call at all for a name in the
    // universe. That matters because the chart call is the one that gets
    // rate-limited, and without a 20-day high the RUNNING law cannot be checked.
    supabase.from('cg_history').select('id, symbol, prices, updated_at').or(`id.eq.${cgId},symbol.eq.${sym}`).limit(1),
    // A9 §4 regime: BTC's stored year of closes (rising 200-day SMA test). desk_config.regime overrides.
    supabase.from('cg_history').select('prices').eq('id', 'bitcoin').limit(1),
    cgFetch(`https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=${cgId},bitcoin&price_change_percentage=24h,7d,30d`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : null),
    // Why the chart failed matters: a rate-limited fetch used to look identical to a
    // coin with no history, and both silently removed the RUNNING extension law from
    // the grade. Keep the status so the reason can be reported.
    cgFetch(`https://api.coingecko.com/api/v3/coins/${cgId}/market_chart?vs_currency=usd&days=30&interval=daily`, { cache: 'no-store' })
      .then(async (r) => r.ok ? { ok: true as const, data: await r.json() } : { ok: false as const, status: r.status })
      .catch((e) => ({ ok: false as const, status: 0, message: e instanceof Error ? e.message : String(e) })),
  ])
  type Mk = { id: string; current_price: number; total_volume: number; price_change_percentage_24h_in_currency?: number; price_change_percentage_7d_in_currency?: number; price_change_percentage_30d_in_currency?: number }
  const rows = (mkt ?? []) as Mk[]
  const me = rows.find((r) => r.id === cgId); const btc = rows.find((r) => r.id === 'bitcoin')
  // Don't throw on a rate limit: fall back to the last known close so the tab still renders a reasoned
  // grade. gradeTiming turns priceStale into a HARD bar, so this can inform but never fund an order.
  // PRICE SOURCE ORDER (Jacob 2026-09-10: "use robinhood as the main source as its what we trade on"):
  //   1. ROBINHOOD  - PRIMARY. It is the venue we fill on, it is not rate-limited, and its
  //                   ask-inclusive-of-buy-spread is the real cost of the trade being graded.
  //   2. COINBASE   - keyless live spot, never rate-limited, 83 of the 88 universe names. Added
  //                   2026-09-11 ("we cant have stale scores") so a CoinGecko 429 can no longer
  //                   leave the grader pricing off yesterday's close.
  //   3. CoinGecko  - price fallback. It is still called regardless, because it alone carries the
  //                   24h/7d/30d changes and the volume the grade needs; only its PRICE is secondary.
  //   4. cg_history - last daily close. STALE, hard-barred, and now a genuine last resort.
  // NOTE: hi20 comes from CoinGecko daily closes, so extPct mixes venues by a few basis points.
  // That is smaller than the close-vs-intraday gap already in that ratio, but it is a known seam.
  let priceStale: { at: string } | null = null
  let priceSource: 'robinhood' | 'coinbase' | 'coingecko' | 'cg_history' = 'robinhood'
  let rhQuote: { bid: number; ask: number; mid: number } | null = null
  let livePrice: number | null = null
  if (rhConfigured()) {
    try {
      const q = await bestBidAsk(sym)
      const bid = Number(q.bid_inclusive_of_sell_spread), ask = Number(q.ask_inclusive_of_buy_spread)
      const mid = Number(q.price) || (bid > 0 && ask > 0 ? (bid + ask) / 2 : 0)
      if (mid > 0) { livePrice = mid; rhQuote = { bid, ask, mid } }
    } catch { /* not a Robinhood pair, or RH unreachable - fall through */ }
  }
  if (!livePrice) {
    const cb = await coinbaseSpot(sym)
    if (cb) { livePrice = cb.usd; priceSource = 'coinbase'; rhQuote = { bid: cb.bid, ask: cb.ask, mid: cb.usd } }
  }
  if (!livePrice && me?.current_price) { livePrice = me.current_price; priceSource = 'coingecko' }
  if (!livePrice) {
    const lk = await lastKnownPrices([cgId])
    if (lk[cgId]) { livePrice = lk[cgId].usd; priceStale = { at: lk[cgId].at }; priceSource = 'cg_history' }
  }
  if (!livePrice) throw new Error(`No price for ${sym}: no Robinhood quote, no Coinbase ${sym}-USD pair, CoinGecko rate-limited, and no cg_history row for ${cgId}`)
  const chartData = chart.ok ? (chart.data as { prices?: [number, number][]; total_volumes?: [number, number][] }) : null
  const chartFailure = chart.ok ? null
    : chart.status === 429 ? 'CoinGecko rate-limited the 30-day chart (429)'
    : `CoinGecko chart fetch failed (${chart.status || 'network error'})`
  const prices = ((chartData?.prices ?? []) as [number, number][]).map((p) => p[1])
  // The last point of a CoinGecko daily series is today's incomplete bar, and
  // cg_history stores that series verbatim — so both get the same trim.
  const completedPx = prices.slice(0, -1)
  const highOf = (px: number[]) => px.length >= 5 ? Math.max(...px.slice(-20)) : null

  // 20-day high, preferring the stored series: no call, no rate limit. Stale rows
  // are refused rather than quietly used — a high computed from week-old bars is
  // not the check the law asks for.
  const histRow = ((histQ.data ?? []) as { prices: [number, number][] | null; updated_at: string }[])[0]
  const histAgeH = histRow?.updated_at ? (Date.now() - new Date(histRow.updated_at).getTime()) / 36e5 : null
  const histFresh = histAgeH !== null && histAgeH <= 48
  const histPx = histFresh && Array.isArray(histRow?.prices) ? histRow.prices.map((p) => p[1]).slice(0, -1) : []
  const hi20FromDb = highOf(histPx)
  const hi20 = hi20FromDb ?? highOf(completedPx)
  const hi20Source = hi20FromDb !== null ? 'cg_history' : hi20 !== null ? 'coingecko' : null

  // cg_history rows carry [ts, close, volume] since 2026-09-11, so the volume leg survives a CoinGecko
  // rate limit the same way the 20-day high already does. Without this, an unverifiable volume capped
  // the grade at C on names that were otherwise clean.
  const livePriceForTape = livePrice
  const histVol = ((histRow?.prices ?? []) as number[][]).map((r) => r[2]).filter((v) => typeof v === 'number' && v > 0)
  // DERIVE THE TAPE FROM cg_history WHEN CoinGecko IS MISSING. Critical: d1/d7/d30 feed the CHASE LAWS.
  // When CoinGecko 429'd, those came back null, the chase checks silently did not fire, and ARB — up
  // 84% in 30 days and hard-barred — graded A/100 and read as buyable (2026-09-11). A check that cannot
  // run must never pass. cg_history carries a year of daily closes, so the laws can always be evaluated.
  const histCloses = ((histRow?.prices ?? []) as number[][]).map((r) => r[1]).filter((v) => typeof v === 'number' && v > 0)
  const chg = (n: number) => {
    if (histCloses.length < n + 1 || !livePriceForTape) return null
    const then = histCloses[histCloses.length - 1 - n]
    return then > 0 ? (livePriceForTape / then - 1) * 100 : null
  }
  // ONE DEFINITION, ALWAYS THE SAME SOURCE. Preferring CoinGecko when available and cg_history
  // otherwise still flickered, because the two measure different things: CoinGecko's rolling 24h in
  // USD vs Coinbase's daily bar in base units. EIGEN read 1.38x on one and 0.80x on the other in the
  // same minute. So the ratio is defined once, on cg_history alone: the LAST COMPLETED daily volume
  // against the 20 completed days before it. That is exactly the quantity the breakout rule names
  // ("volume >= 1.5x its 20-day average" on a daily close), it is always available, and it cannot
  // drift between reads. Today's partial bar is deliberately excluded — a half-finished day compared
  // against full ones reads low and would bar good names for the crime of being checked before noon.
  const completedHistVol = histVol.slice(0, -1)          // drop today's partial bar
  const avgVol20 = completedHistVol.length >= 6
    ? completedHistVol.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, completedHistVol.length)
    : null
  const vol24hUnified = completedHistVol.length ? completedHistVol[completedHistVol.length - 1] : null
  const volSource = avgVol20 != null && vol24hUnified != null ? 'cg_history (last completed day)' : null
  // A failed chart only breaks the RUNNING law when the stored series could not
  // supply the high either. When it could, the chart costs us the volume
  // confirmation and nothing more, so say that instead of barring the entry.
  const tapeError = hi20 === null ? chartFailure
    : chartFailure ? `${chartFailure} — 20-day high served from cg_history, volume unconfirmed`
    : null

  const input_rs7 = () => me?.price_change_percentage_7d_in_currency != null && btc?.price_change_percentage_7d_in_currency != null ? me.price_change_percentage_7d_in_currency - btc.price_change_percentage_7d_in_currency : null
  const holdings = (holdQ.data ?? []) as { symbol: string; qty: number; avg_cost: number }[]
  const cash = Number(holdings.find((h) => h.symbol === 'USD')?.qty ?? 0)
  const positions = holdings.filter((h) => h.symbol !== 'USD' && Number(h.qty) > 0)
  // Book value at CoinGecko prices for the held names (one more call; the page's own figure is client-side).
  const heldIds = await resolveIds(positions.map((p) => p.symbol))
  const heldIdList = [...new Set(positions.map((p) => heldIds[p.symbol]).filter(Boolean))]
  const heldMkt = positions.length ? await cgFetch(`https://api.coingecko.com/api/v3/simple/price?ids=${heldIdList.join(',')}&vs_currencies=usd`, { cache: 'no-store' }).then((r) => r.ok ? r.json() : {}).catch(() => ({})) as Record<string, { usd: number }> : {}
  // A rate-limited price must NEVER value a position at zero: that collapses the book to cash, zeroes
  // the slot count and caps every grade at D (2026-09-10 defect). Fall back to the last known close.
  const missing = positions.filter((p) => !(heldMkt[heldIds[p.symbol]]?.usd > 0))
  const fallback = missing.length ? await lastKnownPrices(missing.map((p) => heldIds[p.symbol])) : {}
  const priceOf = (sym: string) => heldMkt[heldIds[sym]]?.usd || fallback[heldIds[sym]]?.usd || null
  const unpriced = positions.filter((p) => priceOf(p.symbol) == null).map((p) => p.symbol)
  const posValue = positions.reduce((s, p) => s + Number(p.qty) * (priceOf(p.symbol) ?? 0), 0)
  const book = posValue + cash
  const stalePriced = missing.filter((p) => fallback[heldIds[p.symbol]]).map((p) => p.symbol)
  const cfg = Object.fromEntries(((cfgQ.data ?? []) as { key: string; value: string }[]).map((r) => [r.key, r.value]))
  const nowIso = new Date().toISOString()
  // A9.1 §2: the blackout law covers CPI and FOMC. desk_config.entry_blackout = "startISO/endISO|label" windows joined by ';'.
  // Windows live in desk_config only; no dated defaults in code (the Sept-2026 ones had expired in place).
  const blackoutCfg = cfg.entry_blackout ?? ''
  const blackout = blackoutCfg.split(';').map((e) => { const [range, label] = e.split('|'); const [b0, b1] = (range ?? '').split('/'); return b0 && b1 && nowIso >= b0 && nowIso <= b1 ? (label ?? 'entry blackout') : null }).find(Boolean) ?? null
  const halfSize = cfg.macro_half_size != null ? String(cfg.macro_half_size).toLowerCase() === 'true' : false
  // A9 §3 breakout signal on the LAST COMPLETED close (window = the 20 completed days before it, today excluded).
  const sigCloses = histCloses.length ? histCloses.slice(0, -1) : completedPx
  const lastClose = sigCloses.length ? sigCloses[sigCloses.length - 1] : null
  const sigWin = sigCloses.slice(-21, -1)
  const sigHi = sigWin.length >= 5 ? Math.max(...sigWin) : null
  const lo20 = sigWin.length >= 5 ? Math.min(...sigWin) : null
  // RS on the SAME completed-bar clock as the breakout: 7-day return of both series from cg_history
  // closes, joined by timestamp. CoinGecko's rolling intraday 7d is only a labelled fallback when no
  // stored history exists — it cannot alter a completed-bar signal.
  const btcPts = ((((btcHistQ.data ?? []) as { prices: number[][] | null }[])[0]?.prices) ?? []) as number[][]
  const rsCompleted = rsCompletedPct((histRow?.prices ?? []) as number[][], btcPts)
  const sigRs = rsCompleted ?? input_rs7()
  const rsSource = rsCompleted != null ? 'cg_history completed closes' : 'coingecko rolling 7d (no stored history — fallback)'
  const sigParts = {
    high: lastClose != null && sigHi != null && lastClose > sigHi,
    vol: vol24hUnified != null && avgVol20 != null && vol24hUnified >= 1.5 * avgVol20,
    rs: sigRs != null && sigRs > 0,
    ext: lastClose != null && sigHi != null && lastClose / sigHi - 1 <= 0.15,
  }
  const signal: boolean | null = lastClose == null || sigHi == null ? null : (sigParts.high && sigParts.vol && sigParts.rs && sigParts.ext)
  const signalWhy = lastClose == null || sigHi == null ? 'no completed-close history' : [`close ${sigParts.high ? '>' : '≤'} 20d high`, `vol ${vol24hUnified != null && avgVol20 ? (vol24hUnified / avgVol20).toFixed(1) + 'x' : '?'} ${sigParts.vol ? '≥' : '<'} 1.5x`, `RS ${sigParts.rs ? '>' : '≤'} BTC`].join(', ')
  // REGIME: desk_config.regime overrides; else BTC's last completed close vs a RISING 200-day SMA with the 50-day above it.
  const btcCloses = (((btcHistQ.data ?? []) as { prices: number[][] | null }[])[0]?.prices ?? []).map((r) => r[1]).filter((v) => typeof v === 'number' && v > 0).slice(0, -1)
  const sma = (arr: number[], n: number, back = 0) => arr.length >= n + back ? arr.slice(arr.length - n - back, arr.length - back).reduce((a, b) => a + b, 0) / n : null
  const s200 = sma(btcCloses, 200), s200prev = sma(btcCloses, 200, 20), s50 = sma(btcCloses, 50)
  const btcLast = btcCloses.length ? btcCloses[btcCloses.length - 1] : null
  const ov = String(cfg.regime ?? '').toUpperCase()
  const regime: Regime = ov === 'BULL' || ov === 'NEUTRAL' || ov === 'BEAR' ? (ov as Regime)
    : btcLast != null && s200 != null && s200prev != null && s50 != null ? (btcLast > s200 && s200 > s200prev && s50 > s200 ? 'BULL' : btcLast < s200 && s50 < s200 ? 'BEAR' : 'NEUTRAL') : 'NEUTRAL'
  const regimeWhy = ov ? 'desk_config override' : btcLast != null && s200 != null ? `BTC ${btcLast.toFixed(0)} vs 200d ${s200.toFixed(0)} (${s200prev != null && s200 > s200prev ? 'rising' : 'not rising'}), 50d ${s50?.toFixed(0) ?? '?'}` : 'no BTC history in cg_history — bars applied in full'
  const sleeveUsd = positions.filter((p) => !ANCHOR.has(p.symbol)).reduce((s, p) => s + Number(p.qty) * (priceOf(p.symbol) ?? 0), 0)
  const mine = positions.find((p) => p.symbol === sym)
  const nameUsd = mine ? Number(mine.qty) * (priceOf(sym) ?? livePrice) : 0

  const input: TimingInput = {
    symbol: sym, price: livePrice, priceStale,
    d1: me?.price_change_percentage_24h_in_currency ?? chg(1), d7: me?.price_change_percentage_7d_in_currency ?? chg(7), d30: me?.price_change_percentage_30d_in_currency ?? chg(30),
    vol24h: vol24hUnified, avgVol20, hi20,
    tapeError: hi20 === null ? tapeError : null,
    rs7VsBtc: sigRs,
    armed: ((trigQ.data ?? []) as { symbol: string; kind: string; level: number }[]).filter((t) => t.symbol === sym).map((t) => ({ kind: t.kind, level: Number(t.level) })),
    cashUsd: cash, bookUsd: book,
    sleeveCount: positions.filter((p) => !ANCHOR.has(p.symbol)).length, slots: Math.min(7, Math.floor(book / 150)), holdingsCount: positions.length,
    weeklyEntries: new Set(((tradesQ.data ?? []) as { symbol: string }[]).map((t) => t.symbol).filter((s) => !ANCHOR.has(s))).size,
    blackout, halted: String(cfg.loop_enabled ?? 'true').toLowerCase() !== 'true',
    halfSize, held: positions.some((p) => p.symbol === sym),
    venue: venueFor(sym),
    signal, signalWhy, regime, regimeWhy, breaker: cfg.sleeve_breaker ? String(cfg.sleeve_breaker) : null, sleeveUsd, nameUsd,
  }
  const result = gradeTiming(input)
  return {
    symbol: sym, cgId, at: nowIso,
    price: livePrice, price_source: priceSource, price_stale: priceStale, rh_quote: rhQuote, vol24h: vol24hUnified, avgVol20, vol_source: volSource, volX: vol24hUnified && avgVol20 ? vol24hUnified / avgVol20 : null,
    d1: input.d1, d7: input.d7, d30: input.d30, hi20, extPct: hi20 ? (livePrice / hi20 - 1) * 100 : null, rs7VsBtc: input.rs7VsBtc, rsSource,
    tapeError, hi20Source,
    book, cash, slots: input.slots, sleeveCount: input.sleeveCount, weeklyEntries: input.weeklyEntries, blackout, halfSize,
    signal, signalWhy, regime, regimeWhy, breaker: input.breaker, sleeveUsd, sleeveCap: book * 0.15, lo20,
    book_health: { unpriced, stale_priced: stalePriced, trustworthy: unpriced.length === 0 },
    ...result,
    rh_configured: rhConfigured(),
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url)
  const secret = req.headers.get('x-admin-secret') || url.searchParams.get('secret')
  if (!process.env.ADMIN_SECRET || secret !== process.env.ADMIN_SECRET) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const symbol = (url.searchParams.get('symbol') ?? '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  if (!symbol) return NextResponse.json({ error: 'symbol required' }, { status: 400 })
  try {
    return NextResponse.json(await buildTiming(symbol), { headers: { 'Cache-Control': 'no-store' } })
  } catch (e) {
    return NextResponse.json({ error: e instanceof Error ? e.message : String(e) }, { status: 502 })
  }
}

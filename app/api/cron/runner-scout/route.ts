import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

// Hourly server-side runner radar for the J&P Fund: scans the Robinhood-listed
// crypto universe from CoinGecko, stages each coin by how far its move has gone,
// upserts fund_radar, flags signals, and banks the nightly fund snapshot — all
// with no laptop involved. LLM investigation of flagged signals happens locally.

export const dynamic = 'force-dynamic'
import { RH_SYMBOLS } from '@/lib/rh-universe'

export const maxDuration = 60


interface CgRow {
  symbol: string; name: string; current_price: number | null
  market_cap: number | null; total_volume: number | null
  price_change_percentage_24h_in_currency: number | null
  price_change_percentage_7d_in_currency: number | null
  price_change_percentage_30d_in_currency: number | null
}

async function fetchPage(page: number): Promise<CgRow[]> {
  const url = `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=${page}&price_change_percentage=24h,7d,30d`
  for (let attempt = 0; attempt < 2; attempt++) {
    const res = await fetch(url, { cache: 'no-store', headers: { 'User-Agent': 'lmc-runner-scout/1.0' } })
    if (res.ok) return (await res.json()) as CgRow[]
    if (res.status === 429 && attempt === 0) { await new Promise((r) => setTimeout(r, 12_000)); continue }
    throw new Error(`CoinGecko ${res.status} on page ${page}`)
  }
  return []
}

async function handle(req: Request) {
  const secret = req.headers.get('x-content-secret') || new URL(req.url).searchParams.get('secret')
  if (!process.env.DAILY_CONTENT_SECRET || secret !== process.env.DAILY_CONTENT_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  const supabase = createServiceClient()
  if (!supabase) return NextResponse.json({ error: 'db unavailable' }, { status: 503 })

  const denverDay = (d = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver' }).format(d)
  const day = denverDay()
  const yesterday = denverDay(new Date(Date.now() - 864e5))

  const market = (await Promise.all([fetchPage(1), fetchPage(2)])).flat()

  const rows = market.flatMap((c) => {
    const sym = c.symbol.toUpperCase()
    if (!RH_SYMBOLS.has(sym) || ['USDC', 'USDG', 'PAXG'].includes(sym)) return []
    const mc = c.market_cap ?? 0
    if (!mc || c.current_price == null) return []
    const turn = ((c.total_volume ?? 0) / mc) * 100
    // Upstream volume fields go bad: 09-15 CoinGecko reported ETH 24h volume at
    // 1.116e19 USD against a 2.96e11 market cap, which scored as a 2.99-billion-
    // percent turnover and fired a signal. A coin that turns over more than five
    // times its market cap in a day is a broken feed, not a runner. Drop the row
    // rather than write it, so the bad number never becomes tomorrow's baseline.
    if (!Number.isFinite(turn) || turn > 500) return []
    const d1 = c.price_change_percentage_24h_in_currency ?? 0
    const d7 = c.price_change_percentage_7d_in_currency ?? 0
    const d30 = c.price_change_percentage_30d_in_currency ?? 0
    const stage = d30 >= 70 ? 'EXTENDED' : d7 >= 25 ? 'RUNNING' : turn >= 8 && d7 > -5 && d30 < 35 ? 'EARLY' : 'quiet'
    return [{
      scan_date: day, symbol: sym, name: c.name, price: c.current_price, market_cap: mc,
      turnover: +turn.toFixed(1), d1: +d1.toFixed(1), d7: +d7.toFixed(1), d30: +d30.toFixed(1),
      stage, score: +(turn * 2 + Math.max(d7, 0) - Math.max(d30, 0) * 0.5 + Math.max(d1, 0)).toFixed(1),
    }]
  })
  if (!rows.length) return NextResponse.json({ error: 'scan produced no rows' }, { status: 500 })

  // Baseline for signal detection, read BEFORE the upsert overwrites today's row:
  // the previous hour's reading if this is not the first scan of the day, else
  // yesterday's close. Comparing every hour against yesterday made one intraday
  // turnover climb re-fire the same signal on the hour, every hour (RE, 08-26:
  // seven identical flags in fifteen hours).
  const [{ data: priorYday }, { data: priorToday }] = await Promise.all([
    supabase.from('fund_radar').select('symbol, stage, turnover').eq('scan_date', yesterday),
    supabase.from('fund_radar').select('symbol, stage, turnover').eq('scan_date', day),
  ])
  const priorBy = new Map((priorYday ?? []).map((p) => [p.symbol as string, p]))
  for (const p of priorToday ?? []) priorBy.set(p.symbol as string, p)

  const { error: radarErr } = await supabase.from('fund_radar').upsert(rows, { onConflict: 'scan_date,symbol' })
  if (radarErr) return NextResponse.json({ error: radarErr.message }, { status: 500 })

  // Signal detection vs that baseline: fresh EARLY entrants and turnover doublings.
  const signals: string[] = []
  for (const r of rows) {
    const p = priorBy.get(r.symbol)
    if (r.stage === 'EARLY' && r.score >= 55 && (!p || p.stage !== 'EARLY')) {
      signals.push(`${r.symbol} newly EARLY score ${r.score} (turn ${r.turnover}%, 7d ${r.d7}%, 30d ${r.d30}%)`)
    }
    if (p && Number(p.turnover) > 0 && r.turnover >= Number(p.turnover) * 2 && r.turnover >= 10) {
      signals.push(`${r.symbol} turnover doubled ${p.turnover}% → ${r.turnover}%`)
    }
  }
  const zec = rows.find((r) => r.symbol === 'ZEC')
  const stamp = new Date().toLocaleString('en-US', { timeZone: 'America/Denver', hour12: false })
  const status = `${stamp} DEN — scanned ${rows.length}. ` +
    (signals.length ? `SIGNALS: ${signals.join(' · ')}. ` : 'No signal. ') +
    (zec ? `ZEC $${zec.price} ${zec.stage} turn ${zec.turnover}% 7d ${zec.d7}% 30d ${zec.d30}%.` : 'ZEC missing from scan.')
  await supabase.from('pa_memory').upsert(
    { topic: 'runner-scout', fact: status, source: 'runner-scout-cron', active: true, updated_at: new Date().toISOString() },
    { onConflict: 'topic' })
  if (signals.length) {
    await supabase.from('pa_memory').upsert(
      { topic: 'runner-scout-signal', fact: `${stamp} DEN — ${signals.join(' · ')} — UNINVESTIGATED, local scout picks up`, source: 'runner-scout-cron', active: true, updated_at: new Date().toISOString() },
      { onConflict: 'topic' })
  }

  // Midnight-adjacent run banks the fund's daily equity snapshot (holdings × scan prices + cash).
  const denverHour = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', hour: 'numeric', hour12: false }).format(new Date()))
  let banked: number | null = null
  if (denverHour === 0) {
    const { data: holdings } = await supabase.from('live_holdings').select('symbol, qty')
    if (holdings?.length) {
      const priceBy = new Map(rows.map((r) => [r.symbol, r.price]))
      let total = 0, missing = false
      for (const h of holdings) {
        if (h.symbol === 'USD') { total += Number(h.qty); continue }
        const p = priceBy.get(h.symbol.toUpperCase())
        if (p == null) { missing = true; break }
        total += Number(h.qty) * Number(p)
      }
      if (!missing) {
        banked = +total.toFixed(2)
        await supabase.from('fund_snapshots').upsert({ snapshot_date: day, total: banked }, { onConflict: 'snapshot_date' })
      }
    }
  }

  return NextResponse.json({ scanned: rows.length, signals, snapshot: banked, day })
}

export const GET = handle
export const POST = handle

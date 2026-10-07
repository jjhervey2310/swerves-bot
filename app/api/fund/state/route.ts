import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'
import { resolveIds, coinbaseSpot, lastKnownPrices } from '@/lib/desk-cg'
import { rhConfigured, bestBidAsk, listOpenOrders, getOrder, orderLevel, orderQty } from '@/lib/robinhood'
import type { SupabaseClient } from '@supabase/supabase-js'

// Live desk state for the ROBINHOOD tab's 60s client refresh.
// Same auth + service-client pattern as the page; read-only; never cached.

export const dynamic = 'force-dynamic'
export const revalidate = 0

// ── Build request #14(b): the broker's resting orders ──────────────────────────────────────────
// `broker_open_orders` is a SNAPSHOT of what is actually armed at Robinhood. It is refreshed here
// (at most once every two minutes per instance) when the API keys are configured; otherwise it is
// whatever the desk last wrote. The age is always returned with it, because "no rows" and "we could
// not ask" are different answers and only one of them means NOT ARMED.
let lastOrderSync = 0
let lastSyncNote: string | null = null   // what the last broker call actually saw — the only way to debug this from prod
async function syncOpenOrders(supabase: SupabaseClient): Promise<void> {
  if (!rhConfigured() || Date.now() - lastOrderSync < 120_000) return
  lastOrderSync = Date.now()
  try {
    const { orders, closed, seen, states } = await listOpenOrders()
    lastSyncNote = `${new Date().toISOString()} seen=${seen} open=${orders.length} states=${states.join('/') || 'none'}`
    // A key that can see NOTHING AT ALL is not a broker saying "nothing is armed". Keep the existing
    // snapshot, leave its timestamp alone so the page ages it into "unknown", and write nothing.
    if (!orders.length && seen === 0) return
    const rows = orders.map((o) => ({
      order_id: o.id,
      symbol: (o.symbol ?? '').replace(/-USD$/i, '').toUpperCase(),
      side: o.side, order_type: o.type,
      level: orderLevel(o), qty: orderQty(o), notional: null,
      state: o.state, created_at: o.created_at ?? null, synced_at: new Date().toISOString(),
    })).filter((r) => r.symbol)
    if (rows.length) await supabase.from('broker_open_orders').upsert(rows, { onConflict: 'order_id' })
    // REMOVE ONLY WHAT THE BROKER EXPLICITLY REPORTS AS NO LONGER OPEN. The first version cleared
    // every row the response did not mention, which erased seven live orders the moment one API
    // call came back thin. An order we were not told about is an order we know nothing about.
    const goneIds = closed.map((o) => o.id).filter(Boolean)
    // ...BUT ALSO ASK ABOUT THE ONES THE BROKER NO LONGER MENTIONS. Robinhood's order list only returns
    // recent orders, so a snapshot row older than that window is never in `orders` and never in
    // `closed`: the rule above kept it forever. Found 2026-10-07 — seven bids and stops from 09-09..15
    // still on the tab three weeks after the account was emptied and every order cancelled. The broker
    // answered (seen > 0), so each unmentioned id is looked up by itself and removed only when the broker
    // says, for that id, that it is not open. A lookup that fails leaves the row in place: unknown is
    // not closed.
    const mentioned = new Set([...orders, ...closed].map((o) => o.id))
    const { data: snap } = await supabase.from('broker_open_orders').select('order_id')
    const unmentioned = ((snap ?? []) as { order_id: string }[]).map((r) => r.order_id).filter((id) => id && !mentioned.has(id))
    for (const id of unmentioned.slice(0, 20)) {
      try {
        const o = await getOrder(id)
        const st = (o.state ?? '').toLowerCase()
        if (st && !['queued', 'confirmed', 'partially_filled', 'open'].includes(st)) goneIds.push(id)
      } catch (e) {
        // Could not ask — leave the row, say nothing false. But SAY WHY in the sync note: this is the
        // only way to see from prod what the per-id endpoint actually returned (2026-10-07: the first
        // version swallowed it, and seven rows survived a deploy with no visible reason).
        if (!lastSyncNote?.includes('lookup')) lastSyncNote = `${lastSyncNote ?? ''} | lookup ${id.slice(0, 8)} failed: ${e instanceof Error ? e.message.slice(0, 140) : 'unknown'}`
      }
    }
    if (goneIds.length) await supabase.from('broker_open_orders').delete().in('order_id', goneIds)
    if (rows.length || goneIds.length) await supabase.from('desk_config').upsert({ key: 'open_orders_synced_at', value: new Date().toISOString() }, { onConflict: 'key' })
  } catch (e) {
    // Leave the last snapshot and its age in place — a failed sync is never an empty book.
    lastSyncNote = `${new Date().toISOString()} sync failed: ${e instanceof Error ? e.message.slice(0, 160) : 'unknown'}`
  }
}

export async function GET(req: Request) {
  const url = new URL(req.url)
  const secret = req.headers.get('x-admin-secret') || url.searchParams.get('secret')
  if (!process.env.ADMIN_SECRET || secret !== process.env.ADMIN_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }
  const supabase = createServiceClient()
  if (!supabase) return NextResponse.json({ error: 'db unavailable' }, { status: 503 })

  // Refresh the broker's resting orders before reading them, so "armed" is the broker's answer and
  // not a snapshot from some earlier session (build request #14b).
  await syncOpenOrders(supabase)

  const [h, t, a, b, st, le, th, oo, ooAt] = await Promise.all([
    supabase.from('live_holdings').select('symbol, qty, avg_cost, synced_at, basis_source').order('symbol'),
    supabase.from('desk_triggers').select('symbol, kind, level, band_pct, spec').eq('active', true).order('symbol'),
    supabase.from('desk_alert_log').select('at, symbol, kind, level, price, sent, queued, note').order('at', { ascending: false }).limit(20),
    supabase.from('pa_memory').select('fact, updated_at').eq('topic', 'dashboard').maybeSingle(),
    supabase.from('pa_memory').select('fact, updated_at').eq('topic', 'house-strategy').maybeSingle(),
    supabase.from('desk_config').select('value, updated_at').eq('key', 'loop_enabled').maybeSingle(),
    // desk_theses (build request #4): thesis + gate under each holding, POLE/WATCH/BARRED for the pole panel.
    // buy_rank / entry_level / entry_note drive the BUY BOARD (build request #16). The board orders
    // by buy_rank and never by updated_at — sorting by the edit clock is what made the most recently
    // touched name look like the top pick (build note, 09-08).
    supabase.from('desk_theses').select('symbol, status, thesis, gate, updated_at, buy_rank, entry_level, entry_note, sector').order('symbol'),
    supabase.from('broker_open_orders').select('order_id, symbol, side, order_type, level, qty, state, created_at, synced_at').order('symbol'),
    supabase.from('desk_config').select('value').eq('key', 'open_orders_synced_at').maybeSingle(),
  ])
  // NARRATIVE LEADERBOARD, the 1..10 board (Jacob 2026-09-15: "why is the narrative leaderboard not
  // working and listed 1-10 / you need to have a pick for every spot verified and would be our next
  // buy if we chose that narrative"). #19 built the sector momentum table below and it works, but it
  // ranked 12 sectors by median 7d and five of them resolved to "none verified" — a seat with no pick.
  // desk_narratives is the missing half: exactly ten ranked rows, each carrying ONE Robinhood-listed
  // pick, the level we would buy it at, and a verdict naming what was checked and on what date.
  // Ranking is by EVIDENCE that money is already moving toward the coin, not by momentum: in a week
  // where every sector is red, ranking on median 7d ranks "least down", which is not a reason to buy.
  const narr = await supabase.from('desk_narratives')
    .select('rank, narrative, plain, evidence, pick, pick_why, verdict, verified_on, checked, against_it, entry, runner_up, syms, sources, updated_at, catalyst, catalyst_on, catalyst_kind, unlock_note')
    .order('rank')
  // Latest radar scan (build request #6): stage/score/turnover beside each POLE/WATCH thesis. Numbers never come from thesis text.
  const latestScan = await supabase.from('fund_radar').select('scan_date').order('scan_date', { ascending: false }).limit(1).maybeSingle()
  const radar = latestScan.data?.scan_date
    ? await supabase.from('fund_radar').select('symbol, stage, score, turnover, d1, d7, d30, price, scan_date').eq('scan_date', latestScan.data.scan_date)
    : { data: null }

  // Latest flow radar (build request #8): flow score + stage beside each queue name.
  const latestFlow = await supabase.from('flow_radar').select('scan_date').order('scan_date', { ascending: false }).limit(1).maybeSingle()
  const flow = latestFlow.data?.scan_date
    ? await supabase.from('flow_radar').select('symbol, flow_score, stage, fees_wow, vol_wow, scan_date').eq('scan_date', latestFlow.data.scan_date)
    : { data: null }

  // PRICE THE BOOK SERVER-SIDE, ON THE SAME CHAIN AS EVERYTHING ELSE (Robinhood -> Coinbase -> last
  // close). The browser used to rebuild it from a client CoinGecko call with `?? 0` on a miss, so a
  // rate limit in Jacob's browser valued a position at nothing — SOL alone would understate the
  // account by $268 (2026-09-11, the fourth instance of failed-fetch-as-zero). A position we cannot
  // price goes in `unpriced` and `book` comes back NULL: unknown, never silently worth zero.
  const hold = (h.data ?? []) as { symbol: string; qty: number }[]
  const posSyms = hold.filter((x) => x.symbol !== 'USD' && Number(x.qty) > 0).map((x) => x.symbol)
  const cashUsd = Number(hold.find((x) => x.symbol === 'USD')?.qty ?? 0)
  const ids = await resolveIds(posSyms).catch(() => ({} as Record<string, string>))
  const priced: Record<string, { usd: number; src: string }> = {}
  for (const sym of posSyms) {
    if (rhConfigured()) {
      try {
        const q = await bestBidAsk(sym)
        const mid = Number(q.price) || (Number(q.bid_inclusive_of_sell_spread) + Number(q.ask_inclusive_of_buy_spread)) / 2
        if (mid > 0) { priced[sym] = { usd: mid, src: 'robinhood' }; continue }
      } catch { /* fall through */ }
    }
    const cb = await coinbaseSpot(sym)
    if (cb) { priced[sym] = { usd: cb.usd, src: 'coinbase' }; continue }
    const id = ids[sym]
    if (id) { const lk = await lastKnownPrices([id]); if (lk[id]) priced[sym] = { usd: lk[id].usd, src: 'cg_history (stale)' } }
  }
  const unpriced = posSyms.filter((sym) => !priced[sym])
  const posValue = posSyms.reduce((sum, sym) => sum + (priced[sym] ? Number(hold.find((x) => x.symbol === sym)!.qty) * priced[sym].usd : 0), 0)

  // NARRATIVE LEADERBOARD (build request #19). Per sector (desk_theses.sector): MOMENTUM = median d7 /
  // d30 across the sector's names that have a row in the latest radar scan (the radar universe is the
  // Robinhood list, so a name the app cannot trade — PUMP, TAO, TON — simply has no row and drops out
  // of the median); OUR EXPOSURE = dollars and % of book held in the sector, priced on the same server
  // chain as the book; GAP = a top-3 sector by momentum where we hold nothing; BEST VERIFIED = the
  // sector's top buy_rank (the desk's explicit act after the mechanism check), else a HELD name, else
  // "none verified". Ranked by median d7 — a narrative switch shows up on the week before the month.
  // A GAP is a research instruction, never an auto-buy: entries still need the mechanism, the tested
  // signal and a written level.
  const thesesRows = (th.data ?? []) as { symbol: string; status: string; sector?: string | null; buy_rank?: number | null }[]
  const radarBySym = new Map(((radar.data ?? []) as { symbol: string; d7: number | null; d30: number | null }[]).map((r) => [r.symbol, r]))
  const bookUsd = unpriced.length ? null : posValue + cashUsd
  const median = (xs: number[]) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2 }
  const heldUsd = (sym: string) => { const p = hold.find((x) => x.symbol === sym); return p && priced[sym] ? Number(p.qty) * priced[sym].usd : 0 }
  const bySector = new Map<string, typeof thesesRows>()
  for (const t of thesesRows) { if (!t.sector) continue; if (!bySector.has(t.sector)) bySector.set(t.sector, []); bySector.get(t.sector)!.push(t) }
  const sectors = [...bySector.entries()].map(([sector, names]) => {
    const scanned = names.filter((t) => radarBySym.has(t.symbol))
    const d7 = median(scanned.map((t) => Number(radarBySym.get(t.symbol)!.d7)).filter(Number.isFinite))
    const d30 = median(scanned.map((t) => Number(radarBySym.get(t.symbol)!.d30)).filter(Number.isFinite))
    const exposureUsd = names.reduce((s, t) => s + heldUsd(t.symbol), 0)
    const ranked = names.filter((t) => t.buy_rank != null).sort((a, b) => (a.buy_rank as number) - (b.buy_rank as number))
    return {
      sector, names: names.map((t) => t.symbol), scanned: scanned.length, d7, d30,
      exposure_usd: exposureUsd, exposure_pct: bookUsd ? (exposureUsd / bookUsd) * 100 : null,
      held: names.filter((t) => heldUsd(t.symbol) > 0).map((t) => t.symbol),
      best_verified: ranked[0]?.symbol ?? names.find((t) => t.status === 'HELD')?.symbol ?? null,
      gap: false,
    }
  }).sort((a, b) => (b.d7 ?? -Infinity) - (a.d7 ?? -Infinity) || (b.d30 ?? -Infinity) - (a.d30 ?? -Infinity))
  sectors.filter((s) => s.d7 != null).slice(0, 3).forEach((s) => { if (s.exposure_usd === 0) s.gap = true })
  // Each narrative's live numbers come from the SAME radar scan and the SAME server price chain as the
  // sector table, so the two can never disagree. `scanned` is published beside the median: a narrative
  // whose names are mostly absent from the scan has a median built on thin air, and the panel says so
  // rather than printing a confident number. A name with no radar row is never counted as flat.
  //
  // TWO ORDERS, ON PURPOSE (Jacob 2026-09-16: "are they listed as what rotation is likely next etc so
  // we are really ahead of the game"). `rank` answers "which of these is most REAL" — how much proof
  // there is that money already reaches the token. It is deliberately slow and it does not move with
  // the tape. `turning` answers a different question: which one is being bought FIRST, right now.
  // Neither is a prediction. `turning` is a measurement of what has already started, which is the only
  // honest form of "early" this desk has — and the breakout record (30 signals, mean −5.0%) is the
  // standing reminder that acting on it alone loses money.
  //
  // rs7 / rs30 = the narrative's median move MINUS BTC's, so a whole-market week cannot masquerade as
  //   a rotation. In an all-red tape "least down vs BTC" is the signal; raw percentages are not.
  // breadth = how many of the narrative's scanned names beat BTC over 7d. A median can be dragged by
  //   one runner; breadth is what separates a rotation from a single name going up.
  // turnover_x = the group's median turnover against the WHOLE scan's median. Above 1 means money is
  //   concentrating here relative to everything else being scanned.
  // Every one of these is null when it cannot be computed. A narrative with no scanned name gets nulls
  //   and sorts LAST, never a zero that quietly reads as "flat".
  const btcRadar = radarBySym.get('BTC') as { d7: number | null; d30: number | null } | undefined
  const btcD7 = Number.isFinite(Number(btcRadar?.d7)) ? Number(btcRadar!.d7) : null
  const btcD30 = Number.isFinite(Number(btcRadar?.d30)) ? Number(btcRadar!.d30) : null
  const scanTurnovers = ((radar.data ?? []) as { turnover: number | null }[])
    .map((r) => Number(r.turnover)).filter(Number.isFinite)
  const scanTurnoverMed = median(scanTurnovers)

  const narrBase = ((narr.data ?? []) as { rank: number; pick: string; syms: string[] | null }[]).map((n) => {
    const syms = (n.syms ?? []).filter(Boolean)
    const scanned = syms.filter((sym) => radarBySym.has(sym))
    const d7n = median(scanned.map((sym) => Number(radarBySym.get(sym)!.d7)).filter(Number.isFinite))
    const d30n = median(scanned.map((sym) => Number(radarBySym.get(sym)!.d30)).filter(Number.isFinite))
    const exposureUsd = syms.reduce((acc, sym) => acc + heldUsd(sym), 0)
    const beat = btcD7 == null ? null
      : scanned.filter((sym) => { const v = Number(radarBySym.get(sym)!.d7); return Number.isFinite(v) && v > btcD7 }).length
    const tnMed = median(scanned.map((sym) => Number((radarBySym.get(sym) as { turnover?: number | null }).turnover)).filter(Number.isFinite))
    return {
      ...n,
      d7: d7n, d30: d30n, scanned: scanned.length, universe: syms.length,
      held: syms.filter((sym) => heldUsd(sym) > 0),
      exposure_usd: exposureUsd,
      exposure_pct: bookUsd ? (exposureUsd / bookUsd) * 100 : null,
      rs7: d7n != null && btcD7 != null ? d7n - btcD7 : null,
      rs30: d30n != null && btcD30 != null ? d30n - btcD30 : null,
      breadth: beat, breadth_of: scanned.length,
      turnover_x: tnMed != null && scanTurnoverMed ? tnMed / scanTurnoverMed : null,
    }
  })

  // `turning` = 1..n on rs7 (then breadth share, then rs30). Computed here, never in the browser, so
  // every client sees the same order off the same scan.
  const turnOrder = [...narrBase].sort((a, b) =>
    (b.rs7 ?? -Infinity) - (a.rs7 ?? -Infinity)
    || ((b.breadth_of ? (b.breadth ?? 0) / b.breadth_of : -1) - (a.breadth_of ? (a.breadth ?? 0) / a.breadth_of : -1))
    || (b.rs30 ?? -Infinity) - (a.rs30 ?? -Infinity))
  const turningBy = new Map(turnOrder.map((n, i) => [n.rank, n.rs7 == null ? null : i + 1]))
  const narratives = narrBase.map((n) => ({ ...n, turning: turningBy.get(n.rank) ?? null }))

  const sectored = new Set(thesesRows.filter((t) => t.sector).map((t) => t.symbol))
  const unsectoredUsd = posSyms.filter((sym) => !sectored.has(sym)).reduce((s, sym) => s + heldUsd(sym), 0)

  return NextResponse.json({
    holdings: h.data ?? null,
    triggers: t.data ?? null,
    alerts: a.data ?? null,
    board: b.data ?? null,
    strategy: st.data ?? null,
    theses: th.data ?? null,
    orders: oo.data ?? null,                                    // null = unreachable, [] = genuinely nothing resting
    orders_synced_at: (ooAt.data as { value?: string } | null)?.value || null,
    orders_live: rhConfigured(),
    orders_sync_note: lastSyncNote,                                // false = the snapshot is only as fresh as the desk's last write
    book: unpriced.length ? null : posValue + cashUsd,
    pos_value: unpriced.length ? null : posValue,
    cash_usd: cashUsd,
    prices: Object.fromEntries(Object.entries(priced).map(([k, v]) => [k, v.usd])),
    price_src: Object.fromEntries(Object.entries(priced).map(([k, v]) => [k, v.src])),
    unpriced,
    radar: radar.data ?? null,
    flow: flow.data ?? null,
    narratives: narr.data ? narratives : null,                     // null = unreachable, [] = genuinely empty. Never conflated.
    narratives_benchmark: { btc_d7: btcD7, btc_d30: btcD30, scan_turnover_median: scanTurnoverMed },
    narratives_error: narr.error?.message ?? null,
    sectors,                                                      // #19 sector momentum, sorted by median d7
    unsectored_usd: unsectoredUsd,                                // held dollars in names with no sector on their thesis row
    loop_enabled: le.data ? String(le.data.value).toLowerCase() === 'true' : null,
    at: new Date().toISOString(),
  }, { headers: { 'Cache-Control': 'no-store' } })
}

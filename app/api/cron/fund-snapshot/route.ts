import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'
import { LLAMA, buildSnapshot, getJson, type LlamaOverviewRow, type LlamaProtocol } from '@/lib/desk/llama'

// FUND SNAPSHOT (daily, after 00:00 UTC): DeFiLlama free tier → fund_snapshots_daily (point-in-time),
// token_map (slug → gecko_id → symbol), and the Fear & Greed index → market_sentiment_daily.
// Re-running the same day overwrites that day's rows with a fresh observed_at. Data-only.

export const dynamic = 'force-dynamic'
export const maxDuration = 60

async function handle(req: Request) {
  const secret = req.headers.get('x-content-secret')
  if (!process.env.DAILY_CONTENT_SECRET || secret !== process.env.DAILY_CONTENT_SECRET) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  const sb = createServiceClient()
  if (!sb) return NextResponse.json({ error: 'db unavailable' }, { status: 503 })
  const date = new Date().toISOString().slice(0, 10)
  const notes: string[] = []

  // Fear & Greed first: tiny, independent, and the sweep rule's input.
  try {
    const fg = await getJson<{ data: { value: string; value_classification: string; timestamp: string }[] }>(LLAMA.fearGreed)
    const d = fg.data?.[0]
    if (d) {
      // available_at = the moment this collector captured the reading: the point-in-time timestamp a decision may use
      // (Phase 4 round 2, R-W #3b). Backfilled history carries NULL here and is unusable by rule.
      const now = new Date().toISOString()
      const { error } = await sb.from('market_sentiment_daily').upsert({ snapshot_date: new Date(Number(d.timestamp) * 1000).toISOString().slice(0, 10), fear_greed: Number(d.value), classification: d.value_classification, source: 'alternative.me/fng live (fund-snapshot collector)', observed_at: now, available_at: now }, { onConflict: 'snapshot_date' })
      if (error) notes.push(`sentiment: ${error.message}`)
    }
  } catch (e) { notes.push(`fear&greed: ${e instanceof Error ? e.message : e}`) }

  let protocols: LlamaProtocol[], fees: LlamaOverviewRow[], revenue: LlamaOverviewRow[], dexs: LlamaOverviewRow[]
  try {
    ;[protocols, fees, revenue, dexs] = await Promise.all([
      getJson<LlamaProtocol[]>(LLAMA.protocols),
      getJson<{ protocols: LlamaOverviewRow[] }>(LLAMA.fees).then((j) => j.protocols ?? []),
      getJson<{ protocols: LlamaOverviewRow[] }>(LLAMA.revenue).then((j) => j.protocols ?? []),
      getJson<{ protocols: LlamaOverviewRow[] }>(LLAMA.dexs).then((j) => j.protocols ?? []),
    ])
  } catch (e) {
    return NextResponse.json({ error: `defillama: ${e instanceof Error ? e.message : e}`, notes }, { status: 502 })
  }

  const { rows, tokenMap } = buildSnapshot(date, protocols, fees, revenue, dexs)
  const observed_at = new Date().toISOString()
  for (let i = 0; i < rows.length; i += 500) {
    const { error } = await sb.from('fund_snapshots_daily').upsert(rows.slice(i, i + 500).map((r) => ({ ...r, observed_at })), { onConflict: 'snapshot_date,llama_slug' })
    if (error) return NextResponse.json({ error: `fund_snapshots_daily: ${error.message}`, saved_before_error: i, notes }, { status: 500 })
  }
  for (let i = 0; i < tokenMap.length; i += 500) {
    const { error } = await sb.from('token_map').upsert(tokenMap.slice(i, i + 500).map((r) => ({ ...r, updated_at: observed_at })), { onConflict: 'llama_slug' })
    if (error) notes.push(`token_map: ${error.message}`)
  }
  return NextResponse.json({ date, protocols: protocols.length, saved: rows.length, token_map: tokenMap.length, with_gecko: tokenMap.filter((t) => t.gecko_id).length, notes })
}

export const GET = handle
export const POST = handle

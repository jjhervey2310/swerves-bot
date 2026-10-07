// Robinhood Crypto Trading API client (server only). Docs: https://docs.robinhood.com/crypto/trading/
// Auth: x-api-key + x-timestamp + x-signature, where the signature is Ed25519 over
//   `${apiKey}${timestamp}${path}${method}${body}`  (path includes the query string; body is the JSON text or '').
// Credentials come ONLY from Vercel env: RH_API_KEY and RH_PRIVATE_KEY (base64 — either the 32-byte seed
// or the 64-byte seed||pub form Robinhood's key script emits). Never logged, never returned to a client.
// Used by ONE caller: /api/fund/buy, which only runs when Jacob taps the button on the ROBINHOOD tab.
import { createPrivateKey, sign, randomUUID } from 'node:crypto'

const BASE = 'https://trading.robinhood.com'
const PKCS8_PREFIX = Buffer.from('302e020100300506032b657004220420', 'hex')

export function rhConfigured(): boolean {
  return !!(process.env.RH_API_KEY && process.env.RH_PRIVATE_KEY)
}

function key() {
  const raw = Buffer.from(process.env.RH_PRIVATE_KEY ?? '', 'base64')
  const seed = raw.length >= 32 ? raw.subarray(0, 32) : raw
  if (seed.length !== 32) throw new Error('RH_PRIVATE_KEY is not a 32- or 64-byte Ed25519 key')
  return createPrivateKey({ key: Buffer.concat([PKCS8_PREFIX, seed]), format: 'der', type: 'pkcs8' })
}

async function call<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const apiKey = process.env.RH_API_KEY
  if (!apiKey) throw new Error('RH_API_KEY missing')
  const ts = Math.floor(Date.now() / 1000).toString()
  const text = body === undefined ? '' : JSON.stringify(body)
  const sig = sign(null, Buffer.from(`${apiKey}${ts}${path}${method}${text}`), key()).toString('base64')
  const res = await fetch(`${BASE}${path}`, {
    method, cache: 'no-store',
    headers: { 'x-api-key': apiKey, 'x-timestamp': ts, 'x-signature': sig, 'Content-Type': 'application/json; charset=utf-8' },
    body: body === undefined ? undefined : text,
  })
  const j = (await res.json().catch(() => ({}))) as T & { detail?: string; errors?: unknown }
  if (!res.ok) throw new Error(`Robinhood ${method} ${path} → ${res.status}: ${j?.detail ?? JSON.stringify(j?.errors ?? j).slice(0, 300)}`)
  return j
}

export interface TradingPair { symbol: string; status: string; min_order_size: string; max_order_size: string; asset_increment?: string; quote_increment?: string }
export async function tradingPair(symbol: string): Promise<TradingPair> {
  const j = await call<{ results: TradingPair[] }>('GET', `/api/v1/crypto/trading/trading_pairs/?symbol=${symbol}-USD`)
  const p = j.results?.[0]
  if (!p) throw new Error(`${symbol}-USD is not a Robinhood pair`)
  return p
}

export interface BestBidAsk { symbol: string; price: string; bid_inclusive_of_sell_spread: string; ask_inclusive_of_buy_spread: string; buy_spread?: string; sell_spread?: string; timestamp?: string }
export async function bestBidAsk(symbol: string): Promise<BestBidAsk> {
  const j = await call<{ results: BestBidAsk[] }>('GET', `/api/v1/crypto/marketdata/best_bid_ask/?symbol=${symbol}-USD`)
  const q = j.results?.[0]
  if (!q) throw new Error(`no quote for ${symbol}-USD`)
  return q
}

export interface Order { id: string; state: string; side: string; type: string; symbol: string; average_price?: string | null; filled_asset_quantity?: string; created_at?: string; executions?: { effective_price: string; quantity: string; timestamp: string }[] }

/** Round DOWN to the pair's increment and format without float noise. */
export function quantize(qty: number, increment: string): string {
  const inc = Number(increment) || 1e-8
  const decimals = Math.max(0, (increment.split('.')[1] ?? '').length)
  const q = Math.floor(qty / inc + 1e-9) * inc
  return q.toFixed(decimals)
}

/** `clientOrderId` is the broker-side idempotency key: Robinhood rejects a second order with the same id,
 *  so a retried or double-submitted request cannot become two fills. */
export async function marketBuy(symbol: string, assetQty: string, clientOrderId: string = randomUUID()): Promise<Order> {
  return call<Order>('POST', '/api/v1/crypto/trading/orders/', {
    client_order_id: clientOrderId, side: 'buy', type: 'market', symbol: `${symbol}-USD`,
    market_order_config: { asset_quantity: assetQty },
  })
}

/** The protective stop the constitution requires on 100% of the units at fill. */
export async function stopLimitSell(symbol: string, assetQty: string, stopPrice: string, limitPrice: string): Promise<Order> {
  return call<Order>('POST', '/api/v1/crypto/trading/orders/', {
    client_order_id: randomUUID(), side: 'sell', type: 'stop_limit', symbol: `${symbol}-USD`,
    stop_limit_order_config: { asset_quantity: assetQty, stop_price: stopPrice, limit_price: limitPrice, time_in_force: 'gtc' },
  })
}

export async function getOrder(id: string): Promise<Order> {
  return call<Order>('GET', `/api/v1/crypto/trading/orders/${id}/`)
}

export interface OpenOrder {
  id: string; state: string; side: string; type: string; symbol: string; created_at?: string
  limit_order_config?: { asset_quantity?: string; limit_price?: string }
  stop_limit_order_config?: { asset_quantity?: string; stop_price?: string; limit_price?: string }
  stop_loss_order_config?: { asset_quantity?: string; stop_price?: string }
  market_order_config?: { asset_quantity?: string }
}

const OPEN_STATES = ['open', 'queued', 'confirmed', 'partially_filled', 'new', 'pending']

/** Every RESTING order at the broker (build request #14b). This is the only source that can say a
 *  level is actually armed: desk_triggers records what the desk MEANT to arm, which is a different
 *  claim and has disagreed with the broker before.
 *
 *  `seen` is how many orders the API returned in total, before filtering. The caller needs it: an
 *  empty `open` list from a key that can see NOTHING is a different fact from an empty list from a
 *  key that can see fifty closed orders, and only the second one means "nothing is armed". The first
 *  run of this shipped without that distinction and deleted a snapshot of seven live orders. */
export async function listOpenOrders(): Promise<{ orders: OpenOrder[]; closed: OpenOrder[]; seen: number; states: string[] }> {
  const byState = await call<{ results?: OpenOrder[] }>('GET', '/api/v1/crypto/trading/orders/?state=open')
    .catch(() => ({ results: undefined }))
  if (byState.results?.length) return { orders: byState.results, closed: [], seen: byState.results.length, states: ['open'] }
  // The state filter is not accepted on every account; fall back to the unfiltered page and filter here.
  // PAGINATE. The unfiltered list is paged, and on 2026-10-07 its first page carried only the three most
  // recent fills — so seven orders cancelled on 09-15 and 09-20 were never in `closed`, and the sync's
  // "remove only what the broker reports closed" rule kept them on the tab for three weeks. Follow `next`
  // for a bounded number of pages; every row on every page counts as mentioned by the broker.
  const rows: OpenOrder[] = []
  let path: string | null = '/api/v1/crypto/trading/orders/'
  for (let page = 0; page < 6 && path; page++) {
    const r: { results?: OpenOrder[]; next?: string | null } = await call('GET', path)
    rows.push(...(r.results ?? []))
    const nx = r.next ?? null
    path = nx ? (nx.startsWith('http') ? nx.replace(/^https?:\/\/[^/]+/, '') : nx) : null
  }
  const open = rows.filter((o) => OPEN_STATES.includes((o.state ?? '').toLowerCase()))
  return {
    orders: open,
    closed: rows.filter((o) => !OPEN_STATES.includes((o.state ?? '').toLowerCase())),
    seen: rows.length,
    states: [...new Set(rows.map((o) => (o.state ?? '?').toLowerCase()))].slice(0, 8),
  }
}

/** The price an open order rests at, whichever config it carries. Null when there is no level to
 *  show (a resting market order) — never 0, which would read as a real price. */
export function orderLevel(o: OpenOrder): number | null {
  const raw = o.stop_limit_order_config?.stop_price ?? o.stop_loss_order_config?.stop_price ?? o.limit_order_config?.limit_price
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

export function orderQty(o: OpenOrder): number | null {
  const raw = o.limit_order_config?.asset_quantity ?? o.stop_limit_order_config?.asset_quantity ?? o.stop_loss_order_config?.asset_quantity ?? o.market_order_config?.asset_quantity
  const n = Number(raw)
  return Number.isFinite(n) && n > 0 ? n : null
}

/** Poll until the order leaves the open states (max ~12s). Returns the last state seen. */
export async function awaitFill(id: string, tries = 12): Promise<Order> {
  let o = await getOrder(id)
  for (let i = 0; i < tries && ['queued', 'confirmed', 'partially_filled', 'open'].includes(o.state); i++) {
    await new Promise((r) => setTimeout(r, 1000))
    o = await getOrder(id)
  }
  return o
}

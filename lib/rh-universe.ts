// THE ROBINHOOD TRADEABLE UNIVERSE — the one list every desk surface checks a symbol against.
//
// Pulled from the broker's own pair catalog (get_currency_pairs, 91 pairs on 2026-10-03; this set was
// first captured 2026-08-23, stables removed). It is the answer to "can this account actually buy it",
// and it is NOT the same as "does Robinhood show a price for it". Robinhood publishes quote pages for
// coins it does not list — SPX6900 (found 2026-08-24) and GRASS (found 2026-10-03: a quote came back,
// a buy preview returned "no currency pair found") — so a price is never evidence of a listing. Coins
// on Robinhood Chain (ORBIO) are not listings either; the agentic account cannot reach them.
//
// Used by: the radar scan (which names get a fund_radar row), the timing grader (NOT ON ROBINHOOD is a
// hard bar, so an unlisted name can sit on the watch list with live numbers and a thesis but can never
// grade as buyable), and the watch-list row badge. Refresh this list when Robinhood lists or delists;
// the catalog changes rarely.
export const RH_SYMBOLS = new Set([
  'AAVE','ADA','AERO','ALGO','ARB','ASTER','ATOM','AVAX','AVNT','AXS','BAT','BCH','BILL','BIO','BNB',
  'BONK','BTC','CASHCAT','CC','CHIP','COMP','CRV','DOGE','DOT','EIGEN','ENA','ETC','ETH','FET','FLOKI',
  'FLR','GRAM','GRT','HBAR','HYPE','IMX','INJ','JTO','LDO','LINK','LIT','LTC','MEGA','MEW','MNT',
  'MOODENG','NEAR','ONDO','OP','ORCA','PENGU','PEPE','PNUT','POL','POPCAT','PYTH','QNT','RAY','RE',
  'RENDER','SEI','SENT','SHIB','SKR','SKY','SNX','SOL','STRK','SUI','SYRUP','TRUMP','UNI','VIRTUAL',
  'VVV','W','WIF','WLD','WLFI','XCN','XLM','XPL','XRP','XTZ','ZEC','ZORA','ZRO','ZRX','PUMP',
])

// WATCH-LIST NAMES ROBINHOOD DOES NOT LIST BUT KRAKEN DOES. Checked against api.kraken.com/0/public/
// AssetPairs on 2026-10-03: GRASSUSD and DRVUSD exist; ORBIO is on neither venue. Jacob buys these BY
// HAND on Kraken (2026-10-03: "we can get them on kraken") — the agentic Robinhood account cannot, so
// the buy button never fires for them, but the grade is computed on merit like everyone else and the
// row stays visible. A Kraken name can never take the pole seat: the pole is a standing pre-approved
// buy, and there is no executor for it.
export const KRAKEN_SYMBOLS = new Set(['GRASS', 'DRV', 'SUPER'])   // SUPERUSD confirmed 2026-10-03
// ON NO EXCHANGE WE USE, BUT ON A DEX. Jacob can buy these by hand with a wallet; nothing here can.
// Where, so the row can say it (CoinGecko tickers, 2026-10-03): ORBIO — Uniswap V4/V3 on Robinhood
// Chain, ~$8M/day (Jacob: "orbio might be on uniswap" — he was right). BP — Meteora and Raydium on
// Solana, or Backpack's own exchange; not on Coinbase.
export const DEX_SYMBOLS: Record<string, string> = {
  ORBIO: 'Uniswap on Robinhood Chain',
  BP: 'Meteora / Raydium on Solana, or Backpack Exchange',
}
export type Venue = 'robinhood' | 'kraken' | 'dex' | 'none'
export function venueFor(sym: string): Venue {
  const s = sym.toUpperCase()
  return RH_SYMBOLS.has(s) ? 'robinhood' : KRAKEN_SYMBOLS.has(s) ? 'kraken' : s in DEX_SYMBOLS ? 'dex' : 'none'
}

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

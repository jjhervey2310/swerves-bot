-- =============================================================
-- Crypto desk — Phase 1 data foundation (docs/CRYPTO-DESK-ARCHITECTURE.md §3, §4)
-- Applied 2026-10-02 via Supabase MCP apply_migration. Additive only: no existing table is touched.
-- Every table carries observed_at: a row is "the value for X as we saw it at observed_at", never "the value".
-- RLS is enabled with NO policies: anon/authenticated are denied; the service role (cron routes) bypasses.
-- =============================================================

-- ---------- unified OHLCV ----------
CREATE TABLE IF NOT EXISTS md_candles (
  venue            TEXT        NOT NULL,            -- coinbase | kraken | gate | …
  symbol           TEXT        NOT NULL,            -- base asset, e.g. BTC
  interval_minutes INT         NOT NULL,            -- 60 | 240 | 1440
  bar_time         TIMESTAMPTZ NOT NULL,            -- bar OPEN, UTC
  open  DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, volume DOUBLE PRECISION,
  observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (venue, symbol, interval_minutes, bar_time)
);
CREATE INDEX IF NOT EXISTS md_candles_sym_int_time ON md_candles (symbol, interval_minutes, bar_time DESC);
ALTER TABLE md_candles ENABLE ROW LEVEL SECURITY;

-- ---------- who was tradeable when ----------
CREATE TABLE IF NOT EXISTS universe_history (
  venue        TEXT NOT NULL,
  symbol       TEXT NOT NULL,
  product_id   TEXT,                                 -- venue pair id, e.g. BTC-USD
  status       TEXT,                                 -- online | delisted | offline | …
  trading_disabled BOOLEAN,
  first_seen   DATE NOT NULL DEFAULT CURRENT_DATE,   -- first day WE observed the product (not the listing date)
  delisted_at  DATE,                                 -- first day WE observed status = delisted (observed, not actual)
  first_bar    TIMESTAMPTZ,                          -- from md_candles — a proxy for listing, labelled as such
  last_bar     TIMESTAMPTZ,
  priority     SMALLINT NOT NULL DEFAULT 1,          -- 0 = held / core, 1 = online, 2 = delisted
  observed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (venue, symbol)
);
ALTER TABLE universe_history ENABLE ROW LEVEL SECURITY;

-- ---------- resumable backfill cursors ----------
CREATE TABLE IF NOT EXISTS md_backfill_cursor (
  venue            TEXT NOT NULL,
  symbol           TEXT NOT NULL,
  product_id       TEXT NOT NULL,
  interval_minutes INT  NOT NULL,
  next_end         TIMESTAMPTZ NOT NULL,             -- fetch window ends here, walking backwards
  target_start     TIMESTAMPTZ NOT NULL,             -- stop once the window start is at/before this
  done             BOOLEAN NOT NULL DEFAULT false,
  bars             INT NOT NULL DEFAULT 0,
  requests         INT NOT NULL DEFAULT 0,
  priority         SMALLINT NOT NULL DEFAULT 1,
  error            TEXT,
  head_synced_at   TIMESTAMPTZ,                      -- last forward-fill of the newest bars
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (venue, symbol, interval_minutes)
);
CREATE INDEX IF NOT EXISTS md_backfill_cursor_todo ON md_backfill_cursor (done, interval_minutes, priority, updated_at);
ALTER TABLE md_backfill_cursor ENABLE ROW LEVEL SECURITY;

-- ---------- point-in-time fundamentals (DeFiLlama free tier) ----------
CREATE TABLE IF NOT EXISTS fund_snapshots_daily (
  snapshot_date  DATE NOT NULL,
  llama_slug     TEXT NOT NULL,
  name           TEXT, symbol TEXT, gecko_id TEXT, parent TEXT, category TEXT, chains TEXT[],
  tvl NUMERIC, mcap NUMERIC, change_1d NUMERIC, change_7d NUMERIC,
  fees_24h NUMERIC, fees_7d NUMERIC, fees_30d NUMERIC,
  revenue_24h NUMERIC, revenue_7d NUMERIC, revenue_30d NUMERIC,
  dex_vol_24h NUMERIC, dex_vol_7d NUMERIC, dex_vol_30d NUMERIC,
  listed_at      TIMESTAMPTZ,
  source_vintage TEXT NOT NULL DEFAULT 'live',       -- live = pulled on snapshot_date; backfill-YYYY-MM = indicative only
  observed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (snapshot_date, llama_slug)
);
CREATE INDEX IF NOT EXISTS fund_snapshots_daily_sym ON fund_snapshots_daily (symbol, snapshot_date DESC);
ALTER TABLE fund_snapshots_daily ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS market_sentiment_daily (
  snapshot_date  DATE PRIMARY KEY,
  fear_greed     INT,
  classification TEXT,
  source         TEXT NOT NULL DEFAULT 'alternative.me',
  observed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  available_at   TIMESTAMPTZ                        -- when a decision may first use the reading: live capture time; NULL for backfilled history (unusable, Phase 4 round 2 R-W #3b)
);
ALTER TABLE market_sentiment_daily ENABLE ROW LEVEL SECURITY;
CREATE POLICY market_sentiment_public_read ON market_sentiment_daily FOR SELECT TO anon, authenticated USING (true);   -- research export with the publishable key (migration sentiment_available_at_and_anon_read, 2026-10-03)

-- ---------- join key: protocol -> token -> venue pairs ----------
CREATE TABLE IF NOT EXISTS token_map (
  llama_slug  TEXT PRIMARY KEY,
  name        TEXT, symbol TEXT, gecko_id TEXT, parent TEXT, category TEXT,
  gecko_source TEXT,                                 -- self | parent | null
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS token_map_symbol ON token_map (symbol);
ALTER TABLE token_map ENABLE ROW LEVEL SECURITY;

-- ---------- computed features (completed bars only; recomputed, never hand-edited) ----------
CREATE TABLE IF NOT EXISTS features_daily (
  symbol        TEXT NOT NULL,
  feature_date  DATE NOT NULL,
  venue         TEXT,
  bars          INT,
  close NUMERIC, ret_1d NUMERIC, ret_7d NUMERIC, ret_30d NUMERIC, ret_90d NUMERIC,
  vol_20d NUMERIC, vol_60d NUMERIC,                  -- annualised stdev of daily log returns
  sma20 NUMERIC, sma50 NUMERIC, sma200 NUMERIC, sma50_slope20 NUMERIC, sma200_slope20 NUMERIC,
  hi20 NUMERIC, lo20 NUMERIC, dist_hi20 NUMERIC, dist_hi50 NUMERIC, dist_hi200 NUMERIC, drawdown_365 NUMERIC,
  vol_ratio_7_30 NUMERIC, dollar_vol_24h NUMERIC,
  rs7_vs_btc NUMERIC, rs30_vs_btc NUMERIC,
  computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, feature_date)
);
ALTER TABLE features_daily ENABLE ROW LEVEL SECURITY;

-- ---------- component health (collector watchdog etc.) ----------
CREATE TABLE IF NOT EXISTS desk_health (
  component        TEXT PRIMARY KEY,
  status           TEXT NOT NULL,                    -- healthy | degraded | dead | unknown
  heartbeat_age_s  INT,
  data_age_s       INT,
  detail           JSONB,
  checked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  changed_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE desk_health ENABLE ROW LEVEL SECURITY;

-- ---------- discretionary watchlist with written theses (labelled, graded later) ----------
CREATE TABLE IF NOT EXISTS desk_watchlist (
  symbol        TEXT PRIMARY KEY,
  stage         TEXT NOT NULL,                      -- WATCH | EARLY | STRONG | BREAKOUT | AVOID | CLOSED
  thesis        TEXT NOT NULL,                      -- why this coin, in plain words
  entry_plan    TEXT, invalidation TEXT NOT NULL,   -- what makes us wrong, stated up front
  target        TEXT, horizon_days INT,
  confidence    SMALLINT,                           -- 0-100, calibrated later against outcomes
  base_rate_note TEXT,                              -- what a random coin of this type does over the horizon
  source        TEXT NOT NULL DEFAULT 'discretionary', -- discretionary | scanner (Phase 7)
  author        TEXT NOT NULL DEFAULT 'claude',
  written_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  active        BOOLEAN NOT NULL DEFAULT true
);
ALTER TABLE desk_watchlist ENABLE ROW LEVEL SECURITY;

-- Shadow paper ledger: every thesis becomes a tracked paper position so the calls get a hit-rate.
CREATE TABLE IF NOT EXISTS desk_paper_ledger (
  id            BIGSERIAL PRIMARY KEY,
  symbol        TEXT NOT NULL,
  side          TEXT NOT NULL DEFAULT 'long',
  opened_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  entry_px      NUMERIC NOT NULL, stop_px NUMERIC, target_px NUMERIC, size_usd NUMERIC NOT NULL DEFAULT 100,
  thesis_ref    TEXT,                               -- desk_watchlist.symbol at the time
  status        TEXT NOT NULL DEFAULT 'open',       -- open | closed
  closed_at     TIMESTAMPTZ, exit_px NUMERIC, exit_reason TEXT,  -- stop | target | invalidation | time | manual
  pnl_pct       NUMERIC,
  notes         TEXT
);
ALTER TABLE desk_paper_ledger ENABLE ROW LEVEL SECURITY;

-- =============================================================
-- Functions (SECURITY DEFINER so pg_cron can call them; owned by postgres)
-- =============================================================

-- One-off seed: kr_deep_candles -> md_candles (venues gate/kraken, 60/240/1440). Idempotent.
CREATE OR REPLACE FUNCTION md_seed_from_kr() RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE n INT;
BEGIN
  INSERT INTO md_candles (venue, symbol, interval_minutes, bar_time, open, high, low, close, volume, observed_at)
  SELECT venue,
         CASE WHEN regexp_replace(market, '(_USDT|USDT|USD)$', '') = 'XBT' THEN 'BTC' ELSE regexp_replace(market, '(_USDT|USDT|USD)$', '') END,
         interval_minutes, at, open, high, low, close, volume, now()
  FROM kr_deep_candles
  WHERE interval_minutes IN (60, 240, 1440)
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Refresh first_bar/last_bar on universe_history from md_candles (daily bars, any venue).
CREATE OR REPLACE FUNCTION universe_refresh_bars() RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE n INT;
BEGIN
  UPDATE universe_history u SET first_bar = m.first_bar, last_bar = m.last_bar, observed_at = now()
  FROM (SELECT venue, symbol, min(bar_time) first_bar, max(bar_time) last_bar FROM md_candles WHERE interval_minutes = 1440 GROUP BY venue, symbol) m
  WHERE m.venue = u.venue AND m.symbol = u.symbol
    AND (u.first_bar IS DISTINCT FROM m.first_bar OR u.last_bar IS DISTINCT FROM m.last_bar);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- Daily features from COMPLETED daily bars only (bar_time < p_date + 1 day). One preferred venue per symbol.
CREATE OR REPLACE FUNCTION compute_features_daily(p_date DATE DEFAULT (CURRENT_DATE - 1)) RETURNS INT LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE n INT;
BEGIN
  WITH src AS (
    SELECT DISTINCT ON (symbol) symbol, venue FROM md_candles
    WHERE interval_minutes = 1440 AND bar_time::date = p_date
    ORDER BY symbol, CASE venue WHEN 'coinbase' THEN 0 WHEN 'kraken' THEN 1 ELSE 2 END
  ), b AS (
    SELECT m.symbol, m.venue, m.bar_time::date d, m.open, m.high, m.low, m.close, m.volume
    FROM md_candles m JOIN src ON src.symbol = m.symbol AND src.venue = m.venue
    WHERE m.interval_minutes = 1440 AND m.bar_time >= (p_date - 400)::timestamptz AND m.bar_time < (p_date + 1)::timestamptz AND m.close > 0
  ), lr AS (
    SELECT *, ln(close / NULLIF(lag(close) OVER w, 0)) AS logret FROM b WINDOW w AS (PARTITION BY symbol ORDER BY d)
  ), w AS (
    SELECT symbol, venue, d, close, volume,
      count(*) OVER (w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) nbars,
      lag(close, 1) OVER w c1, lag(close, 7) OVER w c7, lag(close, 30) OVER w c30, lag(close, 90) OVER w c90,
      avg(close) OVER (w ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) sma20,
      avg(close) OVER (w ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) sma50,
      avg(close) OVER (w ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) sma200,
      max(high) OVER (w ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) hi20,
      max(high) OVER (w ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) hi50,
      max(high) OVER (w ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) hi200,
      min(low)  OVER (w ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) lo20,
      max(close) OVER (w ROWS BETWEEN 364 PRECEDING AND CURRENT ROW) hi365,
      avg(volume) OVER (w ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) v7,
      avg(volume) OVER (w ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) v30,
      stddev_samp(logret) OVER (w ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) sd20,
      stddev_samp(logret) OVER (w ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) sd60
    FROM lr WINDOW w AS (PARTITION BY symbol ORDER BY d)
  ), w2 AS (
    SELECT *, lag(sma50, 20) OVER w sma50_20ago, lag(sma200, 20) OVER w sma200_20ago FROM w WINDOW w AS (PARTITION BY symbol ORDER BY d)
  ), today AS (
    SELECT * FROM w2 WHERE d = p_date AND nbars >= 30
  ), btc AS (
    SELECT close, c7, c30 FROM today WHERE symbol = 'BTC' LIMIT 1
  )
  INSERT INTO features_daily (symbol, feature_date, venue, bars, close, ret_1d, ret_7d, ret_30d, ret_90d, vol_20d, vol_60d,
    sma20, sma50, sma200, sma50_slope20, sma200_slope20, hi20, lo20, dist_hi20, dist_hi50, dist_hi200, drawdown_365,
    vol_ratio_7_30, dollar_vol_24h, rs7_vs_btc, rs30_vs_btc, computed_at)
  SELECT t.symbol, t.d, t.venue, t.nbars, t.close,
    t.close / NULLIF(t.c1, 0) - 1, t.close / NULLIF(t.c7, 0) - 1, t.close / NULLIF(t.c30, 0) - 1, CASE WHEN t.nbars > 90 THEN t.close / NULLIF(t.c90, 0) - 1 END,
    t.sd20 * sqrt(365), CASE WHEN t.nbars >= 60 THEN t.sd60 * sqrt(365) END,
    t.sma20, CASE WHEN t.nbars >= 50 THEN t.sma50 END, CASE WHEN t.nbars >= 200 THEN t.sma200 END,
    CASE WHEN t.nbars >= 70 THEN t.sma50 / NULLIF(t.sma50_20ago, 0) - 1 END, CASE WHEN t.nbars >= 220 THEN t.sma200 / NULLIF(t.sma200_20ago, 0) - 1 END,
    t.hi20, t.lo20, t.close / NULLIF(t.hi20, 0) - 1, CASE WHEN t.nbars >= 50 THEN t.close / NULLIF(t.hi50, 0) - 1 END, CASE WHEN t.nbars >= 200 THEN t.close / NULLIF(t.hi200, 0) - 1 END,
    t.close / NULLIF(t.hi365, 0) - 1,
    t.v7 / NULLIF(t.v30, 0), t.close * t.volume,
    CASE WHEN b.close IS NOT NULL THEN (t.close / NULLIF(t.c7, 0) - 1) - (b.close / NULLIF(b.c7, 0) - 1) END,
    CASE WHEN b.close IS NOT NULL THEN (t.close / NULLIF(t.c30, 0) - 1) - (b.close / NULLIF(b.c30, 0) - 1) END,
    now()
  FROM today t LEFT JOIN btc b ON true
  ON CONFLICT (symbol, feature_date) DO UPDATE SET
    venue = EXCLUDED.venue, bars = EXCLUDED.bars, close = EXCLUDED.close, ret_1d = EXCLUDED.ret_1d, ret_7d = EXCLUDED.ret_7d, ret_30d = EXCLUDED.ret_30d, ret_90d = EXCLUDED.ret_90d,
    vol_20d = EXCLUDED.vol_20d, vol_60d = EXCLUDED.vol_60d, sma20 = EXCLUDED.sma20, sma50 = EXCLUDED.sma50, sma200 = EXCLUDED.sma200,
    sma50_slope20 = EXCLUDED.sma50_slope20, sma200_slope20 = EXCLUDED.sma200_slope20, hi20 = EXCLUDED.hi20, lo20 = EXCLUDED.lo20,
    dist_hi20 = EXCLUDED.dist_hi20, dist_hi50 = EXCLUDED.dist_hi50, dist_hi200 = EXCLUDED.dist_hi200, drawdown_365 = EXCLUDED.drawdown_365,
    vol_ratio_7_30 = EXCLUDED.vol_ratio_7_30, dollar_vol_24h = EXCLUDED.dollar_vol_24h, rs7_vs_btc = EXCLUDED.rs7_vs_btc, rs30_vs_btc = EXCLUDED.rs30_vs_btc, computed_at = now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- kr_* collector watchdog (docs/COLLECTOR-UNKNOWN.md). Data-only: reads two tables, writes one row.
CREATE OR REPLACE FUNCTION collector_health() RETURNS TABLE(status TEXT, heartbeat_age_s INT, data_age_s INT) LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE hb INT; da INT; st TEXT;
BEGIN
  -- Market-data freshness (2026-10-03: the kr_* collector tables were dropped under the Free-plan quota; this watches
  -- md_candles / md_backfill_cursor instead). hb = age of the newest daily head refresh; da = age of the newest completed daily bar.
  SELECT EXTRACT(EPOCH FROM now() - max(head_synced_at))::INT INTO hb FROM md_backfill_cursor WHERE interval_minutes = 1440;
  SELECT EXTRACT(EPOCH FROM now() - (max(bar_time) + interval '1 day'))::INT INTO da FROM md_candles WHERE venue = 'coinbase' AND interval_minutes = 1440;
  st := CASE WHEN hb IS NULL OR da IS NULL THEN 'unknown'
             WHEN hb > 7200 OR da > 172800 THEN 'dead'
             WHEN hb > 3600 OR da > 93600 THEN 'degraded'
             ELSE 'healthy' END;
  INSERT INTO desk_health (component, status, heartbeat_age_s, data_age_s, detail, checked_at, changed_at)
  VALUES ('market_data', st, hb, da, jsonb_build_object('source', 'md_candles coinbase 1440 / md_backfill_cursor heads'), now(), now())
  ON CONFLICT (component) DO UPDATE SET status = EXCLUDED.status, heartbeat_age_s = EXCLUDED.heartbeat_age_s, data_age_s = EXCLUDED.data_age_s,
    detail = EXCLUDED.detail, checked_at = now(), changed_at = CASE WHEN desk_health.status IS DISTINCT FROM EXCLUDED.status THEN now() ELSE desk_health.changed_at END;
  RETURN QUERY SELECT st, hb, da;
END $$;

-- One JSON for the DESK status tab. Read-only.
CREATE OR REPLACE FUNCTION desk_status() RETURNS JSONB LANGUAGE sql SECURITY DEFINER STABLE AS $$
  SELECT jsonb_build_object(
    'at', now(),
    'collector', (SELECT jsonb_build_object('host', host, 'last_beat', at, 'age_s', EXTRACT(EPOCH FROM now() - at)::INT, 'cycle', cycle, 'phase', phase) FROM kr_heartbeat ORDER BY at DESC LIMIT 1),
    'health', (SELECT COALESCE(jsonb_agg(to_jsonb(h)), '[]'::jsonb) FROM desk_health h),
    'md', (SELECT COALESCE(jsonb_agg(jsonb_build_object('venue', venue, 'interval', interval_minutes, 'rows', n, 'symbols', s, 'first', f, 'last', l) ORDER BY venue, interval_minutes), '[]'::jsonb)
           FROM (SELECT venue, interval_minutes, count(*) n, count(DISTINCT symbol) s, min(bar_time) f, max(bar_time) l FROM md_candles GROUP BY 1, 2) x),
    'backfill', (SELECT COALESCE(jsonb_agg(jsonb_build_object('interval', interval_minutes, 'done', d, 'total', t, 'bars', b, 'requests', r, 'errors', e) ORDER BY interval_minutes), '[]'::jsonb)
                 FROM (SELECT interval_minutes, count(*) FILTER (WHERE done) d, count(*) t, sum(bars) b, sum(requests) r, count(*) FILTER (WHERE error IS NOT NULL) e FROM md_backfill_cursor GROUP BY 1) x),
    'universe', (SELECT jsonb_build_object('online', count(*) FILTER (WHERE status = 'online'), 'delisted', count(*) FILTER (WHERE status = 'delisted'), 'total', count(*), 'last_sync', max(observed_at)) FROM universe_history),
    'fund', (SELECT jsonb_build_object('last_date', max(snapshot_date), 'rows_last', (SELECT count(*) FROM fund_snapshots_daily f2 WHERE f2.snapshot_date = (SELECT max(snapshot_date) FROM fund_snapshots_daily)), 'days', count(DISTINCT snapshot_date)) FROM fund_snapshots_daily),
    'sentiment', (SELECT to_jsonb(s) FROM market_sentiment_daily s ORDER BY snapshot_date DESC LIMIT 1),
    'features', (SELECT jsonb_build_object('last_date', max(feature_date), 'rows_last', (SELECT count(*) FROM features_daily f2 WHERE f2.feature_date = (SELECT max(feature_date) FROM features_daily)), 'days', count(DISTINCT feature_date)) FROM features_daily),
    'token_map', (SELECT jsonb_build_object('rows', count(*), 'with_gecko', count(*) FILTER (WHERE gecko_id IS NOT NULL)) FROM token_map),
    'watchlist', (SELECT COALESCE(jsonb_agg(to_jsonb(w) ORDER BY CASE w.stage WHEN 'BREAKOUT' THEN 0 WHEN 'STRONG' THEN 1 WHEN 'EARLY' THEN 2 WHEN 'WATCH' THEN 3 ELSE 4 END, w.updated_at DESC), '[]'::jsonb) FROM desk_watchlist w WHERE w.active),
    'paper', (SELECT jsonb_build_object('open', count(*) FILTER (WHERE status = 'open'), 'closed', count(*) FILTER (WHERE status = 'closed'),
              'wins', count(*) FILTER (WHERE status = 'closed' AND pnl_pct > 0), 'avg_pnl_pct', round(avg(pnl_pct) FILTER (WHERE status = 'closed'), 2),
              'rows', (SELECT COALESCE(jsonb_agg(to_jsonb(p) ORDER BY p.opened_at DESC), '[]'::jsonb) FROM (SELECT * FROM desk_paper_ledger ORDER BY opened_at DESC LIMIT 30) p)) FROM desk_paper_ledger),
    'cron', (SELECT COALESCE(jsonb_agg(jsonb_build_object('job', j.jobname, 'schedule', j.schedule, 'active', j.active, 'last_run', (SELECT max(start_time) FROM cron.job_run_details r WHERE r.jobid = j.jobid)) ORDER BY j.jobid), '[]'::jsonb) FROM cron.job j)
  );
$$;

-- Order-flow core schema. PostgreSQL 15+ (plain). See 0002 for TimescaleDB hypertables and policies.
-- Conventions: timestamps are timestamptz (UTC); prices are numeric (never float) in the
-- source of truth; quantities numeric(24,8); price rows are bigint = round(price / tick).

CREATE TABLE instruments (
    iid          text PRIMARY KEY,                 -- 'NSE:RELIANCE', 'DELTA:BTCUSD'
    symbol       text NOT NULL,
    exchange     text NOT NULL,
    provider     text NOT NULL,
    tick_size    numeric(18,8) NOT NULL CHECK (tick_size > 0),
    lot_size     numeric(18,8) NOT NULL DEFAULT 1 CHECK (lot_size > 0),
    tz           text NOT NULL DEFAULT 'UTC',
    active       boolean NOT NULL DEFAULT true,
    meta         jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX instruments_symbol_idx ON instruments (exchange, symbol);

CREATE TABLE sessions (
    iid          text NOT NULL REFERENCES instruments(iid),
    session_start timestamptz NOT NULL,
    session_end  timestamptz NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('regular','extended','crypto_day')),
    PRIMARY KEY (iid, session_start),
    CHECK (session_end > session_start)
);

CREATE TABLE trades (
    iid          text NOT NULL,
    ts           timestamptz NOT NULL,
    seq          bigint NOT NULL,
    price        numeric(24,8) NOT NULL CHECK (price > 0),
    qty          numeric(24,8) NOT NULL CHECK (qty > 0),
    side         smallint NOT NULL CHECK (side IN (-1,0,1)),   -- -1 bid-hit, 1 ask-lift, 0 unknown
    side_method  text NOT NULL CHECK (side_method IN ('exchange','quote_rule','tick_rule','lee_ready','none')),
    PRIMARY KEY (iid, ts, seq)
);

CREATE TABLE candles (
    iid          text NOT NULL,
    timeframe    text NOT NULL,
    ts_open      timestamptz NOT NULL,
    open         numeric(24,8) NOT NULL,
    high         numeric(24,8) NOT NULL,
    low          numeric(24,8) NOT NULL,
    close        numeric(24,8) NOT NULL,
    volume       numeric(24,8) NOT NULL DEFAULT 0,
    source       text NOT NULL,
    PRIMARY KEY (iid, timeframe, ts_open),
    CHECK (high >= low)
);

CREATE TABLE orderbook_snapshots (
    iid          text NOT NULL,
    ts           timestamptz NOT NULL,
    seq          bigint NOT NULL,
    bids         jsonb NOT NULL,                  -- [[price, qty], ...] best first
    asks         jsonb NOT NULL,
    PRIMARY KEY (iid, ts, seq)
);

CREATE TABLE footprint_bars (
    iid          text NOT NULL,
    timeframe    text NOT NULL,
    ts_open      timestamptz NOT NULL,
    tick_size    numeric(18,8) NOT NULL,
    open         numeric(24,8) NOT NULL,
    high         numeric(24,8) NOT NULL,
    low          numeric(24,8) NOT NULL,
    close        numeric(24,8) NOT NULL,
    volume       numeric(24,8) NOT NULL,
    delta        numeric(24,8) NOT NULL,
    cvd_close    numeric(24,8) NOT NULL,
    unknown_share real NOT NULL CHECK (unknown_share BETWEEN 0 AND 1),
    quality      text NOT NULL CHECK (quality IN ('exact','estimated','bar_approximated')),
    rows         jsonb NOT NULL,                  -- {"row": [bid_vol, ask_vol], ...}
    closed       boolean NOT NULL DEFAULT true,
    PRIMARY KEY (iid, timeframe, ts_open, tick_size)
);

CREATE TABLE profiles (
    iid          text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('volume','tpo')),
    scope        text NOT NULL CHECK (scope IN ('session','daily','weekly','composite')),
    period_start timestamptz NOT NULL,
    tick_size    numeric(18,8) NOT NULL,
    rows         jsonb NOT NULL,                  -- {"row": value}
    levels       jsonb NOT NULL,                  -- poc, vah, val, ib, nodes, single prints
    approximated boolean NOT NULL DEFAULT false,
    PRIMARY KEY (iid, kind, scope, period_start, tick_size)
);
CREATE INDEX profiles_lookup_idx ON profiles (iid, kind, scope, period_start DESC);

CREATE TABLE observations (
    id           bigint GENERATED ALWAYS AS IDENTITY,
    iid          text NOT NULL,
    kind         text NOT NULL,
    ts_start     timestamptz NOT NULL,
    ts_end       timestamptz NOT NULL,
    data_quality text NOT NULL,
    confidence   real NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    payload      jsonb NOT NULL,
    PRIMARY KEY (id, ts_start)
);
CREATE INDEX observations_iid_kind_idx ON observations (iid, kind, ts_start DESC);

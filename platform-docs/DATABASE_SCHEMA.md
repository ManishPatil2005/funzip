# Database Schema (design, PostgreSQL + TimescaleDB)

Conventions: `uuid` primary keys (v7 where available), `timestamptz` in UTC, money/price as `numeric`, every
tenant-owned table has `tenant_id` with row-level security, soft deletes via `deleted_at`, audit columns
`created_at, created_by, updated_at`.

## 1. Reference data

```sql
instrument (
  iid uuid pk, canonical_symbol text unique,        -- 'NSE:EQ:RELIANCE'
  segment text, isin text, name text,
  tick_size numeric not null, lot_size int, currency text,
  price_scale smallint not null default 0,          -- explicit unit scale, never inferred
  expiry date, strike numeric, option_type text,
  underlying_iid uuid references instrument,
  status text, valid_from date, valid_to date
);
provider_instrument_map (
  iid uuid references instrument, provider text, provider_token text, provider_symbol text,
  verified_at timestamptz, verification_note text,
  primary key (provider, provider_token)
);
instrument_symbol_history (iid, symbol, valid_from, valid_to);
trading_calendar (segment, session_date, open_utc, close_utc, is_holiday, special_session);
index_membership (index_iid, member_iid, valid_from, valid_to);   -- point-in-time universes
sector_map (iid, sector, industry, valid_from, valid_to);
corporate_action (id, iid, type, ex_date, ratio_num, ratio_den, cash_amount, source, verified bool);
adjustment_factor (iid, effective_date, factor numeric);          -- derived, versioned
```

## 2. Market data (Timescale hypertables)

```sql
bar (
  iid uuid, interval text, ts_open timestamptz,
  o numeric, h numeric, l numeric, c numeric, volume numeric, oi numeric,
  adjusted bool, data_version text, quality text,    -- exact | estimated | bar_approx
  primary key (iid, interval, ts_open, adjusted)
);  -- hypertable on ts_open, compression after 7 days, continuous aggregates for 5m/15m/1h/1d

tick (
  iid uuid, ts_exchange timestamptz, ts_received timestamptz,
  price numeric, qty numeric, side char(1), side_method text
);  -- hypertable, short retention (e.g. 7-30 days), then archived to Parquet

depth_snapshot (iid, ts, levels smallint, bids jsonb, asks jsonb);  -- sampled, short retention
feed_health_event (ts, provider, segment, state, detail jsonb, latency_ms);
data_quarantine (id, iid, series_ref, reason, ratio numeric, detected_at, resolved_at);
dataset_version (data_version text pk, created_at, source_manifest jsonb, row_counts jsonb);
```

Cold storage layout (Parquet): `bars/interval=1m/segment=NSE_EQ/year=2026/month=10/part-*.parquet`, queried by
DuckDB with partition pruning. Exports use the same layout plus a manifest.

## 3. Users, tenancy, access

```sql
tenant (tenant_id pk, name, plan, created_at);
app_user (user_id pk, tenant_id, email unique, password_hash, mfa_enabled, status, created_at);
role (role_id, name);  user_role (user_id, role_id, tenant_id);
api_key (key_id, tenant_id, user_id, hash, scopes text[], ip_allowlist cidr[], last_used_at, revoked_at);
provider_credential (
  cred_id, tenant_id, user_id, provider, label,
  ciphertext bytea, data_key_ref text, key_version int,     -- envelope encryption, never plaintext
  created_at, rotated_at, revoked_at
);
audit_log (
  seq bigserial pk, ts, tenant_id, actor_id, action, object_type, object_id,
  ip inet, diff jsonb, prev_hash bytea, hash bytea         -- hash chain
);
```

## 4. Scanner

```sql
scanner (scanner_id, tenant_id, owner_id, name, visibility, created_at);
scanner_version (
  scanner_id, version int, graph jsonb not null,           -- logic graph AST
  graph_hash bytea, note, created_at, created_by,
  primary key (scanner_id, version)
);   -- immutable once written
scan_run (
  run_id, scanner_id, version, universe_ref, as_of_date, data_version,
  started_at, finished_at, status, row_count, params jsonb
);
scan_result (run_id, iid, matched bool, features jsonb, context jsonb);   -- partitioned by run
export_job (export_id, run_id, format, status, object_url, manifest jsonb, expires_at);
template_share (template_id, scanner_id, version, share_scope, token_hash, created_at);
```

## 5. Backtesting

```sql
backtest (bt_id, tenant_id, scanner_id, version, kind, config jsonb, data_version, created_at);
backtest_run (run_id, bt_id, variant jsonb, seed, status, started_at, finished_at);  -- WF windows, MC seeds
backtest_trade (run_id, trade_id, iid, entry_ts, exit_ts, side, qty, entry_px, exit_px, costs, tags jsonb);
backtest_metric (run_id, name, value, scope);   -- scope: in_sample | out_of_sample | full
trial_ledger (tenant_id, scanner_id, trials int, updated_at);  -- how many variants were tried (overfitting control)
```

## 6. Learning

```sql
concept (concept_id, slug, title, summary, level, prerequisites uuid[]);
lesson (lesson_id, concept_id, version, body, status, reviewer, reviewed_at);
lesson_example (lesson_id, iid, session_date, annotations jsonb, data_version);   -- frozen examples
lesson_progress (user_id, lesson_id, status, score, updated_at);
```

## 7. Integrity rules
- `scanner_version` and `dataset_version` are immutable; edits create new versions.
- A `scan_run` or `backtest` always stores `data_version`; reproduction requires the same version.
- Foreign keys everywhere except hypertables (enforced by loaders and tests).
- Backups: PITR for Postgres, nightly Parquet snapshot, restore drill each quarter.

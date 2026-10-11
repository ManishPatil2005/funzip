-- TimescaleDB layer (optional). Requires the timescaledb extension; core tables work without it.
CREATE EXTENSION IF NOT EXISTS timescaledb;

SELECT create_hypertable('trades', 'ts', chunk_time_interval => INTERVAL '1 day');
ALTER TABLE trades SET (timescaledb.compress, timescaledb.compress_segmentby = 'iid', timescaledb.compress_orderby = 'ts, seq');
SELECT add_compression_policy('trades', INTERVAL '3 days');
SELECT add_retention_policy('trades', INTERVAL '90 days');
SELECT create_hypertable('candles', 'ts_open', chunk_time_interval => INTERVAL '30 days');
SELECT add_retention_policy('candles', INTERVAL '5 years');
SELECT create_hypertable('orderbook_snapshots', 'ts', chunk_time_interval => INTERVAL '6 hours');
ALTER TABLE orderbook_snapshots SET (timescaledb.compress, timescaledb.compress_segmentby = 'iid', timescaledb.compress_orderby = 'ts, seq');
SELECT add_compression_policy('orderbook_snapshots', INTERVAL '1 day');
SELECT add_retention_policy('orderbook_snapshots', INTERVAL '14 days');
SELECT create_hypertable('footprint_bars', 'ts_open', chunk_time_interval => INTERVAL '7 days');
SELECT add_retention_policy('footprint_bars', INTERVAL '2 years');
SELECT create_hypertable('observations', 'ts_start', chunk_time_interval => INTERVAL '30 days');

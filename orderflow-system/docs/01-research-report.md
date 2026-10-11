# 01 · Research Report — Order-Flow Charting Platforms

Evidence tags: **[S]** stated in a cited source · **[I]** my inference · **[U]** not verified (confirm before relying).
Sources (10): (1) GoCharting docs `gocharting.com/docs/orderflow/orderflow-in-gocharting` · (2) ATAS `learn.atas.net`, `help.atas.net` · (3) Sierra Chart numbers-bars threads (`nexusfi.com`, `optimusfutures.com`) · (4) Quantower `help.quantower.com` cluster chart · (5) Bookmap KB `bookmap.com/knowledgebase` + Connectivity PDF · (6) TradingView support `tradingview.com/support/solutions/43000726164` · (7) CME MDP 3.0 wiki (`cmegroupclientsite.atlassian.net`) · (8) Angel One SmartAPI docs/forum (`smartapi.angelone.in`) · (9) Delta Exchange docs (`docs.delta.exchange`, `api.india.delta.exchange`) · (10) TrueData market-data levels blog (`truedata.in`).

## 1. Methodology by platform

| Topic | GoCharting | ATAS | Sierra Chart | Quantower | Bookmap | TradingView |
|---|---|---|---|---|---|---|
| Volume source | Feed volume per price; footprint, delta, imbalance listed [S1] | Tick/trade data; configurable benchmarks and limits [S2] | Bid/ask volume per price from tick data (numbers bars) [S3] | Cluster chart with bid/ask, delta, volume modes [S4] | Trades overlaid on a depth heatmap [S5] | Footprint indicator built on **intrabar** lower-timeframe data [S6] |
| Buy/sell split | Aggressor from feed [U exact rule] | Aggressor from feed; classification depends on connection [U] | Bid/ask by trade vs prevailing quote [S3,I] | From feed aggressor [U] | Trade side from feed [U] | **Estimated** from intrabar direction → can differ from tick truth [S6] |
| Imbalance | Ratio-based [S1; default U] | Default ratio **150%** (configurable) [S2] | Diagonal ratio, configurable [S3] | Imbalance highlighting [S4; params U] | n/a (heatmap) | Default ratio **300%** [S6] |
| Large traders | Filters/bubbles [U] | Big-trade filters [U] | Volume-by-price filters [U] | Cluster filters [U] | Volume bubbles [S5] | Bubble indicators (community) [U] |
| Volume profile | Yes [S1] | Yes, many variants [S2] | Yes | Yes | Yes (VWAP/profile add-ons) [U] | Built-in VPVR / session [U] |
| Market profile (TPO) | Yes [U detail] | Yes | Yes | Yes | No | Yes (TPO charts, paid tiers [U]) |
| DOM / depth | Depth where feed has it [U] | DOM + cluster [U] | DOM + depth bars | DOM | Core product; heatmap colour red = high liquidity, dark = thin [S5] | None (no real depth) [I] |

Honest limit: rows marked **[U]** were not confirmed in the pages I could fetch; they reflect common industry convention and must be re-checked before they are quoted as fact.

## 2. Data-feed reality (decides what can be built)
- **CME [S7]**: MDP 3.0 carries an explicit aggressor-side flag (FIX tag 5797) and order-level detail → exact delta and true depth-by-order. This is the reference quality all footprint products assume.
- **Indian retail feeds [S8, S10]**: 1-second snapshot style ticks, no aggressor flag, depth usually 5 levels; tick-by-tick is not offered to retail. Footprint/delta here are therefore **estimates** (quote rule / tick rule).
- **Angel SmartAPI [S8]**: 20-level depth is beta; subscription token cap (about 1000 per connection); historical candle requests are capped (about 500 records). Access terms changed from 1 Apr 2026 (see Angel notice) [S].
- **Delta Exchange [S9]**: REST needs HMAC-SHA256 headers with a timestamp valid ~5 s; weight-based limit (~20,000 per 5 min); websocket channels include `trades`, `l2_orderbook`, `l2_updates`. Whether the trade payload carries a taker side is **[U]** and drives whether delta is exact.
- **Bookmap [S5]**: needs a feed with true depth; no Indian feed is listed in its connectivity document [S].

## 3. Comparison matrix — what each needs vs what we can supply

| Feature | Needs | Exact at CME | NSE/MCX via Angel | Crypto via Delta |
|---|---|---|---|---|
| Footprint bid/ask | Aggressor flag per trade | Yes | Estimated | Exact **if** taker side present [U], else estimated |
| Delta / CVD | Same | Yes | Estimated | as above |
| Diagonal imbalance | Same | Yes | Estimated | as above |
| Volume profile | Prices + volume | Yes | Yes from ticks; bar-approximated from candles | Yes |
| TPO / Market Profile | Price-time only | Yes | **Yes, fully** (needs only candles) | Yes |
| DOM / book imbalance | Depth | Full | 5 levels only | 20 levels [S9] |
| Heatmap | Depth history | Full | Coarse (5 lv, 1 s) | Moderate |
| Iceberg / spoof | Order-level data | Possible | Pattern-only, low confidence | Pattern-only |

## 4. Key conclusions
1. TPO and volume profile are fully implementable everywhere; delta-based features carry a mandatory **data-quality tier** outside CME.
2. Match TradingView's honesty about estimation: it labels intrabar estimates; we label every output EXACT / ESTIMATED / BAR_APPROXIMATED.
3. Imbalance ratio defaults differ by vendor (150% vs 300%); we default to 3.0 and expose it, because there is no universal value.
4. Heatmaps are only as good as the depth feed; we ship the algorithm but flag NSE/MCX as coarse.

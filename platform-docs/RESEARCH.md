# Phase 0 Research Study

Date: 2026-10-10. Scope: market research, competitor analysis, product vision, technical feasibility, data
infrastructure and API evaluation.

**Evidence tags used throughout**
- **[V]** verified this session from a fetched source (listed in the Sources section)
- **[A]** anecdotal: a practitioner forum or a vendor-authored article, treat with caution
- **[U]** general knowledge not re-verified this session; confirm before relying on it

---

## 1. Market research

**The problem worth solving.** Most retail traders lose money, and most tools help them act faster rather than
understand better. SEBI's own studies of individual equity F&O traders found that roughly nine in ten lost money
over the years studied [U]. Scanners, signal apps and indicator marketplaces serve the "what do I click" need.
Very few serve the "why does price move here" need. That gap is the product.

**Segments**

| Segment | Core need | Willingness to pay | Data need |
|---|---|---|---|
| Retail learner | Understand auction logic, structure, volume | Low to medium | EOD + delayed intraday is enough |
| Serious retail / prop-style | Validate ideas before risking capital | Medium | Real-time intraday, honest backtests |
| Professional / small fund | Research throughput, reproducibility | High | Tick/depth, long history, exports |
| Educators and communities | Teach with live examples | Medium (B2B2C) | Same as retail, plus sharing |
| Institutional | Audit trail, API, SSO | Highest | Licensed data, SLAs |

**Trends supporting the bet [U]:** growth in Indian demat participation, regulatory pressure on advice and
algos (SEBI retail algo framework effective 2026-04-01 [V]), crypto derivatives going on-shore in India, and LLMs
making no-code strategy creation realistic.

**What is genuinely hard (and therefore a moat if solved):** trustworthy data, honest backtests, and teaching
content that is accurate. None of the three is a UI problem.

---

## 2. Competitor analysis

| Platform | Strengths | Weaknesses / gaps | Evidence |
|---|---|---|---|
| **TradingView** | Best-in-class charting, 400+ indicators, 110+ drawing tools, huge script community, free tier; plans from free to $199.95/mo (annual billing) | Order flow is not its focus; learning is community-driven, not structured; backtesting limited to Pine; ads on free tier | [V] stockbrokers.com, pricingsaas |
| **GoCharting** | Footprint, CVD, Market Profile, DOM, strong Indian F&O fit | Backtesting needs scripting (Lipi); not no-code; footprint on Indian data is derived (see 5.3) | [A] AlgoTest article (vendor-authored, AlgoTest sells a competing product) |
| **TrendSpider** | Strategy lab, no-code bots, AI assistant, auto analysis | From about $82/mo, steep learning curve, no direct broker link, weak for Indian data | [V] stockbrokers.com |
| **Bookmap** | Liquidity heatmap, depth visualisation | Reportedly left India because Indian depth data was insufficient | [A] tradingqna thread |
| **ATAS / Quantower / Jigsaw / NinjaTrader** | Deep footprint, DOM, tape reading | Desktop apps; built for global futures; NSE connectivity unclear | [A] AlgoTest article |
| **AlgoTest** | No-code F&O backtests and deployment | No order flow; options-centric | [A] |
| **Chartink** | Simple, popular technical scanner for NSE | Mostly screening conditions, little education, limited backtesting | [U] |
| **Screener.in** | Fundamental screens, clean | Fundamentals only | [U] |
| **ODX Charts** | Order-flow-style charts for Indian markets | Not verified this session | [U] |
| **Sensibull / Opstra** | Options analytics | Options only | [U] |

**Pattern.** Every competitor optimises one of: charting, screening, order flow, or backtesting. None combines
*teaching + scanning + honest validation* with the data-quality labelling that order-flow claims need.

**Where this product should be different**
1. Every observation states its **data quality** (true aggressor data vs derived approximation).
2. Every scan or strategy comes with **a validation trail** (out-of-sample, trial count, costs).
3. Outputs are **context and scenarios with teaching notes**, never calls to buy or sell.
4. Scans are **reproducible**: same query, same as-of date, same data version, same result.

---

## 3. Product vision

> Teach traders how markets operate, and let them create, test and validate ideas using data.

Principles:
- **Understand before act.** Output explains the auction, not an order.
- **Honesty about data.** If delta is estimated, say so on the chart.
- **Falsifiable ideas.** Every idea can be turned into a testable query and judged by out-of-sample evidence.
- **Scalable ladder.** Same engine from a learner's first scan to a fund's API usage.
- **Provider-agnostic.** Data sources are replaceable; business logic never imports a broker SDK.

Non-goals (for now): order execution, copy trading, signal selling, portfolio advice.

---

## 4. Technical feasibility study

| Requirement from brief | Verdict | Why |
|---|---|---|
| Real-time NSE/BSE/MCX ticks | **Feasible** | Angel SmartAPI WebSocket 2.0 with LTP / Quote / Snap Quote modes [V] |
| 20-level market depth | **Partial** | Depth-20 mode exists but was described as beta, not for production [V] |
| True footprint / delta on NSE | **Not available as true data** | Practitioners report no aggressor tagging; delta is derived [A]. Build it, label it "estimated" |
| Bid/ask imbalance, absorption on NSE | **Partial** | Possible on quote + trade snapshots; lower fidelity than exchange L2/L3 |
| Spoofing / iceberg detection on NSE | **Research only** | Needs order-level (L3) data not available to retail APIs |
| Real order flow for crypto | **Feasible** | Delta Exchange exposes full L2 book, trades and candles channels [V] |
| Forex feeds | **Unresolved** | Delta docs read this session do not mention forex [V]. A second forex source is needed |
| 10 years of daily history | **Feasible** | Daily bars from NSE EOD files + corporate-action adjustment; Angel is rate-limited (see 6.1) |
| 10 years of intraday history | **Not feasible from Angel** | Candle API returns max 500 records per call [A, admin statement]; 1m data for years would take weeks of calls. Needs a paid historical vendor or own recording |
| Historical option chains (strike-wise OI) | **Record forward** | Strike-wise OI history must be captured from the live feed [V OIData] |
| Event and news backtests | **Hard** | Needs a licensed, point-in-time historical news archive |
| Natural language to strategy | **Feasible** | LLM emits a constrained logic-graph (JSON AST), validated, never code |
| ICT / SMC concepts (FVG, order blocks, sweeps) | **Feasible as defined rules** | These are discretionary; we implement explicit, documented definitions and say so |
| Kafka + Kubernetes from day one | **Not recommended** | Operational cost exceeds benefit until multi-tenant tick fan-out (see DECISIONS ADR-004) |
| Multi-tenant SaaS on one Angel account | **Likely prohibited / unsafe** | Redistribution needs exchange licensing (see 5.4). Use bring-your-own-keys per user |

---

## 5. Data infrastructure study

### 5.1 Data tiers (the central design idea)

| Tier | Contents | Sources | Honest labels |
|---|---|---|---|
| **A: true flow** | Trades with aggressor side, full L2 | Crypto (Delta), global futures vendors | `data_quality = exact` |
| **B: derived flow** | Ticks / quotes, side inferred by quote or tick rule | Angel WebSocket on NSE/MCX | `data_quality = estimated (method)` |
| **C: bars only** | OHLCV | Historical APIs, EOD files | `data_quality = bar-approximated` |

### 5.2 Storage plan
- **Hot:** Redis for last quote, latest bar, pub/sub, rate-limit buckets.
- **Warm:** PostgreSQL + TimescaleDB hypertables for ticks (short retention), 1m bars and continuous aggregates.
- **Cold / analytic:** Parquet in object storage, queried with DuckDB and Polars (columnar, cheap, reproducible).
- **Versioning:** every dataset has a `data_version` so scans and backtests can be re-run bit-for-bit.

### 5.3 Why order flow honesty matters
Forum evidence says Indian footprint and delta products are approximations built from tick and volume data [A].
The platform therefore never presents estimated delta as exchange truth. Charts carry a quality badge; teaching
notes explain what estimated delta can and cannot show.

### 5.4 Licensing and redistribution (a business-model constraint)
NSE Data & Analytics governs non-display use (algorithms, calculations) and redistribution of derived data through
separate agreements and fees; vendors and their clients can be required to sign [V, NSE Non-Display Policy]. The
policy lists no fee figures and no date, so costs must be requested from NSE Data. Consequences:
- A personal, self-hosted tool using your own broker login is the lowest-risk start.
- A multi-user SaaS must either (a) have every user connect their own broker keys, or (b) sign a vendor licence.
- Get a lawyer's opinion before the first paying user. This document is not legal advice.

### 5.5 Free end-of-day source
NSE publishes end-of-day "bhavcopy" files, and open-source downloaders exist [V, search results; format and
terms should be re-checked on NSE's site]. This is the proposed backbone for daily history, cross-checked against
broker candles, with corporate-action adjustment applied by us.

---

## 6. API evaluation

### 6.1 Angel One SmartAPI

| Topic | Finding | Evidence |
|---|---|---|
| Login | `generateSession(clientCode, password, totp)` returns a JWT (REST), refresh token and a feed token (WebSocket). **A PIN/password is needed in addition to the three keys you listed.** Sessions expire daily | [V] deepwiki, OIData |
| TOTP | Generated from the TOTP secret (pyotp). The secret plus PIN is enough to log in as the user | [V] |
| WebSocket modes | 1 LTP, 2 Quote (OHLC), 3 Snap Quote, 4 Depth (20 levels, beta) | [V] |
| Tokens per socket | A SmartAPI team member cited a 1000-token limit | [V] forum, wording is general |
| Large subscriptions | Users report dropped ticks and missing index tokens under load | [A] forum |
| Historical candles | 1-minute and above; **max 500 records per request** (admin); docs reportedly claim 30 days of 1m per request, which contradicts it | [V/A] forum |
| Rate limits (2024 forum table) | Candle data: 3/s, 180/min, 5000/hour. Quote: 10/s, 500/min, 5000/hour. Login: 1/s | [V] forum, dated 2024, re-check |
| Orders | 10 orders/second threshold; static IP mandatory for order execution from 2026-04-01; market and IOC orders not allowed for algos | [V] Angel One notice |
| Market-data-only use | Static IP rules are written about **order execution**; the notice does not address read-only data users | [V] absence, confirm with Angel support |
| Instruments | Daily master JSON, hundreds of thousands of rows, NSE + BSE + MCX | [V] OIData |

**Capacity maths.** Ten years of daily bars is about 2,500 candles, so 5 requests per symbol. For 2,000 symbols
that is 10,000 calls: at 5,000 per hour, about two hours plus headroom. One-minute history is 375 bars per NSE
session, so 500 candles covers about 1.3 sessions per call; years of 1m data across a universe is impractical,
hence the NSE EOD route for daily and forward-recording for intraday.

### 6.2 Delta Exchange (India)

| Topic | Finding | Evidence |
|---|---|---|
| Base URLs | Production `https://api.india.delta.exchange`; testnet `https://cdn-ind.testnet.deltaex.org`. The global URL belongs to Delta Global and is not for this API | [V] |
| Auth | Headers `api-key`, `signature`, `timestamp`, `User-Agent`; signature = HMAC-SHA256 over method + timestamp + path + query + body; **valid 5 seconds** | [V] |
| IP rules | Keys with trading permission require whitelisted IPs | [V] |
| Rate limit | 20,000 weight units per 5-minute window; market data weight 3; orders 5; history 10; batch 25; matching engine 500 ops/s per product | [V] |
| WebSocket | Public: `ob_l2`, `ob_l1`, `ob_updates`, `trades`, `ticker`, `candlesticks`, `mark_price`, `funding_rate`, `spot_price`. Private channels for orders, positions, margins | [V] |
| Products | Perpetual futures, dated futures, call and put options, INR spot pairs | [V] |
| Forex | Not mentioned in the portion read; last 21k characters unread | [V gap] |

### 6.3 Other providers considered (all behind the same interface)
Zerodha Kite, Upstox, Dhan (historical and websocket APIs with different limits [U]), Interactive Brokers,
Polygon, Binance, Rithmic/CQG (true futures order flow, paid [U]). None needs an architecture change if the
provider layer in `DATA_PROVIDER_LAYER.md` is followed.

---

## Sources
- Angel One SmartAPI rate-limit thread: https://smartapi.angelone.in/smartapi/forum/topic/4387/changes-in-api-rate-limit/4?lang=en-US
- Angel One notice, SmartAPI access from 2026-04-01: https://oga-prod.angelone.in/news/market-updates/what-s-changing-in-angel-one-s-smartapi-access-from-april-1-2026
- SmartAPI Python SDK overview: https://deepwiki.com/angel-one/smartapi-python
- OIData, Angel One market data guide: https://www.oidata.in/blog/angel-one-api-market-data
- SmartAPI depth-20 beta thread: https://smartapi.angelone.in/smartapi/forum/post/15422
- SmartAPI candle record cap: https://smartapi.angelone.in/smartapi/forum/post/13093
- Delta Exchange India API docs: https://docs.delta.exchange/
- NSE Non-Display Policy: https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Non_Display_Policy.pdf
- Order flow in India (forum): https://tradingqna.com/t/orderflow-trading-in-india/192774
- GoCharting alternatives (AlgoTest, vendor-authored): https://algotest.in/blog/best-gocharting-alternatives-in-india.md
- TradingView pricing: https://pricingsaas.com/companies/tradingview
- TrendSpider vs TradingView: https://www.stockbrokers.com/review/tools/trendspider-vs-tradingview
- SEBI 2026 static IP summary (developer blog, unverified): https://dev.to/shaktitiwari/sebi-2026-static-ip-mandate-retail-trader-compliance-guide-33mj

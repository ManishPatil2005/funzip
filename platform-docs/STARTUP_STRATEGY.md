# Startup Strategy

Figures below are hypotheses to test, not forecasts.

## 1. Positioning
"The place traders learn how markets work and validate ideas honestly." Not a signal service, not another
charting clone. Three promises: **trustworthy data, reproducible research, real teaching.**

Target order: Indian retail learners and serious retail first (B2C), educators and communities next (B2B2C),
prop desks and small funds after (B2B), global crypto traders via Delta Exchange as a second market.

## 2. Pricing models (illustrative)

| Tier | Audience | Included | Indicative price |
|---|---|---|---|
| Free | Learners | EOD scans, limited profile views, first lessons, 3 saved scanners | 0 |
| Pro | Serious retail | Intraday (own broker keys), full learning, backtests with quotas, exports | roughly Rs 700 to 1,500 per month |
| Team / Educator | Classes, communities | Shared workspaces, frozen annotated sessions, seats | per seat, roughly Rs 500 to 1,000 |
| Institutional | Desks, funds | API, higher quotas, audit logs, SSO, private data, SLAs | custom (contract) |

Anchors for comparison [V]: TradingView paid plans range from about USD 12.95 to 199.95 per month on annual
billing; TrendSpider starts around USD 82 per month. Add-ons: extra backtest compute, historical data packs.
Because data licences may dominate costs (ARCHITECTURE §6), price only after quotes from NSE Data and any
vendor.

## 3. Acquisition strategy
1. **Education-led content:** free, accurate explainers and annotated sessions (SEO and YouTube/Telegram style
   distribution in English and Hindi).
2. **Embeddable frozen examples:** educators embed annotated charts with attribution; every embed is a funnel.
3. **Community and creators:** partner with traders who teach; revenue share on team plans.
4. **College and bootcamp programmes:** discounted seats; student cohorts become advocates.
5. **B2B pilots:** small prop desks and research teams who value reproducibility and exports.
6. **Trust marketing:** publish methodology, definitions, data-quality statistics and incident reports openly.

## 4. Moat
- **Data advantage:** verified, versioned, point-in-time datasets and recorded intraday/option-chain history that
  accumulates over time (competitors cannot buy yesterday's recording).
- **Trust advantage:** quality labels and quarantine; users learn they can rely on what is shown.
- **Workflow advantage:** one graph object spanning teaching, scanning, backtesting and reports.
- **Education advantage:** a reviewed concept library and frozen examples with a clear methodology.
- **AI advantage:** natural language to validated graph with explain-back, evaluated continuously; not
  prediction, which is where most AI trading products overpromise.

## 5. Network effects
- Shared templates and forks (scanner gallery with validation badges: "out-of-sample tested", "trial count").
- Community-annotated sessions and journals (content that improves the platform).
- Educator ecosystems: each educator brings a cohort.
- Data flywheel: more users produce more demand for recorded depth, improving coverage (careful with licensing).

## 6. Community advantage
Moderated spaces, verified educator badges, reproducible-claims norm ("show the manifest"), public leaderboard
of **methodology quality**, not returns.

## 7. Business risks
- **Regulation:** SEBI advice/research rules and algo framework; mitigate with the language policy, no execution,
  legal opinion before launch.
- **Data licensing:** cost and permission; mitigate with BYO keys, phased scope, vendor negotiation.
- **Platform dependency:** broker API changes; mitigate with provider ports.
- **Competition:** TradingView adding order flow or education; mitigate with trust, reproducibility and
  depth in learning.
- **Trust incidents:** a wrong price chart damages credibility; mitigate with normalisation gates and visible
  quality labels.
- **Customer outcomes:** users losing money regardless of education; mitigate with honest messaging and risk
  education. Do not market returns.

## 7. Unit economics sketch (to be replaced by real quotes)
Gross margin depends mainly on data licence per user and LLM cost per active user. Controls: BYO keys for
intraday data, caching, quotas. Target at maturity: gross margin above 70% on Pro, to be validated.

## 8. First 90 days after Phase 1 (indicative)
Private beta with 20 to 50 traders and 2 educators; weekly feedback loop; publish methodology page; start the legal
and data-licensing workstream; measure activation (first scan, first lesson, first backtest).

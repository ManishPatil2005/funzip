# funzip

Three related projects, each in its own folder:

| Folder | What it is |
|---|---|
| `orderflow-system/` | Order-flow charting system: footprint, delta/CVD, volume profile, Market Profile, DOM/heatmap, observation-only detectors. FastAPI + React/TypeScript. See its README for status and honest limitations. |
| `stock-scanner/` | NSE/MCX scanner with strategy builder and Jim Dalton Market Profile (v1). |
| `platform-docs/` | Phase 0 research and architecture documents for the market-intelligence platform. |

Output across all projects is observational and educational: no BUY/SELL/HOLD instructions. Never commit `.env` files or broker credentials.

# DOA Agent — A Modular Sentiment Trader for Polymarket

A small, decoupled MVP that scrapes news, turns it into structured signals
with an LLM, computes a Bayesian posterior in pure Python, compares it to
live Polymarket prices, and (in paper mode) takes positions when the edge
clears a risk-gated threshold.

> **Status:** MVP. Ships in **PAPER-TRADING** mode by default — no wallet,
> no real money. LIVE trading is wired but intentionally unimplemented at
> the signing layer so you can't accidentally drain a wallet.

## Architecture (decoupled, restart-safe)

| Role | Module | Responsibility |
| --- | --- | --- |
| **Scout** | `app/modules/ingestion.py` | Pulls news from RSS feeds + CryptoPanic. Dedupes by URL. |
| **Quant** | `app/modules/intelligence.py` | LLM extracts structured fields → Bayesian update → posterior. |
| **Oracle** | `app/modules/market.py` | Polymarket Gamma + CLOB read-only data. Snapshots every cycle. |
| **Overseer** | `app/modules/risk.py` | Edge threshold, max size, drawdown kill switch. |
| **Trader** | `app/modules/execution.py` | Idempotent (UNIQUE `idem_key`) paper executor. |
| **Conductor** | `app/orchestrator.py` | One loop = Scout → Quant → Oracle → decide → risk → trade. |
| **Command Center** | `frontend/` | React dashboard: portfolio, PnL, signals, rationale, kill switch. |

### Core design principles applied
- **LLM is not the calculator.** The LLM only emits `{sentiment, confidence, topic, entities}`. The probability is computed in `bayesian_update()` in pure Python.
- **Idempotent execution.** Every trade plan derives a deterministic `idem_key = condition_id:outcome:signal_id`. The DB `UNIQUE` constraint absorbs duplicate fires from retries.
- **Single source of truth.** Every decision writes a `Trade` row joined to `Signal` → `NewsItem` and `MarketSnapshot`. Any losing trade is one SQL query away from a full post-mortem (the `/api/trade/{id}/rationale` endpoint powers the drawer in the UI).

---

## Prerequisites
- Python 3.11+
- Node 18+

## Backend setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # (optional — defaults work without any keys)
uvicorn app.main:app --reload --port 8000
```

The agent loop starts automatically on app startup. Visit `http://localhost:8000/healthz` to confirm. API docs at `http://localhost:8000/docs`.

### Free APIs used (zero-key path works)
- **Polymarket** Gamma + CLOB (public, no auth).
- **RSS** CoinDesk, Cointelegraph, Decrypt (no auth).
- **CryptoPanic** free tier (optional).
- **LLM** order of preference: `GROQ_API_KEY` (free, fast) → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY` → **heuristic keyword fallback** (no key needed).

With zero env keys, the agent still runs end-to-end using the heuristic NLP fallback. Add a Groq key for materially better signal quality.

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api` and `/healthz` to the backend on port 8000.

## Default reasonable assumptions

The user didn't lock these in, so the MVP defaults to:

1. **Market focus:** Crypto/DeFi events on Polymarket (keyword-filtered: bitcoin, ethereum, crypto, sec, etf, fed). Override via `MARKET_KEYWORDS` or pin specific markets in `WATCH_MARKETS`.
2. **Latency target:** Minutes-to-hours sentiment alpha, not HFT. The loop ticks every 30s (`LOOP_INTERVAL_SECONDS`).
3. **Wallet architecture:** Paper trading by default. `TRADING_MODE=LIVE` plus `WALLET_PRIVATE_KEY` is **gated by a `NotImplementedError`** in `execution._execute_live` until you wire a signed CLOB client.

## Going LIVE (when you're ready)

1. Implement `_execute_live` in `app/modules/execution.py` using `py-clob-client`:
   - Initialize the client with `WALLET_PRIVATE_KEY` + Polygon chain id `137`.
   - Build and sign a market order via the CLOB EIP-712 flow.
   - Capture the returned order id / tx hash on the `Trade` row.
2. Smoke-test against tiny sizes first (e.g. `MAX_USDC_PER_TRADE=1`).
3. Flip `TRADING_MODE=LIVE` and **monitor the kill switch**.

## Dashboard at a glance
- Top: portfolio stats + realized-PnL equity curve.
- Trade log — click any row to open the rationale drawer (the trade joined to its signal, source news, and market snapshot).
- Signals · markets · news streams updated every 5s.
- Decision log shows every rejection reason from the Overseer.
- Kill switch in the header halts trading immediately; auto-engages if daily drawdown breaches.

## File map

```
backend/
  app/
    main.py                # FastAPI app + lifespan + loop startup
    config.py              # Settings (env)
    database.py            # SQLAlchemy engine + session scope
    models.py              # NewsItem, Signal, MarketSnapshot, Trade, AgentState, LogEvent
    schemas.py             # Pydantic API models
    orchestrator.py        # The agent loop
    modules/
      ingestion.py         # Scout: RSS + CryptoPanic
      intelligence.py      # Quant: LLM extract + Bayesian update
      market.py            # Oracle: Polymarket Gamma + CLOB
      execution.py         # Trader: idempotent paper executor (+ live stub)
      risk.py              # Overseer: thresholds, kill switch
    api/
      routes.py            # Dashboard REST endpoints

frontend/
  src/
    App.tsx                # Layout + panels + kill switch
    api.ts                 # Typed API client
    components/
      Panel.tsx            # Card / Stat / Pill primitives
      EquityChart.tsx      # Recharts equity curve
      TradeDrawer.tsx      # Rationale drawer (Trade -> Signal -> News -> Snapshot)
```

## Deployment

The agent has a long-running background loop, so it needs an **always-on**
host. Free tiers that sleep (e.g. Render free) will pause the loop. The
recommended target is **Fly.io** — free tier, persistent volume for SQLite,
no sleep. The Dockerfile builds both frontend and backend into one image so
you ship a **single URL** that serves both the dashboard and the API.

### Deploy to Fly.io

One-time setup:

```bash
# Install flyctl
brew install flyctl                  # macOS
# OR: curl -L https://fly.io/install.sh | sh

fly auth signup                      # or `fly auth login`
```

Deploy:

```bash
cd <repo-root>

# 1. Reserve a globally unique app name + region (creates fly.toml metadata).
fly launch --no-deploy --copy-config --name <YOUR-APP-NAME> --region iad

# 2. Create the persistent volume (1GB free tier).
fly volumes create doa_data --size 1 --region iad

# 3. (Optional) set an LLM key as a Fly secret.
fly secrets set GROQ_API_KEY=...

# 4. Ship it.
fly deploy

# 5. Open the live URL.
fly open
```

Your dashboard is now at `https://<YOUR-APP-NAME>.fly.dev`. The SQLite DB
lives on the `/data` volume, so trade history survives redeploys.

### Other free options

| Platform | Verdict |
| --- | --- |
| **Render** (free) | Sleeps after 15 min idle → kills the agent loop. Avoid. |
| **Railway** | Works, but free tier is a one-time $5 credit. |
| **Hugging Face Spaces** | Free GPU/CPU spaces work for the API, but loops can be killed on inactivity. |
| **A $4/mo VPS** | DigitalOcean/Hetzner. Full control, no time limits. Use the same Dockerfile. |
| **Split deploy** | Frontend on Vercel + backend on Fly. Set `VITE_API_URL` and rebuild. Only worth doing if you outgrow single-deploy. |

### CI

`.github/workflows/ci.yml` runs on every push and PR:
- Backend: install deps, smoke-import the app, sanity-check Bayesian + heuristic.
- Frontend: `tsc --noEmit` + `vite build`.
- Docker: build the production image end-to-end.

## Troubleshooting

- **"No trades yet"** is normal — the Overseer requires `edge ≥ 0.08` and `confidence ≥ 0.55`. Drop them in `.env` for faster demo trades.
- **Empty market list** means none of the active Polymarket markets matched your keywords. Set `WATCH_MARKETS=<condition_id>` to pin a specific one.
- **Heuristic LLM provider** in the header means no Groq/OpenAI/Anthropic key was loaded. That's fine — quality drops but the loop runs.

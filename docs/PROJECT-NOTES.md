# Project Notes — polymarket-sentiment-agent

Working notes and changelog. The README is the user-facing document; this
file records what changed and why.

## Changelog

### 2026-07-13 — Deploy target migrated from Fly.io to Render

The old Fly.io deployment (poly-agent.fly.dev) was dead (TLS connection
reset) while still being linked as a live demo, and Fly.io is no longer a
supported host for these projects.

- Removed `fly.toml`; added `render.yaml` (Render Blueprint: Docker runtime,
  free plan, health check on `/healthz`, `autoDeploy` on push to main).
- Secrets (`X402_PAY_TO`, `GROQ_API_KEY`) are `sync: false` in the blueprint
  — entered in the Render dashboard, never committed.
- CORS default origin swapped from poly-agent.fly.dev to
  poly-agent.onrender.com (`app/config.py`, `.env.example`, `render.yaml`).
- README/CLAUDE.md deploy docs rewritten for the Render blueprint flow;
  all Fly commands and URLs removed.
- Known free-tier tradeoffs, documented rather than hidden: instance sleeps
  after ~15 min idle (agent loop pauses); no persistent disk, so the default
  SQLite DB is ephemeral. `DATABASE_URL` already supports any SQLAlchemy
  URL — Neon Postgres (free tier) is the documented production option. No
  new persistence layer was built.
- Verified locally before committing: fresh venv, full pytest suite, and a
  live `uvicorn` boot with a 200 from `/healthz`.
- Pending: actual Render deploy (owner login required), then replace the
  poly-agent.onrender.com placeholder with the real URL here, in README,
  CLAUDE.md, `render.yaml` CORS, and the portfolio site links.

### 2026-07-06 — Production hardening (committed 2026-07-13)

- Added 38-test backend pytest suite (Bayesian math, market-edge matching,
  risk gates, idempotent execution, LIVE-mode safety contract, API smoke
  tests); CI now runs it.
- Scoped CORS to explicit origins via `CORS_ORIGINS` (no `*` wildcard on a
  payment-handling API).
- README rewritten for honesty: paper-trading only, unvalidated signal (not
  proven alpha), testnet-only x402, SQLite durability limits.

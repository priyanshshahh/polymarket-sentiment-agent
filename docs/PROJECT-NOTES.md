# Project Notes — polymarket-sentiment-agent

Working notes and changelog. The README is the user-facing document; this
file records what changed and why.

## Changelog

### 2026-07-17 — Campaign 3: security hardening + track-record system (ported from signalrelay audit)

Per `docs/PORT-PLAN.md` and `docs/CODE-AUDIT.md`:

- Fixed `GET /api/portfolio` tz-naive/aware crash (SQLite round-trips
  `DateTime` columns as naive; the 24h cutoff was aware). Added a
  regression test with a real FILLED trade — the prior test suite only
  ever exercised the empty-portfolio path.
- Added `ADMIN_TOKEN` bearer auth (`app/auth.py`, `hmac.compare_digest`)
  on `/api/kill-switch`, `/api/loop/*`, and the new
  `/api/track-record/resolve` — fails closed (503) when unset, 401 on a
  wrong/missing token.
- x402 paywall now requires an explicit `X402_ENABLED=true` in addition
  to `X402_PAY_TO`, and validates the address is well-formed/non-zero at
  startup (`RuntimeError` otherwise) instead of silently activating on
  `bool(X402_PAY_TO)` alone.
- Clamped the Bayesian posterior away from exact 0/1 (mirrors the
  existing prior clamp) so an extreme update can't blow up `log()` in
  the new track-record scoring.
- `database.py` now normalizes `postgres://`/`postgresql://` URLs to
  `postgresql+psycopg2://` and auto-creates the SQLite parent dir;
  added the missing `psycopg2-binary` dependency.
- Added the track-record system: `PredictionRecord` /
  `MarketResolution` models, `app/modules/track_record.py` (Gamma
  resolution join, Brier/log-loss/calibration, `insufficient_data` gate
  below 10 resolved predictions), public `GET /api/track-record`,
  admin-gated `POST /api/track-record/resolve`. The paid
  `/api/trade/{id}/rationale` payload now also carries per-signal
  provenance and an honest x402 receipt/trust-model note. Adapted from
  the reference implementation: this repo has no `demo` column on any
  table (the demo-seeding layer was intentionally not ported — see
  `docs/PORT-PLAN.md`), so the ported models/module drop `demo`
  filtering entirely rather than carrying an always-false column.
- Added the two a11y CSS lines (`color-scheme: dark`, `touch-action:
  manipulation`) to `frontend/src/index.css`.
- Audit fixes: removed the dead `wallet_private_key` config field
  (nothing read it); fixed the README/CLAUDE.md "live demo" claim —
  `poly-agent.onrender.com` still 404s, so both now say "deploy
  pending" instead of asserting a dead URL is live.
- Backend test count: 38 -> 77 (all ported/adapted tests plus the new
  portfolio regression test). Frontend still builds clean (`tsc
  --noEmit` + `vite build`).
- Explicitly not ported (see `docs/PORT-PLAN.md` Skip section): the
  multi-page frontend rewrite, the demo-seeding layer, and
  signalrelay's `allow_methods=["*"]` CORS loosening — this repo keeps
  its stricter `["GET", "POST", "OPTIONS"]` allowlist.

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

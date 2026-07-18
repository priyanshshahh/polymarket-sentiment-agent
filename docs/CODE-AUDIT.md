# Code Audit — this repo's own weak spots

Scope: issues native to this repo, not covered by `docs/PORT-PLAN.md`
(that doc covers what to pull in from signalrelay's copy; this one is
what's wrong here independent of that). Light pass, top 5.

## 1. `GET /api/portfolio` will 500 on any real deployment with a filled trade

`backend/app/api/routes.py`, `portfolio()`, compares a timezone-aware
`cutoff` (`datetime.now(timezone.utc) - timedelta(hours=24)`) against
`Trade.created_at` values read back from SQLite, which come back
timezone-**naive** (confirmed by direct reproduction: a plain SQLAlchemy
`DateTime` column round-tripped through SQLite loses `tzinfo`, and
comparing it to an aware datetime raises `TypeError: can't compare
offset-naive and offset-aware datetimes`). `backend/tests/test_api.py` only
has `test_portfolio_empty` — no test ever populates a `FILLED` trade and
hits this comparison, so the bug is completely masked by the current test
suite despite `/api/portfolio` being the endpoint the dashboard polls every
5 seconds. This is the most urgent finding in this audit: the moment the
paper-trading loop actually fills one trade, the dashboard's portfolio
panel breaks. Signalrelay already fixed this (see PORT-PLAN item 1) —
recommend porting that fix directly rather than re-deriving it, and adding
a test that creates a `FILLED` trade with a real `created_at` before
hitting `/api/portfolio`.

## 2. Dead `wallet_private_key` config field

`backend/app/config.py:47` still declares `wallet_private_key: str = ""`
and `backend/.env.example` still documents `WALLET_PRIVATE_KEY=`. Nothing
in `backend/app/` reads `settings.wallet_private_key` — the only reference
left is inside a README code sample (`README.md` around line 583) showing
*hypothetical* future signer code, not anything actually wired up.
Signalrelay already recognized this as dead weight and removed it
(`ff76f1d`, "Drop the inert WALLET_PRIVATE_KEY setting"). Low risk, but
worth deleting here directly — it's a footgun-shaped placeholder (a secret
field that looks load-bearing but isn't) sitting in a settings class for a
payment-adjacent service.

## 3. "Live demo" claim doesn't match reality

The README's top badge row and opening line claim a **live demo** at
`https://poly-agent.onrender.com` (`README.md` lines 4 and 7), and
`CLAUDE.md` repeats "Live app: https://poly-agent.onrender.com". Checked
directly: both `https://poly-agent.onrender.com/` and `/healthz` currently
return HTTP 404. This is consistent with `docs/PROJECT-NOTES.md`'s own
changelog entry, which says the Render deploy is still **pending** ("owner
login required... replace the poly-agent.onrender.com placeholder with the
real URL"). The README's own "Status & honest results" section
half-acknowledges this further down ("the public URL goes live once that
blueprint is deployed") but the badges and opening paragraph above it still
read as an unconditional liveness claim. Given this repo's whole stated
ethos is "honest README, no overclaiming" (commit `b5e3c90`), this is the
one place that ethos isn't being applied to itself. Fix: either remove the
live-demo badge/links until the Blueprint is actually deployed and verified,
or move the caveat up above the fold instead of burying it in the status
section.

## 4. No frontend tests at all

`frontend/package.json` has no `test` script and there's no `*.test.*` /
`*.spec.*` file anywhere under `frontend/src`. The backend has a genuinely
solid 38-test suite; the frontend (`App.tsx`, `TradeDrawer.tsx`,
`EquityChart.tsx`, `api.ts`) has zero coverage — a broken `api.ts` fetch
path or a crash in the trade-rationale rendering would only surface as a
runtime error in the browser. Given the frontend is a small, single-page
dashboard (not the focus of this audit's ranked risk), this is noted but
not scored as urgent as items 1-3 — a handful of smoke tests on `api.ts`'s
response parsing would be the highest-leverage addition if this gets
picked up.

## 5. CI's "38 backend tests" claim in README is currently accurate but fragile to drift

`README.md` states "Tests: 38 backend pytest tests..." as a specific,
checkable number (confirmed by this audit's own test run — see below). That
specificity is good practice, but it's the kind of claim that silently goes
stale the next time a test is added or removed without updating the
README, and nothing enforces it (no test that asserts count, no CI check
comparing README to `pytest --collect-only`). Not a bug, just a known decay
point to watch — if a port from `docs/PORT-PLAN.md` (e.g. `ADMIN_TOKEN` or
track-record tests) is merged, update this line in the same commit.

## Baseline test run

```
cd backend && .venv/bin/python -m pytest
...
38 passed in 0.36s
```

Python 3.12.4 (`backend/.venv`), confirms the README's "38 backend pytest
tests" claim exactly. Baseline is green; nothing in this audit required
changing test files.

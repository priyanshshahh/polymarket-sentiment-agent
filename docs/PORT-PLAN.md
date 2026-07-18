# Port Plan — signalrelay's polymarket-sentiment-agent → this repo

Comparison date: 2026-07-17. Compared this repo (`render-migration` @ 6f29166)
against the embedded copy at `signalrelay/polymarket-sentiment-agent`
(`prod-hardening` @ 9c6c944). Not a shared git history — this is a file-level
diff of `backend/app/*` and the top-level configs. Signalrelay was read-only;
nothing there was touched.

`app/modules/execution.py`, `ingestion.py`, `market.py`, and `risk.py` are
byte-identical between the two repos. Everything else in `backend/app/`
diverged. The frontend diverged much more: signalrelay rewrote the
single-page dashboard into a `react-router-dom` multi-page app
(`pages/Dashboard.tsx`, `PitchDeck.tsx`, `TrackRecord.tsx`, `X402Lab.tsx`,
`components/Layout.tsx`), on top of a separate "demo data" seeding layer
(`seed_demo.py`, `seed_history.py`, a `demo` boolean on every table,
`docker-entrypoint.sh`, `SEED_DEMO` env var) that predates and is unrelated
to Campaign 3. Treat those two things as a different, bigger initiative than
"port Campaign 3" — see Skip section.

## Ranked port list

### 1. Fix `/api/portfolio` timezone crash — S — do this first
**Source:** `signalrelay/.../backend/app/api/routes.py`, `portfolio()`
(the `_naive()` helper and the `.replace(tzinfo=None)` on `cutoff`).

This repo's `portfolio()` computes `cutoff = datetime.now(timezone.utc) -
timedelta(hours=24)` (tz-aware) and compares it against `Trade.created_at`
read back from SQLite (tz-**naive** — SQLAlchemy's plain `DateTime` column
strips tzinfo on SQLite round-trip). Confirmed by direct reproduction:
comparing a fresh-from-DB naive datetime against an aware `cutoff` raises
`TypeError: can't compare offset-naive and offset-aware datetimes`. This
repo's test suite only exercises the *empty* portfolio (`test_portfolio_empty`
in `backend/tests/test_api.py`) so it never hits this path. In any real run
where the agent has filled a trade, `GET /api/portfolio` — the endpoint the
dashboard polls every 5 seconds — will 500. This isn't a Campaign-3 feature,
it's a latent bug signalrelay happened to fix while touching the same
function; port the fix on its own, independent of everything else here.

### 2. `ADMIN_TOKEN` bearer auth on control endpoints — S
**Source:** `signalrelay/.../backend/app/auth.py` (new file, `require_admin_token`),
`config.py` (`admin_token` field), `api/routes.py` (`Depends(require_admin_token)`
on `/api/kill-switch`, `/api/loop/run-once`, `/api/loop/start`, `/api/loop/stop`).

Right now those four routes are wide open on this repo — CORS restricts
*browsers*, not `curl`. Anyone who can reach the port can flip the kill
switch or force a trading cycle. The signalrelay fix is a single
`Header`-based dependency using `hmac.compare_digest`, and it fails closed
(503, not open) when `ADMIN_TOKEN` is unset — no risk of silently
"auth-off" behavior if you forget to set it. Bring `tests/test_admin_auth.py`
along; it's the spec for the 503/401/200 behavior.

### 3. x402 pay-to validation + explicit `X402_ENABLED` flag — S
**Source:** `signalrelay/.../backend/app/x402_setup.py` (`validate_pay_to`),
`config.py` (`x402_enabled` field).

Today this repo activates the paywall purely on `bool(settings.x402_pay_to)`
— a typo'd or zero address silently starts a "paid" endpoint that either
can't collect or collects to a burned address, and nothing tells you at
boot. Signalrelay's version requires an explicit `X402_ENABLED=true` *and*
validates the address is a well-formed, non-zero `0x...` string, raising a
hard `RuntimeError` at startup otherwise. `.github/workflows` CI and
`render.yaml`/env docs need one line each for the new var. Bring
`tests/test_paywall.py`.

### 4. Posterior clamp in the Bayes update — XS
**Source:** `signalrelay/.../backend/app/modules/intelligence.py`, one line:
`posterior = min(max(posterior, 1e-4), 1 - 1e-4)` after the log-odds update.

Prevents an extreme prior/likelihood-ratio combination from rounding to an
exact 0.0 or 1.0, which would break edge math and (once track-record scoring
exists) blow up `log()` in log-loss. Zero behavioral risk, no dependencies.
Pure win, do it regardless of anything else on this list.

### 5. Postgres URL normalization + SQLite dir bootstrap — S
**Source:** `signalrelay/.../backend/app/database.py`
(`normalize_db_url`, `_prepare_sqlite_dir`, `pool_pre_ping=not sqlite`).

This repo's own README and `render.yaml` already tell operators to "point
`DATABASE_URL` at Postgres (Neon free tier) for durability" — and
`psycopg2-binary` is already in `requirements.txt` — but `database.py` never
normalizes the `postgres://`/`postgresql://` scheme that Neon/Render hand
out to the `postgresql+psycopg2://` dialect SQLAlchemy 2.x actually needs.
Following the repo's own documented advice today would fail at
`create_engine`. Also ports the `./data/` directory auto-create (this repo's
`config.py` default is `sqlite:///./doa.db` at the CWD root instead of
`./data/doa.db` — either update the default to match the Dockerfile's
`/data` convention, or keep this repo's default and just port the
dir-creation logic generically). Low risk, no schema change.

### 6. Per-signal provenance + x402 receipt trust-model note in `trade_rationale` — S
**Source:** `signalrelay/.../backend/app/api/routes.py`, `trade_rationale()`
(the `provenance` dict and `x402_receipt` block), plus `orchestrator.py`'s
`_model_version()` helper.

Adds which model/version produced a probability and an honest paragraph
explaining that the server does *no* local payment verification — the
facilitator does, and the trust model is "verify the tx hash yourself." This
is exactly the kind of disclosure this repo's README already goes out of its
way to make elsewhere (the "Status & honest results" section) — it's a
natural extension of that stance and is genuinely $0 in dependencies if you
skip item 7 (drop the `"track_record_endpoint": "/api/track-record"` line
from the payload, or add it once item 7 lands).

### 7. Full track-record system — M/L
**Source:** `signalrelay/.../backend/app/models.py` (`PredictionRecord`,
`MarketResolution` classes), `backend/app/modules/track_record.py` (new
module: Gamma resolution join, Brier/log-loss/calibration, `insufficient_data`
gate), `orchestrator.py` (`_log_prediction` hook in the main loop), 2 new
routes in `api/routes.py` (`GET /api/track-record`, `POST
/api/track-record/resolve`).

This is the single highest-value item on the list because it directly
answers this repo's own README caveat: *"the edge is an unvalidated signal
... has not been backtested or validated against realized outcomes."* The
track-record system makes that falsifiable instead of an assertion. It's
M/L, not S, because:
- New tables need a migration story. This repo has no Alembic/migration
  tool — `database.py` relies on SQLAlchemy `create_all()`, which only
  creates *missing* tables and won't touch existing ones. That's actually
  fine for adding two brand-new tables (no ALTER needed), but confirm no
  local dev `doa.db` files with stale schema are relied upon before
  deploying.
- `track_record.py`'s `compute_track_record()` and `backfill_from_trades()`
  both filter/tag on a `demo: bool` column on `PredictionRecord` and `Trade`.
  This repo has **no** `demo` column anywhere (see Skip, below) — either add
  a minimal `demo` column (default `False`, never set to `True`, so the
  `include_demo` query param becomes permanently inert) purely to keep the
  ported module's shape, or — cleaner — strip the demo filtering out of the
  ported copy entirely and hardcode "score everything." Recommend the
  latter: don't import a boolean you'll never populate.
  - Also note `PredictionRecord.demo` uses `bool(getattr(sig, "demo",
    False))` when logging from `orchestrator.py` — that `getattr` fallback
    means it's harmless even if `Signal.demo` doesn't exist, but simplest is
    to just drop the field from the ported model.
- Depends on item 6's `_model_version()` helper (small, port together).
- Bring `tests/test_track_record.py` (164 lines) — it's the spec for
  `parse_resolution()`'s "require ≥0.99 settlement price" decisiveness rule
  and the `insufficient_data` threshold behavior; don't skip it, the scoring
  math is easy to get subtly wrong (see the `_EPS` clamp in `_log_loss`,
  mirrors item 4's clamp).
- Frontend: **don't** pull in signalrelay's `pages/TrackRecord.tsx` +
  `react-router-dom` + `Layout.tsx` wholesale (see Skip). If you want the
  data visible, add it as a panel/tab inside the existing single-page
  `App.tsx`, reusing `api.ts`'s `TrackRecord`/`TrackRecordRow`/
  `CalibrationBin` types (those are cleanly copyable — no router
  dependency).

### 8. Two-line a11y CSS — XS
**Source:** `signalrelay/.../frontend/src/index.css`: `html { color-scheme:
dark; }` (correct dark-mode form controls/scrollbars) and `a, button,
[role="button"] { touch-action: manipulation; }` (drops the 300ms mobile tap
delay). These two lines are the only a11y-relevant change that lives outside
the page-split refactor — genuinely free to take, no dependency on anything
else.

## Skip (and why)

- **The multi-page frontend rewrite** (`react-router-dom`, `Layout.tsx`,
  `pages/Dashboard.tsx`, `pages/PitchDeck.tsx`, `pages/X402Lab.tsx`). This is
  a product decision (pitch-deck page, an "X402 Lab" explainer/demo page),
  not a Campaign-3 hardening item, and it's the majority of signalrelay's
  frontend diff. This repo is a lean single-page dashboard; adopting a
  router + a pitch-deck page for it is scope creep the README's own "research
  scaffold, not a product" framing argues against. Skip unless someone
  explicitly wants this repo repositioned as a demo/pitch artifact.
- **The `demo` seeding infrastructure** (`demo` boolean on every table,
  `seed_demo.py`, `seed_history.py`, `docker-entrypoint.sh`'s `SEED_DEMO`
  branch, `/api/demo/rationale` teaser endpoint, `DemoTeaser` UI in
  `TradeDrawer.tsx`). This exists so signalrelay's dashboard looks populated
  for demos/pitches out of the box. This repo's README explicitly stakes out
  the opposite position — "any paper PnL shown is... not evidence... treat
  it as a research scaffold, not a money printer" — seeding illustrative
  fake trades to make the dashboard look busier cuts against that stance.
  Skip entirely; if item 7 needs a `demo` field, see the recommendation
  there to drop it instead.
- **`allow_methods=["*"]` in CORS middleware.** This is a regression, not an
  upgrade — signalrelay's `main.py` loosened this repo's explicit
  `["GET", "POST", "OPTIONS"]` allowlist to a wildcard, and dropped the
  Render production origin from the default `cors_origins` list (now
  localhost-only by default, relying on the dashboard `CORS_ORIGINS`
  env var being set correctly at deploy time). `signalrelay`'s own
  `test_cors.py` never asserts on `allow_methods`, so this looks like an
  unintentional loosening while renaming `cors_origins_list` →
  `cors_origin_list`, not a deliberate hardening. **Do not port this**; this
  repo's tighter version is the better one to keep.
- **`wallet_private_key` removal** — not really "porting FROM signalrelay,"
  but noting here since it's adjacent: signalrelay already dropped this
  dead setting (commit `ff76f1d`, "Drop the inert WALLET_PRIVATE_KEY
  setting"). This repo still has it; see `docs/CODE-AUDIT.md` item 1 — fix
  it here directly rather than "porting" anything.

## Render deploy specifics (this repo, not signalrelay's)

- This repo's `render.yaml` service is named `poly-agent` at the repo root
  (not `rootDir: polymarket-sentiment-agent` — signalrelay's blueprint sets
  `rootDir` because it's a subdirectory of a monorepo; this repo's blueprint
  should NOT copy that key).
- `render.yaml` here does not declare `ADMIN_TOKEN` or `X402_ENABLED` at
  all. If items 2 and 3 are ported, add both as `sync: false` env var
  entries (secrets set in the dashboard) so a fresh Blueprint deploy prompts
  for them instead of silently running with admin routes disabled (503) and
  the paywall off.
- `DATABASE_URL` here defaults to `sqlite:////data/doa.db` in the Dockerfile
  and `render.yaml`, but `config.py`'s Python-level default is
  `sqlite:///./doa.db` (repo root, not `/data`) — the two defaults already
  disagree before any porting; worth reconciling regardless of item 5.

## Effort key
S = under an hour, self-contained. M = a few hours, touches 2-3 files plus
tests. L = half a day+, schema/architecture implications.

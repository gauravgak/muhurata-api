# Muhurata — workspace guide for Claude

Two projects, deployed separately:

- **`muhurata-site-11/`** — the public site. Static HTML/CSS/JS, **no build,
  no framework**. Deployed on Netlify at `muhurata.com`.
- **`muhurata-api-9/`** — the reading service. Python + FastAPI on uvicorn.
  Deployed on **Render (Starter instance — no cold start)**, auto-deploys
  from `main` on GitHub.

> Neither folder is a git repo locally. The only `.git` is at `~` with
> zero commits and no remote. Treat the deployed GitHub repos as the
> source of truth and confirm before assuming a local change is what
> production runs.

## The real stack

### Site (`muhurata-site-11/`)
- Plain HTML + inline `<style>` + inline `<script>`. No bundler, no
  `package.json`. ES5-style vanilla JS.
- Pages: `index.html` (form + reading + free tools + Naksha chat),
  `kundli.html` (full 7-tab chart), `terms.html`, `privacy.html`.
- Shared, non-inline scripts (loaded in `<head>`, in this order):
  - `config.js` — `window.MH_CONFIG` (`API_BASE`, `SUPABASE_URL`,
    `SUPABASE_ANON_KEY`). The anon key is public by design.
  - `@supabase/supabase-js` UMD from jsDelivr.
  - `auth.js` — `window.mhAuth`: Google sign-in, session, `token()`.
    Any `[data-mh-auth]` button auto-syncs to signed-in/out.
  - `api.js` — `window.mhApiFetch(path, opts)`: prefixes `API_BASE`,
    attaches the Supabase bearer token (unless `{anon:true}`), and maps
    401→`unauthorized`, 429→`rate_limited`, 503→`unavailable`, network
    fail→`cold`. Every API call should go through it.
- `netlify.toml` sets security headers + a CSP. Still no build step.

### API (`muhurata-api-9/`)
- **FastAPI** on **uvicorn**, `--workers 2` (Render Starter, 0.5 CPU).
  The chart maths run under a per-process `threading.Lock`
  (`chart_engine._swe_lock`) because Swiss Ephemeris' C lib isn't
  thread-safe — 2 workers = 2 concurrent computations, ample for the
  ~10k-users scale.
- **Ephemeris:** `pyswisseph`, built-in **Moshier** model, sidereal,
  **Lahiri**, whole-sign houses. `chart_engine.py` + `interpret.py` are
  pure, deterministic, **no LLM** — locked by golden + invariant tests.
- **Database (`db.py`):** Supabase Postgres in production, SQLite locally
  and in tests (auto-selected when `DATABASE_URL` is empty). Postgres
  goes through a **process-wide pool** (`psycopg` 3 + `psycopg_pool`)
  pointed at Supabase's **transaction pooler (Supavisor, port 6543)** —
  `prepare_threshold=None`, `connect_timeout=5`, `statement_timeout=8s`,
  `max_size=8` per worker. `with db.cursor() as c:` borrows one
  connection for one transaction and returns it on exit. Transient
  connection failures raise `db.DBUnavailable`, which `app.py` turns into
  a fast **HTTP 503** (no more 130s hangs).
- **Schema:** `migrations/NNNN_*.sql` applied by `migrate.py` (tracked in
  `schema_migrations`, idempotent). Run as Render's **Pre-Deploy
  Command**. Nothing creates tables at import time. `{{PK}}` is the one
  dialect token. Add a migration; never hand-edit a live table.
- **Startup:** a FastAPI `lifespan` opens the pool with backoff; a DB
  that's briefly down does **not** crash boot — `/api/health` reports
  `{"ok":false,"db":"degraded"}` with a 503 until it recovers.
- **Auth (`auth.py`):** verifies Supabase JWTs locally (project JWKS,
  or `SUPABASE_JWT_SECRET` HS256 fallback). `require_user` → 401,
  `require_admin` → 403 unless the email is in `ADMIN_EMAILS`.
  - Admin only: `/api/leads`, `/api/whatsapp/catchup-batch`.
  - Sign-in required: `/api/naksha/chat`, `/api/predictions`.
  - Anonymous (the funnel): `/api/reading`, `/api/kundali`,
    `/api/matching`, `/api/full-kundli`, `/api/horoscope`, `/api/cities`.
- **Naksha limit** (`naksha.check_and_increment`) is keyed on the
  verified Supabase **user id** (migration `0002`), so a page refresh
  can't reset the 5-free-questions count.
- **Rate limiting (`ratelimit.py`):** in-process per-IP token bucket on
  `/api/reading`, `/api/reading/pdf`, `/api/naksha/chat`,
  `/api/predictions`. Cloudflare in front does the coarse cross-worker
  limiting. Client IP is read from `CF-Connecting-IP`.
- **Honeypot:** `ReadingRequest.website` — non-empty ⇒ silent 200 no-op.
- **WhatsApp webhook:** `X-Hub-Signature-256` verified against
  `WA_APP_SECRET` (`whatsapp.verify_signature`). `WA_VERIFY_TOKEN` has
  **no default** — verification fails closed if unset.
- **LLM** (Naksha chat + `/api/predictions` only): OpenRouter free model
  or Anthropic `claude-haiku-4-5`, over raw `urllib`.

## Dev / build / test commands (as they actually exist)

### API
```
cd muhurata-api-9
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt && pip install pytest
python migrate.py                         # apply migrations (SQLite locally)
uvicorn app:app --reload --port 8000      # docs at /docs
pytest                                    # 18 tests, SQLite, no network
python chart_engine.py                    # prints a sample chart
```
- Dependencies are pinned. `requirements.in` is the source; regenerate
  the lock with `uv pip compile requirements.in -o requirements.txt --generate-hashes`.
- `.python-version` = 3.12.7 (Render reads `PYTHON_VERSION`).
- Regenerate the chart golden file after an intentional ephemeris change:
  `WRITE_GOLDEN=1 pytest -k golden` then commit `tests/golden_chart.json`.
- CI (`.github/workflows/ci.yml`) runs migrations + pytest on every PR.

### Site
No build, no tests. Open `index.html`, or serve the folder
(`python -m http.server`). Fill real values into `config.js`. Deploy =
push to the GitHub repo Netlify watches.

## Manual setup this code expects (not done in code)

1. Create the Supabase project; enable Google as an auth provider.
2. `pg_dump` the old Render database and restore it into Supabase
   **before** it expires.
3. Set Render env vars (see `muhurata-api-9/.env.example`): `DATABASE_URL`
   (pooler 6543), `DIRECT_URL` (5432), `SUPABASE_URL`,
   `SUPABASE_JWKS_URL`, `ADMIN_EMAILS`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`,
   LLM keys.
3. Upgrade the Render service to **Starter**, set the Pre-Deploy Command
   to `python migrate.py`, start command to
   `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 2`.
4. Put Cloudflare in front of both hostnames (rate-limit `/api/*`).
5. Fill `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `API_BASE` in
   `muhurata-site-11/config.js`.
6. Buy the Swiss Ephemeris commercial licence (closed commercial use).

## Rules

- **Never push to `main` without asking.** The API auto-deploys from
  `main`; there is no staging environment. CI + Render's one-click
  rollback are the only safety nets.
- **Everything is on a paid-but-small or free tier — assume it can
  vanish.** Supabase Pro, Render Starter, Cloudflare free. Keep the
  off-platform `pg_dump` habit. Design every change so the database or a
  service being gone tomorrow is survivable.
- **Design language: bold & modern (Astrotalk-style, chosen Sep 2026,
  supersedes the earlier "calm dharmic serif" brief).** Near-black warm
  ground, one bright amber accent (`--brass` ≈ `#f4b52e`), **Space
  Grotesk** everywhere in heavy weights, fat rounded pill buttons
  (`--pill`), oversized punchy headlines, marketing hero with a hook, a
  sticky top nav. Dark-committed — the old light/dark toggle is
  neutralised. Still no harsh reds (the red roles map to amber). The
  whole look is driven from `theme.css`, which remaps the tokens the
  pages' inline CSS already runs on.
- **Chart calculation stays deterministic and testable.** No LLM in the
  ephemeris or interpretation path. `chart_engine.py` / `interpret.py`
  stay pure functions of their inputs. The LLM is only for Naksha chat
  and the long-form `/api/predictions` sections.

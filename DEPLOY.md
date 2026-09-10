# Deploying Muhurata (free tier + Supabase + Google sign-in)

Two projects: **api** (this repo → Render) and **site** (→ Netlify at
muhurata.com). Target: **$0/month** — Render free web service, Supabase
free Postgres + Auth.

Free-tier trade-offs you're accepting: ~50s cold start on the API after
15 min idle; Supabase 500 MB DB that auto-pauses after ~1 week with no
traffic (a daily uptime ping keeps it awake); manual backups only.

Do the steps in order. **Step 3 has a clock on it** — the current live
database expires and is deleted.

---

## 1. Supabase project  (~10 min)

1. supabase.com → **New project** (Free). Pick the region nearest India
   (Mumbai `ap-south-1`, else Singapore).
2. **Project Settings → Database → Connection string**:
   - **Transaction pooler** (host ends `...pooler.supabase.com`, port
     **6543**) → this is `DATABASE_URL`
   - **Direct connection** (port **5432**) → this is `DIRECT_URL`
   - Make sure each ends with `?sslmode=require`.
3. **Project Settings → API**:
   - **Project URL** → `SUPABASE_URL`  (e.g. `https://abcd1234.supabase.co`)
   - **`anon` `public`** key → `SUPABASE_ANON_KEY`  (public — goes in the site's `config.js`)
   - **JWT Secret** → `SUPABASE_JWT_SECRET`
   - `SUPABASE_JWKS_URL` = `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`

## 2. Google sign-in  (~15 min)

1. console.cloud.google.com → new project → **APIs & Services → OAuth
   consent screen** → External → fill app name, support email, done.
2. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins: `https://muhurata.com`,
     `http://localhost:8000`
   - Authorized redirect URI: `https://<ref>.supabase.co/auth/v1/callback`
   - Copy the **Client ID** and **Client secret**.
3. Supabase → **Authentication → Providers → Google** → paste Client ID +
   secret → enable.
4. Supabase → **Authentication → URL Configuration**:
   - Site URL: `https://muhurata.com`
   - Redirect URLs: `https://muhurata.com/**`, `http://localhost:8000/**`

## 3. Rescue the current database  (~5 min — before it expires)

1. Get the **current** live `DATABASE_URL` from your existing Render
   dashboard (the service that's live now).
2. Dump it and load it into Supabase:
   ```
   pg_dump --no-owner --no-privileges "OLD_DATABASE_URL" > muhurata-rescue.sql
   psql "SUPABASE_DIRECT_URL" < muhurata-rescue.sql
   ```
   No `pg_dump`? `brew install libpq && brew link --force libpq`, or
   export/import with TablePlus / Postico.
3. Keep `muhurata-rescue.sql` somewhere off-platform. This is your only
   backup until you set up scheduled dumps.

The app's migrations (`migrate.py`, run automatically on deploy) reconcile
the schema afterwards — they're idempotent and safe over a restored dump.

## 4. Wire the repos  (me + you)

1. You send me the two GitHub repo URLs (api + site).
2. I set the git remotes, write your real Supabase values into the site's
   `config.js` and the `connect-src` in `netlify.toml`, and commit both.
3. You `git push` each (needs your GitHub auth — a PAT or SSH key).

## 5. Render — the API  (~10 min)

If a Render service already auto-deploys the api repo, you just need the
env vars; otherwise: New → Web Service → connect the repo → it reads
`render.yaml`.

- **Build command**: `pip install -r requirements.txt && python migrate.py`
- **Start command**: `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1`
- **Environment** (Dashboard → service → Environment) — set from
  `.env.example`, using your step-1/2 values:
  `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_URL`, `SUPABASE_JWKS_URL`,
  `SUPABASE_JWT_SECRET`, `ADMIN_EMAILS` (your email),
  `OPENROUTER_API_KEY`, plus the `WA_*` values if WhatsApp is live.
  Leave `OPENROUTER_MODEL` as `openrouter/free` for now.
- Deploy. Watch the build log — `migrate.py` prints `applied 0001…` etc.
- Note the service URL (`https://muhurata-api-XXXX.onrender.com`) and send
  it to me so I can lock it into `config.js` (`API_BASE`) and the CSP.

## 6. Netlify — the site  (~2 min)

If Netlify auto-deploys the site repo, the push in step 4 ships it.
Otherwise: connect the repo (no build command, publish directory `.`), or
drag-and-drop the folder. `netlify.toml` sets the headers/CSP.

## 7. Smoke test

- muhurata.com → submit a reading → chart + reading render
- "Sign in" (top right) → Google → returns signed in
- Naksha chat → ask something → LLM answers (or "chat brain isn't
  configured" if the OpenRouter key is missing / rate-limited)
- `curl https://<api>/api/leads` → 401; with your Google token → 200
- `curl -X POST https://<api>/api/whatsapp/webhook -d '{}'` → 403

## After launch

- **Keep Supabase awake**: a free uptime monitor (e.g. UptimeRobot)
  hitting `https://<api>/api/health` every 10 min stops both the Render
  service and the Supabase DB from idling out.
- **Backups**: schedule a nightly `pg_dump` (GitHub Actions cron →
  `DIRECT_URL` → commit to a private bucket / repo).
- **When there's real traffic**: Render Starter ($7) kills the cold
  start; Supabase Pro ($25) adds daily backups + no auto-pause; pin a
  cheap paid `OPENROUTER_MODEL` so the PDF's LLM sections work.
- **Swiss Ephemeris**: buy the commercial licence (closed commercial use).

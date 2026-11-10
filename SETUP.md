# ResearchGraph — complete setup (Windows PowerShell commands; macOS/Linux: same, different venv activation)

Read `PROJECT_STATUS.md` first: it lists what was verified and what you must still run yourself.

## A. Checkpoint
Copy this unzipped folder somewhere safe (or zip it) before changing anything. Your old SQLite file is never modified by anything here.

## B. Supabase (free) — about 10 minutes
1. https://supabase.com → New project. Save the **database password**.
2. Dashboard → **SQL Editor** → paste all of `supabase/migrations/0001_researchgraph.sql` → Run. (No destructive statements. It creates tables, pgvector, RLS, the private `papers` bucket and Storage policies.)
3. **Authentication → Providers → Email**: keep enabled. Decide whether "Confirm email" is on (the app handles both).
4. **Authentication → URL Configuration**: Site URL = your Vercel URL (add later); add Redirect URLs `http://localhost:5173/**` and `https://YOUR-APP.vercel.app/**`. Password-reset links need these.
5. Collect (Project Settings): **Project URL**, **anon/publishable key** (API page), **service_role key** (API page, secret), **Database connection string → Session pooler** (Database page; replace the password). Optional: **JWT secret** only if your project still uses legacy HS256 keys.

## C. AI keys (free)
- Groq: https://console.groq.com/keys → create key.
- Gemini: https://aistudio.google.com/apikey → create the key in a project **without billing enabled** (that is what keeps usage on the free tier; the code has no paid path, but a billed project could charge).
- Check your own free limits in each console, then set the `*_RPM/RPD/TPM/TPD` guards in `.env` slightly below them.

## D. Run locally
Backend:
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # then edit .env: paste your values (never commit it)
uvicorn app.main:app --reload --port 8000 --env-file .env
```
Check http://127.0.0.1:8000/api/health and `/api/health/ready` (database true, ai_configured true, auth configured, storage supabase).
**Demo mode without Supabase** (single built-in user, SQLite, local PDFs): in `.env` set `ENV=dev`, `AUTH_DISABLED=true`, `STORAGE_BACKEND=local`, leave `DATABASE_URL` empty; still add GROQ/GEMINI keys.

Frontend (new terminal):
```
cd frontend
copy .env.example .env          # VITE_API_BASE_URL, VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY
npm install                     # updates package-lock.json for @supabase/supabase-js; commit it
npm run dev                     # http://localhost:5173
```
(Leave the two VITE_SUPABASE_* values empty for demo mode: no login screen.)

## E. Verify the real providers (do this before trusting anything)
```
cd backend
python ../scripts/live_check.py
```
Fix every FAIL (usually a model id: the script lists the ids your key can use; set `GROQ_MODEL` / `GEMINI_MODEL` / `EMBED_MODEL`).
Then the quality benchmarks with your six PDFs:
```
python ../scripts/benchmark_providers.py --pdf-dir C:\path\to\six_pdfs --sleep 8
```
Read `benchmark_results/extraction.md`; set the per-feature winner via `AI_PRIMARY_PROVIDER` or `*_MODEL_<FEATURE>` or the table in `backend/app/ai/router.py`.
Upload + analyze the six PDFs in the app, Generate graph (expect 4 music papers together, 2 inspection papers together; if the semantic edges are too many/few, tune `RG_SIM_THRESHOLD` — Gemini vectors have a different similarity scale than the old nomic ones, see `docs/EMBEDDINGS.md`), then:
```
python ../scripts/mentor_benchmark.py --api http://127.0.0.1:8000      # add --token <access token> when login is on
```
and read `benchmark_results/mentor.md` yourself.

## F. Automated tests
```
cd backend
python -m unittest tests.test_ai_layer -v      # stdlib only
python -m pytest tests -q                       # needs requirements installed; includes tests/test_isolation.py (two users)
bash tests/run_e2e.sh                           # Git Bash/WSL
```
Manual two-account test: sign up user A and B (two browsers), upload a PDF as A, confirm B sees nothing and `GET /api/papers/<A's id>` as B returns 404.

## G. Move old local data (optional)
See `docs/MIGRATION.md` (dry run first; SQLite stays untouched).

## H. Deploy (free tiers; verify current limits, `docs/DEPLOYMENT.md`)
1. Push this folder to GitHub (`.env` files are git-ignored).
2. Render → New → Blueprint → pick the repo (`render.yaml`) → paste the secret env vars from `backend/.env.example`. `CORS_ORIGINS` = your Vercel URL (set after step 3 and redeploy).
3. Vercel → Import repo → Root Directory `frontend` → env vars `VITE_API_BASE_URL` (Render URL), `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` → Deploy.
4. Put the Vercel URL into Supabase Site URL/Redirect URLs and Render `CORS_ORIGINS`.
5. Smoke test: sign up, upload, analyze, graph, mentor, log out/in (data persists), `https://<render>/api/health/ready`.
Free Render sleeps when idle: the first request after a pause can take about a minute.

## Troubleshooting
- 401 everywhere: frontend Supabase vars wrong, or backend `SUPABASE_URL`/`SUPABASE_ANON_KEY` missing.
- 503 "AI … temporarily": both free quotas used or keys wrong — run `live_check.py`.
- `relation ... does not exist`: the SQL migration was not run on this project.
- Mentor says nothing is indexed after changing `EMBED_PROVIDER/EMBED_MODEL`: it re-embeds automatically on the next question/graph generation.

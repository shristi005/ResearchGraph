# Project status (honest)
Authoring sandbox: no network (Groq, Gemini, Supabase, npm, PyPI all unreachable), no pip, no FastAPI/SQLAlchemy/PyMuPDF/httpx, no browser, no Vercel/Render, no benchmark PDFs. Work was therefore done as code + SQL + docs, tested only where stdlib allowed.

## Verified (actually executed)
| Check | Result |
|---|---|
| `python -m compileall backend scripts` (syntax of all Python) | pass |
| `python -m unittest tests.test_ai_layer` — 26 tests: real provider-client HTTP code vs a stand-in server; feature routing, 429/5xx/401/404/400/malformed handling, both-down, retry limits, cooldown, local quota guard, identical fallback payload, no-key behaviour, no secrets in errors, embeddings (768-d, normalised, 429), HS256/remote token verification + cache, retrieval picking | 26/26 pass |
| `scripts/live_check.py` against the stand-in server (script logic only) | 16/17; the one failure is semantic ranking, which a hash stand-in cannot do |
| `scripts/migrate_sqlite_to_supabase.py` dry run on a synthetic SQLite file | pass |
These are **simulated**; they are not evidence that real Groq/Gemini behave identically.

## Implemented but NOT executed (needs your machine)
- Groq + Gemini clients, router, quota guard (live behaviour unverified); model ids/limits unverified.
- Embedding providers (gemini, local fastembed); retrieval quality unmeasured; similarity threshold must be re-tuned.
- SQLAlchemy per-user scoping (`do_orm_execute` + `with_loader_criteria`, owner stamping), Postgres engine, pgvector insert/search SQL, Storage service, JWT dependency, all route changes. **Highest risk:** the automatic scoping and pgvector SQL were never run. Run `pytest tests/test_isolation.py` and the two-account test before real use.
- SQL migration (tables, vector(768), HNSW, RLS, bucket + storage policies, `match_chunks`, profile trigger) — never executed on Postgres.
- Frontend: login/signup/forgot/reset pages, auth context, token interceptor, protected routes, sign-out block, blob PDF open, AI banner. Not built (`npm install` blocked): run `npm run build` and look at it.
- Updated legacy tests (`test_services.py`, `test_upload.py`, `e2e.py`) were edited, not run.

## NOT done
- Phase 2 quality work: no new PDF-extraction improvements (merged words/reading order, Docling/OCR not evaluated), no clustering changes, no changes to `gap_service`, no mentor retrieval changes beyond user/paper/model filtering and tests. These need the six benchmark PDFs and live models; they were **not** in the ZIP (`sample_papers/` holds 7 synthetic fake-news/medical PDFs, which are not a substitute).
- Provider benchmark, six-paper clustering, 7 Mentor tests, two-user test, visual regression/screenshots, deployment: scripts and checklists are provided (`docs/LIVE_TESTS.md`); no results exist.
- Not deployed. Nothing was deleted; no data migrated; Ollama code and `fake_ollama.py` were removed (replaced by `tests/fake_ai_server.py`).

## UI changes (all minimal)
Added auth pages in the existing style; sidebar gains email + "Sign out" below the nav; banner text says AI instead of Ollama; one subtitle on My Papers says "let AI read them" instead of "local model". Layouts, colours and components otherwise untouched.

## Files changed/added
Backend: `config.py`, `main.py`, `auth.py`, `auth_tokens.py`, `ai/*` (new), `database/session.py`, `models/*`, `services/{ai_client,storage_service,chunk_service,embedding_service,llm_service,cache_service,reprocess,…}`, `routes/*`; removed `services/ollama_client.py`. Frontend: `api.js`, `supabase.js`, `auth/AuthContext.jsx`, `pages/Auth.jsx`, `App.jsx`, `main.jsx`, `PaperAnalysis.jsx`, `Papers.jsx` (one sentence), `package.json`, `vercel.json`. Root: `supabase/migrations/0001_researchgraph.sql`, `render.yaml`, `scripts/*`, `docs/*`, `SETUP.md`, `.env.example` files.
New dependency: `psycopg[binary]` (backend), `@supabase/supabase-js` (frontend); optional `fastembed`. Env vars: `backend/.env.example`.

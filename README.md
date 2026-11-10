# ResearchGraph

Upload research PDFs, let hosted **free-tier AI (Groq + Gemini)** read them, and explore how they relate as an interactive
graph. Get plain-language explanations of every paper and connection, evidence-backed research *opportunities*, and a
Research Mentor that answers from your own papers with page citations. Accounts, papers, vectors and PDFs live in Supabase.

**Start here:** [`SETUP.md`](SETUP.md) (complete step-by-step) · [`PROJECT_STATUS.md`](PROJECT_STATUS.md) (what is verified and what is not)
· [`docs/`](docs) (architecture, AI routing, embeddings, migration, deployment, live tests).

```
React + Vite (Vercel) --JWT--> FastAPI (Render) --> Supabase Postgres + pgvector + Auth + private Storage
                                  |-- Groq API   (free tier)   -- feature routing + automatic fallback --
                                  |-- Gemini API (free tier)   --                                     --
                                  '-- embeddings (Gemini embedding API, or local fastembed) - separate from generation
```
Browsers only talk to FastAPI. API keys never reach the frontend. Nothing falls back to a paid service.

## Quick local run without any cloud account (demo mode)
Needs only a Groq and/or Gemini API key (both free): see SETUP.md part C and part D "demo mode".

## Tests
- `python3 -m unittest tests.test_ai_layer -v` in `backend/` - stdlib only, no installs (26 tests: routing, fallback, quota, embeddings, auth tokens, ranking).
- `python -m pytest tests -q` in `backend/` after `pip install -r requirements.txt` (service/API tests, two-user isolation).
- `bash tests/run_e2e.sh` - live server + stand-in Groq/Gemini server (plumbing only).
- `python scripts/live_check.py` - REAL provider checks with your keys. `scripts/benchmark_providers.py`, `scripts/mentor_benchmark.py` - your six PDFs.

## Architecture
```
backend/app
  main.py          FastAPI app + CORS
  config.py        limits, model names, all thresholds (override with env vars RG_*)
  auth.py, auth_tokens.py   Supabase JWT verification + per-request user-scoped DB session
  ai/              Groq + Gemini clients, feature router, fallback, free-quota guard, embeddings (docs/AI_ROUTING.md)
  database/        SQLAlchemy engine/session, automatic per-user row scoping (Supabase Postgres; SQLite for local tests)
  models/          Paper, Relationship, Hypothesis, Chunk, Conversation, Message (all carry user_id)
  schemas/         Pydantic request/response + extraction validation
  routes/          papers, analysis, graph, gaps (REST only, no logic)
  services/        pdf_service                      PyMuPDF text + metadata
                   research_extraction_service      sections -> Groq/Gemini JSON -> validation -> grounding
                   ai_client                        facade over the AI router + embeddings (friendly errors)
                   storage_service                  private Supabase Storage (local folder in dev)
                   embedding_service                combined text -> embedding provider -> stored with its model id
                   similarity_service               cosine (scikit-learn), topic + method overlap
                   citation_service                 reference list parsing + title matching
                   graph_service                    persist edges, NetworkX graph, API payloads
                   section_service                  headings, abstract inference, article type, quote + page lookup
                   gap_service                      research opportunities (4 categories) from verified evidence
                   feasibility_service              student feasibility analysis (AI, cached)
                   graph_explanation_service        graph overview, node and edge explanations (AI, cached)
                   relationship_view                shared items + plain-language strength (no raw scores)
                   chunk_service / mentor_service   retrieval over page-referenced chunks + Research Mentor chat
                   llm_service / cache_service      validated LLM calls, cached results
  utils/           file hashing, text normalisation
frontend/src       pages/ (Dashboard, Papers, PaperAnalysis, GraphPage, Gaps), graph/ (PaperNode, RelEdge, SidePanel, layout)
```
**Data flow:** PDF -> validate + hash -> PyMuPDF text; original saved to private Storage as `<user_id>/<hash>.pdf`; rows in Postgres ->
`POST /analyze` (background, one at a time) -> structured JSON saved -> `POST /api/graph/generate` (embeds, compares
every pair, finds citations, saves edges) -> `GET /api/graph` (NetworkX -> JSON for React Flow) -> `POST /api/gaps/generate`.

## API
`POST /api/papers/upload` · `GET /api/papers` · `GET|DELETE /api/papers/{id}` · `GET /api/papers/{id}/text|file` ·
`POST /api/papers/{id}/analyze` · `GET /api/papers/{id}/analysis` · `GET /api/ai/status` (providers, routing, quota; `/api/ollama/status` kept as an alias) · `GET /api/health/ready` ·
`POST /api/graph/generate` · `GET /api/graph` · `GET /api/graph/paper/{id}/neighbors` ·
`GET /api/graph/overview` · `GET /api/graph/edge/{id}/detail` · `GET /api/papers/{id}/explanation` ·
`POST /api/papers/{id}/reprocess` · `POST /api/papers/reprocess-all` ·
`POST /api/gaps/generate` · `GET /api/gaps` · `PATCH /api/gaps/{id}` · `POST /api/gaps/{id}/feasibility` ·
`POST /api/mentor/index` · `POST /api/mentor/chat` · `GET /api/mentor/conversations[/{id}]` · `GET /api/health`

## Honesty rules built in
- **No invented metadata.** Title and authors must appear in the paper's opening text, the year must appear in the text,
  and the abstract is copied verbatim from the PDF, otherwise they are removed with a visible warning. A paper with no
  detected title is shown by its file name.
- **Citations only from reference lists.** A citation edge needs a reference entry that matches another uploaded paper's
  title (confidence >= 0.90). Similarity never creates a citation.
- **Opportunities are hypotheses.** Every quote is a sentence found in the PDF, shown with its page. Statements the AI
  extracted that cannot be matched to a PDF sentence are never used as evidence. Confidence comes from the evidence
  (papers, wording agreement, quote sources, extraction quality), is never "high", and exploratory combinations and
  single-source ideas are capped at low. Dataset availability and novelty are never claimed: they are marked for manual validation.
- **Original vs AI.** Panels label text "From the PDF" (word for word) or "AI explanation". The extracted data is never replaced by summaries.
- **Mentor.** Answers must tag claims with sources that were actually retrieved; invented tags are removed and flagged.
- **Model reality.** Any LLM can miss or blur items. Treat extracted lists as drafts and check the PDF.

## Tuning (env vars, set before starting uvicorn)
`RG_SIM_THRESHOLD` (default 0.70), `RG_SIM_MAX_EDGES_PER_NODE` (4), `RG_TOPIC_MIN_SHARED` (2),
`RG_METHOD_MIN_SHARED` (1), `RG_CITATION_MIN_CONFIDENCE` (0.90), `RG_DATA_DIR`, `RG_MENTOR_TOP_K` (6).
**After switching embedding model, re-tune `RG_SIM_THRESHOLD`** (see docs/EMBEDDINGS.md). AI/Supabase settings: `backend/.env.example`.
PowerShell example: `$env:RG_SIM_THRESHOLD="0.6"; uvicorn app.main:app --reload --port 8000`

## Troubleshooting
- Red banner "Cannot reach the backend": Terminal 1 is not running.
- Red banner "AI setup needed": a provider key or the embedding setting is missing in the backend environment.
- No similarity edges: lower `RG_SIM_THRESHOLD` (real embeddings vary by topic mix).
- Scanned PDFs are rejected (no OCR).
- A paper shows "abstract inferred": the PDF has no Abstract heading, so the first long front-matter paragraph is used. Check it.
- AI text says "temporarily unavailable": both free quotas are used up or the providers are down; the facts and quotes still show. Press Regenerate later.

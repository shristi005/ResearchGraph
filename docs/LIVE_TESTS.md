# Checks only you can run (need your keys / accounts / PDFs)
Consoles: Groq limits https://console.groq.com/settings/limits · Gemini limits https://aistudio.google.com (usage/rate limits) · Supabase dashboard.
1. `python scripts/live_check.py` → all PASS except possibly concurrency (429 = low RPM, fine).
2. `python scripts/benchmark_providers.py --pdf-dir <six pdfs>` → choose providers per feature.
3. Six-paper graph: 4 music + 2 visual-inspection clusters; no forced edges; isolated nodes allowed.
4. `python scripts/mentor_benchmark.py` + read `benchmark_results/mentor.md` (7 tests).
5. Two accounts: isolation (uploads, graph, opportunities, conversations, `/file` URL).
6. Live fallback beyond the bad-key test: temporarily set `GROQ_RPM=1` and ask the Mentor twice → second answer says provider gemini in `/api/ai/status` counters.
7. UI: compare each page with the original (Dashboard, Papers, Graph, Opportunities, Mentor, Paper Analysis) at desktop and phone width; check the sign-out block in the sidebar and the auth pages.
### Deployed
Frontend loads; `/api/health/ready` all true; sign up/in/out/reset; upload; analyze (real Groq/Gemini); Mentor; log out/in persistence; redeploy and re-check persistence; first request after idle works.

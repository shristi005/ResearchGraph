# Deployment notes (verify each limit on the vendor page; they change)
- Render free web service: sleeps after idle (cold start ~1 min), 512 MB RAM (PyMuPDF + scikit-learn + numpy fit but are tight; do not use `EMBED_PROVIDER=local`), no persistent disk (PDFs go to Supabase Storage).
- Supabase free: DB size and Storage caps, and projects can pause after inactivity: check the dashboard.
- Vercel hobby: static React build; `vercel.json` provides SPA rewrites.
- Groq/Gemini free tiers: per-model RPM/RPD/TPM limits; account/region eligibility applies.
Security model: backend connects to Postgres with the database role (bypasses RLS) and enforces ownership in code (`database/session.py` adds `user_id = :uid` to every query on owned tables and stamps new rows); RLS protects direct access with the public keys. The service-role key is used only in `storage_service.py` after ownership is established. `AUTH_DISABLED` is ignored when `ENV=production`.
Do not mark the deployment complete until `docs/LIVE_TESTS.md` section "Deployed" passes.

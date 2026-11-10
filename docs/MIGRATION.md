# SQLite → Supabase
1. Run the SQL migration (SETUP B2). 2. Sign up in the app once; copy your user UUID (Dashboard → Authentication → Users).
3. `cd backend` (venv active, `.env` filled), then:
```
python ../scripts/migrate_sqlite_to_supabase.py --sqlite data/researchgraph.db --user-id <uuid>          # dry run
python ../scripts/migrate_sqlite_to_supabase.py --sqlite data/researchgraph.db --user-id <uuid> --apply
```
Safe: SQLite opened read-only and kept as backup; `ON CONFLICT DO NOTHING`; counts verified after copy; PDFs uploaded to Storage; vectors intentionally not copied. The dry run was executed on a synthetic file; `--apply` was **not** run (no Supabase access).
Schema: `papers, chunks(+vector(768)), relationships, hypotheses, conversations, messages, ai_cache, profiles`, all user tables have `user_id` + RLS policy `user_id = auth.uid()`. Same PDF may exist for different users (unique per user+hash).

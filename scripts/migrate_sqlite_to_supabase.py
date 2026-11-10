#!/usr/bin/env python3
"""Copy an existing local ResearchGraph SQLite database (and its PDFs) into Supabase for ONE user.

Safe by design:
  * the SQLite file is opened READ-ONLY and never modified (keep it as your backup);
  * default is a DRY RUN that only prints what would be copied; nothing is written without --apply;
  * rows are inserted with ON CONFLICT DO NOTHING (re-running never duplicates or overwrites);
  * old Ollama/nomic vectors are NOT copied (different model => incompatible); papers/chunks get re-embedded lazily.

Usage (from backend/, with the backend venv active and DATABASE_URL, SUPABASE_* set):
  python ../scripts/migrate_sqlite_to_supabase.py --sqlite data/researchgraph.db --user-id <auth user uuid>
  python ../scripts/migrate_sqlite_to_supabase.py --sqlite data/researchgraph.db --user-id <uuid> --apply
Find the user UUID: Supabase Dashboard -> Authentication -> Users (sign up in the app first).
"""
import argparse
import sqlite3
import sys
from pathlib import Path

TABLES = [  # FK order
    ("papers", ["id", "original_filename", "stored_path", "file_hash", "size_bytes", "page_count", "raw_text", "status",
                "error", "pdf_title", "pdf_author", "layout_json", "extraction_json", "created_at"]),
    ("chunks", ["id", "paper_id", "idx", "page", "section", "text"]),
    ("relationships", ["id", "source_id", "target_id", "type", "score", "explanation", "shared_json", "created_at"]),
    ("hypotheses", ["id", "key", "kind", "hypothesis", "supporting_paper_ids", "evidence", "reasoning", "uncertainties",
                    "validation_steps", "confidence", "review_status", "details_json", "feasibility_json",
                    "enrichment_status", "created_at"]),
    ("conversations", ["id", "title", "created_at"]),
    ("messages", ["id", "conversation_id", "role", "content", "sources_json", "warnings_json", "created_at"]),
]


def read_rows(con, table, cols):
    have = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if not have:
        return []
    use = [c for c in cols if c in have]
    return [dict(zip(use, r)) for r in con.execute(f"SELECT {', '.join(use)} FROM {table}")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--user-id", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    src = Path(a.sqlite).resolve()
    if not src.exists():
        print(f"SQLite file not found: {src}")
        return 1
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    data = {t: read_rows(con, t, cols) for t, cols in TABLES}
    for t, rows in data.items():
        print(f"{t:14s} {len(rows):6d} rows")
    if not a.apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to copy.")
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    from sqlalchemy import text
    from app import config
    from app.database.session import engine
    from app.services import storage_service
    if not config.IS_POSTGRES:
        print("DATABASE_URL must point at Supabase Postgres for --apply.")
        return 1

    # 1) PDFs -> Storage; rewrite stored_path to the object key
    for p in data["papers"]:
        old = Path(p["stored_path"])
        if old.exists():
            p["stored_path"] = storage_service.save(a.user_id, p["file_hash"], old.read_bytes())
        else:
            print(f"  ! PDF missing on disk for paper {p['id']} ({p['original_filename']}); row copied, file not.")
            p["stored_path"] = storage_service.key_for(a.user_id, p["file_hash"])

    # 2) rows
    with engine.begin() as conn:
        for t, cols in TABLES:
            for r in data[t]:
                r = {**r, "user_id": a.user_id}
                names = list(r)
                conn.execute(text(f"INSERT INTO public.{t} ({', '.join(names)}) VALUES ({', '.join(':' + n for n in names)}) "
                                  f"ON CONFLICT DO NOTHING"), r)
            conn.execute(text(f"SELECT setval(pg_get_serial_sequence('public.{t}','id'), "
                              f"GREATEST((SELECT COALESCE(MAX(id),1) FROM public.{t}),1))"))
        # 3) verify
        for t, _ in TABLES:
            n = conn.execute(text(f"SELECT count(*) FROM public.{t} WHERE user_id = :u"), {"u": a.user_id}).scalar()
            print(f"verify {t:14s} in Supabase for this user: {n} (source: {len(data[t])})")
    print("\nDone. Papers' vectors were intentionally not copied; open the Research Graph / Mentor to re-embed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

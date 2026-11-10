"""Splits each paper into page-referenced chunks, embeds them, and retrieves the most relevant ones for a question."""
import json

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.ai import embeddings
from app.ai.ranking import pick
from app.config import CHUNK_CHARS, IS_POSTGRES
from app.models.ai import Chunk
from app.models.paper import Paper
from app.services import ai_client
from app.services.research_extraction_service import load_document
from app.services.section_service import split_sentences


def build_chunks(p: Paper) -> list[tuple[int, str, str]]:
    """[(page, section, text)] from section paragraphs (references and back matter are skipped)."""
    doc = load_document(p)
    out: list[tuple[int, str, str]] = []
    if doc.abstract_source == "inferred" and doc.abstract:
        out.append((doc.abstract_page or 1, "abstract", doc.abstract[:CHUNK_CHARS * 2]))
    for section, paras in doc.paras.items():
        buf, page = "", None
        for para in paras:
            for sent in (split_sentences(para.text) or [para.text]):
                if buf and (len(buf) + len(sent) > CHUNK_CHARS or para.page != page):
                    out.append((page or 0, section, buf.strip())); buf = ""
                page = para.page
                buf += " " + sent
        if buf.strip():
            out.append((page or 0, section, buf.strip()))
    return [c for c in out if len(c[2]) > 40]


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def ensure_indexed(db: Session, papers: list[Paper]) -> int:
    """Build + embed chunks for papers that have none for the CURRENT embedding model.
    Old vectors (other model) are replaced only after the new ones were generated successfully."""
    model = embeddings.model_id()
    done = 0
    for p in papers:
        if db.scalar(select(Chunk.id).where(Chunk.paper_id == p.id, Chunk.embed_model == model).limit(1)):
            continue
        chunks = build_chunks(p)
        if not chunks:
            continue
        vecs = ai_client.embed_documents([t for _, _, t in chunks])  # raises before anything is touched on failure
        db.execute(delete(Chunk).where(Chunk.paper_id == p.id))
        rows = []
        for i, ((page, section, txt), v) in enumerate(zip(chunks, vecs)):
            c = Chunk(paper_id=p.id, idx=i, page=page, section=section, text=txt, embed_model=model,
                      embedding_json=None if IS_POSTGRES else json.dumps(v))
            db.add(c)
            rows.append((c, v))
        db.flush()  # assigns ids and stamps user_id
        if IS_POSTGRES:  # Supabase pgvector column; written with raw SQL so no extra Python dependency is needed
            for c, v in rows:
                db.execute(text("UPDATE chunks SET embedding = CAST(:v AS vector) WHERE id = :id AND user_id = :uid"),
                           {"v": _vec_literal(v), "id": c.id, "uid": c.user_id})
        db.commit()
        done += 1
    return done


def retrieve(db: Session, query: str, paper_ids: list[int], k: int) -> list[Chunk]:
    """Only chunks of the given papers AND of the session's user AND of the current embedding model are searched."""
    if not paper_ids:
        return []
    model = embeddings.model_id()
    q = ai_client.embed_query(query)
    if IS_POSTGRES:
        uid = db.info.get("user_id")
        if not uid:
            raise PermissionError("Retrieval requires an authenticated user session.")
        rows = db.execute(text(
            "SELECT id, paper_id, 1 - (embedding <=> CAST(:q AS vector)) AS sim FROM chunks "
            "WHERE user_id = :uid AND paper_id = ANY(:pids) AND embed_model = :m AND embedding IS NOT NULL "
            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"),
            {"q": _vec_literal(q), "uid": uid, "pids": list(paper_ids), "m": model, "n": max(k * 4, 24)}).all()
        ranked = [(r.id, r.paper_id, float(r.sim)) for r in rows]
        by_id = {c.id: c for c in db.scalars(select(Chunk).where(Chunk.id.in_([r[0] for r in ranked])))} if ranked else {}
    else:
        import numpy as np
        objs = db.scalars(select(Chunk).where(Chunk.paper_id.in_(paper_ids), Chunk.embed_model == model,
                                              Chunk.embedding_json.is_not(None))).all()
        if not objs:
            return []
        qv = np.array(q, dtype=float)
        m = np.array([json.loads(r.embedding_json) for r in objs], dtype=float)
        sims = (m @ qv) / ((np.linalg.norm(m, axis=1) * np.linalg.norm(qv)) + 1e-9)
        order = np.argsort(-sims)
        ranked = [(objs[i].id, objs[i].paper_id, float(sims[i])) for i in order]
        by_id = {c.id: c for c in objs}
    return [by_id[cid] for cid in pick(ranked, paper_ids, k) if cid in by_id]

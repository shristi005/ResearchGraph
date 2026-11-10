"""Re-reads the ORIGINAL stored PDF with the layout-aware extractor and refreshes everything that does not
need an LLM (text, page layout, verbatim abstract, article type, section report, page-referenced evidence).
Existing AI-extracted fields (topics, methods, findings...) are kept untouched."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai import Chunk
from app.models.paper import Paper
from app.services import section_service as ss, storage_service
from app.services.paper_view import get_analysis
from app.services.pdf_service import extract_text
from app.services.research_extraction_service import enrich_analysis


def reprocess(db: Session, p: Paper) -> bool:
    data = storage_service.read(p.stored_path)
    if data is None:
        return False
    content = extract_text(data)
    p.raw_text, p.layout_json, p.page_count = content.text, content.layout_json, content.page_count
    db.query(Chunk).filter(Chunk.paper_id == p.id).delete()
    a = get_analysis(p)
    if a is not None:
        a = enrich_analysis(a, ss.analyze(content.paras))
        p.extraction_json = a.model_dump_json()
        p.embedding_json = None  # the abstract may have changed; re-embed on the next graph generation
        if p.status == "embedded":
            p.status = "analyzed"
    db.commit()
    return True


def reprocess_missing(db: Session) -> int:
    n = 0
    for p in db.scalars(select(Paper).where(Paper.layout_json.is_(None))).all():
        try:
            n += reprocess(db, p)
        except Exception:
            db.rollback()
    return n

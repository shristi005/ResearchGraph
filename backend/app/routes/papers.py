from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, MIN_TEXT_CHARS
from app.auth import current_user, scoped_db
from app.auth_tokens import User
from app.models.paper import Paper
from app.models.ai import Chunk
from app.models.relationship import Relationship
from app.schemas.paper import PaperDetail, PaperOut, PaperText, UploadResponse, UploadResult
from app.services import reprocess as reprocess_service, storage_service
from app.services.pdf_service import PDFExtractionError, extract_text
from app.services.paper_view import display_title, get_analysis
from app.utils.files import looks_like_pdf, sha256_bytes

router = APIRouter(prefix="/api/papers", tags=["papers"])


def to_out(p: Paper) -> PaperOut:
    a = get_analysis(p)
    title, source = display_title(p, a)
    return PaperOut(
        id=p.id, original_filename=p.original_filename, size_bytes=p.size_bytes, page_count=p.page_count,
        status=p.status, error=p.error, title=title, title_source=source,
        pdf_title=p.pdf_title, pdf_author=p.pdf_author,
        publication_year=a.publication_year if a else None, topics=(a.topics[:6] if a else []),
        has_extraction=p.extraction_json is not None, has_embedding=p.embedding_json is not None,
        created_at=p.created_at,
    )


@router.post("/upload", response_model=UploadResponse)
async def upload_papers(files: list[UploadFile] = File(...), db: Session = Depends(scoped_db), user: User = Depends(current_user)):
    if not files:
        raise HTTPException(400, "No files provided.")

    results: list[UploadResult] = []
    for f in files:
        name = f.filename or "unnamed"

        def reject(msg: str) -> None:
            results.append(UploadResult(filename=name, outcome="rejected", message=msg))

        if not name.lower().endswith(".pdf"):
            reject("Only .pdf files are accepted.")
            continue

        data = await f.read()
        if not data:
            reject("File is empty.")
            continue
        if len(data) > MAX_UPLOAD_BYTES:
            reject(f"File is larger than {MAX_UPLOAD_MB} MB.")
            continue
        if not looks_like_pdf(data):
            reject("File content is not a valid PDF (bad header).")
            continue

        digest = sha256_bytes(data)
        existing = db.scalar(select(Paper).where(Paper.file_hash == digest))
        if existing:
            results.append(UploadResult(
                filename=name, outcome="duplicate",
                message=f"Identical file already uploaded as paper #{existing.id}.",
                paper=to_out(existing),
            ))
            continue

        try:
            content = extract_text(data)
        except PDFExtractionError as exc:
            reject(str(exc))
            continue
        if len(content.text) < MIN_TEXT_CHARS:
            reject("Almost no extractable text. This looks like a scanned/image-only PDF (OCR is not supported).")
            continue

        # Preserve the original upload (private Supabase Storage in production), keyed by user + hash.
        try:
            stored = storage_service.save(user.id, digest, data)
        except storage_service.StorageError as exc:
            reject(str(exc))
            continue

        paper = Paper(
            original_filename=name,
            stored_path=stored,
            file_hash=digest,
            size_bytes=len(data),
            page_count=content.page_count,
            raw_text=content.text.replace("\x00", ""),
            layout_json=content.layout_json.replace("\\u0000", ""),
            pdf_title=content.title,
            pdf_author=content.author,
            status="uploaded",
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)
        results.append(UploadResult(
            filename=name, outcome="created",
            message=f"Uploaded ({content.page_count} pages, {len(content.text):,} characters).",
            paper=to_out(paper),
        ))

    return UploadResponse(results=results)


@router.post("/reprocess-all")
def reprocess_all(db: Session = Depends(scoped_db)):
    """Re-read every stored PDF with the layout-aware extractor (no AI, keeps all analyses)."""
    done = 0
    for p in db.scalars(select(Paper)).all():
        try:
            done += reprocess_service.reprocess(db, p)
        except Exception:
            db.rollback()
    return {"reprocessed": done}


@router.post("/{paper_id}/reprocess", response_model=PaperOut)
def reprocess_one(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    if not reprocess_service.reprocess(db, p):
        raise HTTPException(410, "The stored PDF file is missing from storage.")
    return to_out(p)


@router.get("", response_model=list[PaperOut])
def list_papers(db: Session = Depends(scoped_db)):
    return [to_out(p) for p in db.scalars(select(Paper).order_by(Paper.id))]


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    base = to_out(p).model_dump()
    return PaperDetail(**base, text_preview=p.raw_text[:1500], text_length=len(p.raw_text))


@router.delete("/{paper_id}")
def delete_paper(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    storage_service.delete(p.stored_path)
    db.query(Relationship).filter((Relationship.source_id == paper_id) | (Relationship.target_id == paper_id)).delete()
    db.query(Chunk).filter(Chunk.paper_id == paper_id).delete()
    db.delete(p)
    db.commit()
    return {"deleted": paper_id}


@router.get("/{paper_id}/text", response_model=PaperText)
def get_paper_text(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    return PaperText(paper_id=p.id, text=p.raw_text)


@router.get("/{paper_id}/file")
def get_paper_file(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    try:
        data = storage_service.read(p.stored_path)
    except storage_service.StorageError as exc:
        raise HTTPException(502, str(exc))
    if data is None:
        raise HTTPException(410, "The stored PDF file is missing from storage.")
    safe = p.original_filename.replace('"', "").replace("\r", "").replace("\n", "")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{safe}"'})

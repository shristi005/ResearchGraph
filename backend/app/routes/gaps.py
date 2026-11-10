import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import session as dbsession
from app.auth import current_user, scoped_db
from app.auth_tokens import User
from app.models.hypothesis import Hypothesis
from app.schemas.gap import FeasibilityRequest, GapsResponse, HypothesisOut, ReviewUpdate
from app.services import feasibility_service, gap_service, graph_service, ai_client

router = APIRouter(prefix="/api/gaps", tags=["research opportunities"])


def to_out(h: Hypothesis) -> HypothesisOut:
    d = json.loads(h.details_json) if h.details_json else {}
    legacy = not h.details_json
    evidence = []
    for e in json.loads(h.evidence):
        e = dict(e)
        e["quote"] = e.get("quote") or e.pop("text", None)
        evidence.append(e)
    cat = gap_service.LEGACY_CATEGORY.get(h.kind, h.kind)
    return HypothesisOut(
        id=h.id, category=cat, category_label=gap_service.CATEGORIES.get(cat, cat), subtype=d.get("subtype"),
        title=d.get("title") or (h.hypothesis[:90] + ("…" if len(h.hypothesis) > 90 else "")),
        hypothesis=h.hypothesis, supporting_paper_ids=json.loads(h.supporting_paper_ids), evidence=evidence,
        reasoning=h.reasoning, problem=d.get("problem", ""), why_matters=d.get("why_matters", ""),
        research_question=d.get("research_question", ""), possible_methodology=d.get("possible_methodology", ""),
        datasets_resources=d.get("datasets_resources", []), student_direction=d.get("student_direction", ""),
        feasibility_considerations=d.get("feasibility_considerations", []), confidence=h.confidence,
        confidence_score=d.get("confidence_score"), confidence_reasons=d.get("confidence_reasons", []),
        uncertainties=json.loads(h.uncertainties), validation_steps=json.loads(h.validation_steps),
        review_status=h.review_status, details_source=d.get("source", "template"),
        enrichment_status=h.enrichment_status, note=d.get("note"), coverage=d.get("coverage"),
        feasibility=json.loads(h.feasibility_json) if h.feasibility_json else None, legacy=legacy)


def _response(db: Session, rows) -> GapsResponse:
    rows = list(rows)
    return GapsResponse(disclaimer=gap_service.DISCLAIMER, paper_count=len(graph_service.analyzed_papers(db)),
                        enriching=any(r.enrichment_status == "pending" for r in rows),
                        hypotheses=[to_out(h) for h in rows])


@router.post("/generate", response_model=GapsResponse)
def generate_gaps(background: BackgroundTasks, db: Session = Depends(scoped_db), user: User = Depends(current_user)):
    """Candidates and evidence are built immediately. If an AI provider is available, the student-facing wording is then
    written in the background (poll GET /api/gaps while `enriching` is true)."""
    try:
        rows = gap_service.generate(db)
    except graph_service.GraphError as exc:
        raise HTTPException(400, str(exc))
    st = ai_client.status()
    if rows and st["llm_ready"]:
        for r in rows:
            r.enrichment_status = "pending"
        db.commit()
        background.add_task(gap_service.enrich_all, [r.id for r in rows], dbsession.session_factory_for(user.id))
    else:
        for r in rows:
            d = json.loads(r.details_json)
            d["note"] = "AI wording unavailable (no AI provider is configured or the free quota is used up). Showing evidence-based template text."
            r.details_json = json.dumps(d)
        db.commit()
    return _response(db, rows)


@router.get("", response_model=GapsResponse)
def list_gaps(db: Session = Depends(scoped_db)):
    return _response(db, db.scalars(select(Hypothesis).order_by(Hypothesis.id)).all())


@router.patch("/{gap_id}", response_model=HypothesisOut)
def review_gap(gap_id: int, body: ReviewUpdate, db: Session = Depends(scoped_db)):
    if body.review_status not in gap_service.REVIEW_STATES:
        raise HTTPException(422, f"review_status must be one of: {', '.join(sorted(gap_service.REVIEW_STATES))}")
    h = db.get(Hypothesis, gap_id)
    if not h:
        raise HTTPException(404, f"Opportunity {gap_id} not found.")
    h.review_status = body.review_status
    db.commit()
    return to_out(h)


@router.post("/{gap_id}/feasibility")
def feasibility(gap_id: int, body: FeasibilityRequest | None = None, refresh: bool = False, db: Session = Depends(scoped_db)):
    body = body or FeasibilityRequest()
    try:
        return feasibility_service.analyze(db, gap_id, body.compute, body.experience, refresh)
    except KeyError:
        raise HTTPException(404, f"Opportunity {gap_id} not found.")

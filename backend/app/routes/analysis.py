from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import session as dbsession
from app.auth import current_user, scoped_db
from app.auth_tokens import User
from app.models.paper import Paper
from app.schemas.extraction import AnalysisOut
from app.services import graph_explanation_service as explain
from app.services import ai_client, research_extraction_service as svc
from app.services.paper_view import get_analysis

router = APIRouter(prefix="/api", tags=["analysis"])


@router.get("/ai/status")
@router.get("/ollama/status", include_in_schema=False)  # old path kept so cached frontends keep working
def ai_status(user: User = Depends(current_user)):
    return ai_client.status()


@router.post("/papers/{paper_id}/analyze", status_code=202)
def analyze(paper_id: int, background: BackgroundTasks, db: Session = Depends(scoped_db), user: User = Depends(current_user)):
    """Start (or restart) analysis. Poll GET /api/papers/{id}/analysis for the result."""
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    if p.status == "analyzing":
        return {"paper_id": p.id, "status": "analyzing", "message": "Analysis is already running."}
    st = ai_client.status()  # fail fast with a useful message instead of failing in the background
    if not st["llm_ready"]:
        raise HTTPException(503, st["message"])
    p.status = "analyzing"
    p.error = None
    db.commit()
    background.add_task(svc.run_analysis, p.id, dbsession.session_factory_for(user.id))
    return {"paper_id": p.id, "status": "analyzing", "message": "Analysis started."}


@router.get("/papers/{paper_id}/analysis", response_model=AnalysisOut)
def get_paper_analysis(paper_id: int, db: Session = Depends(scoped_db)):
    p = db.get(Paper, paper_id)
    if not p:
        raise HTTPException(404, f"Paper {paper_id} not found.")
    return AnalysisOut(paper_id=p.id, status=p.status, error=p.error, analysis=get_analysis(p))


@router.get("/papers/{paper_id}/explanation")
def paper_explanation(paper_id: int, refresh: bool = False, db: Session = Depends(scoped_db)):
    """Student-friendly AI explanation of one analyzed paper (cached). Original extracted data is separate."""
    try:
        return explain.node_explanation(db, paper_id, refresh)
    except KeyError:
        raise HTTPException(404, "This paper has not been analyzed yet.")

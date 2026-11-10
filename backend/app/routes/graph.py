from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import current_user, scoped_db
from app.auth_tokens import User
from app.services import graph_explanation_service as explain
from app.services import graph_service, ai_client

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.post("/generate")
def generate_graph(db: Session = Depends(scoped_db)):
    try:
        return graph_service.generate(db)
    except graph_service.GraphError as exc:
        raise HTTPException(400, str(exc))
    except ai_client.AIError as exc:
        raise HTTPException(503, str(exc))


@router.get("")
def get_graph(db: Session = Depends(scoped_db)):
    return graph_service.graph_payload(db)


@router.get("/paper/{paper_id}/neighbors")
def get_neighbors(paper_id: int, db: Session = Depends(scoped_db)):
    try:
        return graph_service.neighbors_payload(db, paper_id)
    except KeyError:
        raise HTTPException(404, f"Paper {paper_id} is not in the graph (not found or not analyzed yet).")


@router.get("/overview")
def graph_overview(paper_ids: str | None = None, refresh: bool = False, db: Session = Depends(scoped_db)):
    """AI overview of the (selected) analyzed papers. Facts are always returned; the AI text may be null with an error."""
    ids = [int(x) for x in paper_ids.split(",") if x.strip().isdigit()] if paper_ids else None
    try:
        return explain.overview(db, ids, refresh)
    except KeyError:
        raise HTTPException(404, "No analyzed papers yet. Analyze at least one paper first.")


@router.get("/edge/{edge_id}/detail")
def edge_detail(edge_id: str, refresh: bool = False, db: Session = Depends(scoped_db)):
    num = edge_id.removeprefix("edge_")
    if not num.isdigit():
        raise HTTPException(404, "Unknown edge id.")
    try:
        return explain.edge_detail(db, int(num), refresh)
    except KeyError:
        raise HTTPException(404, f"Edge {edge_id} not found. Regenerate the graph and try again.")

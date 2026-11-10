from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user, scoped_db
from app.auth_tokens import User
from app.models.ai import Conversation, Message
from app.services import chunk_service, graph_service, mentor_service, ai_client

router = APIRouter(prefix="/api/mentor", tags=["research mentor"])


class ChatRequest(BaseModel):
    message: str | None = Field(default=None, max_length=4000)
    conversation_id: int | None = None
    paper_ids: list[int] | None = None
    opportunity_id: int | None = None
    regenerate: bool = False


@router.get("/suggestions")
def suggestions():
    return {"suggestions": mentor_service.SUGGESTIONS}


@router.get("/status")
def status(db: Session = Depends(scoped_db)):
    return mentor_service.index_status(db)


@router.post("/index")
def index(db: Session = Depends(scoped_db)):
    """Prepare (chunk + embed) papers for retrieval. Safe to call repeatedly."""
    try:
        n = chunk_service.ensure_indexed(db, graph_service.analyzed_papers(db))
    except ai_client.AIError as exc:
        raise HTTPException(503, str(exc))
    return {"newly_indexed": n, **mentor_service.index_status(db)}


@router.post("/chat")
def chat(body: ChatRequest, db: Session = Depends(scoped_db)):
    try:
        return mentor_service.chat(db, body.message, body.conversation_id, body.paper_ids, body.opportunity_id, body.regenerate)
    except graph_service.GraphError as exc:
        raise HTTPException(400, str(exc))
    except KeyError:
        raise HTTPException(404, "Conversation not found.")
    except ai_client.AIError as exc:
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        raise HTTPException(502, str(exc))


@router.get("/conversations")
def conversations(db: Session = Depends(scoped_db)):
    rows = db.scalars(select(Conversation).order_by(Conversation.id.desc())).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in rows]


@router.get("/conversations/{cid}")
def conversation(cid: int, db: Session = Depends(scoped_db)):
    c = db.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found.")
    msgs = db.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.id)).all()
    return {"id": c.id, "title": c.title, "messages": [mentor_service.message_out(m) for m in msgs]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, db: Session = Depends(scoped_db)):
    c = db.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "Conversation not found.")
    db.query(Message).filter(Message.conversation_id == cid).delete()
    db.delete(c); db.commit()
    return {"deleted": cid}

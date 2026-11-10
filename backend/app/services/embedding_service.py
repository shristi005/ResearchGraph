"""Builds the text that represents a paper, embeds it with Ollama, stores the vector as JSON."""
import json

from sqlalchemy.orm import Session

from app.models.paper import Paper
from app.schemas.extraction import PaperExtraction
from app.ai import embeddings
from app.services import ai_client
from app.services.paper_view import display_title, get_analysis

MAX_CHARS = 2400


def combined_text(title: str, a: PaperExtraction) -> str:
    parts = [f"Title: {title}"]
    if a.abstract:
        parts.append(f"Abstract: {a.abstract[:900]}")
    if a.research_problem:
        parts.append(f"Research problem: {a.research_problem}")
    if a.topics:
        parts.append("Topics: " + "; ".join(a.topics))
    if a.methodologies or a.algorithms:
        parts.append("Methodologies: " + "; ".join(a.methodologies + a.algorithms))
    if a.findings:
        parts.append("Findings: " + " ".join(a.findings))
    return "\n".join(parts)[:MAX_CHARS]


def embed_paper(db: Session, p: Paper) -> list[float]:
    a = get_analysis(p)
    if a is None:
        raise ValueError(f"Paper {p.id} has not been analyzed yet.")
    title, _ = display_title(p, a)
    vec = ai_client.embed_documents([combined_text(title, a)])[0]
    p.embedding_json = json.dumps({"model": embeddings.model_id(), "vector": vec})
    p.status = "embedded"
    db.commit()
    return vec


def load_vector(p: Paper) -> list[float] | None:
    if not p.embedding_json:
        return None
    try:
        d = json.loads(p.embedding_json)
        if d.get("model") != embeddings.model_id():   # vectors from another model are never comparable
            return None
        return d["vector"]
    except Exception:
        return None


def ensure_embeddings(db: Session, papers: list[Paper]) -> int:
    """Embed every paper that lacks a vector. Returns how many were newly embedded."""
    n = 0
    for p in papers:
        if load_vector(p) is None:
            embed_paper(db, p)
            n += 1
    return n

"""Research Mentor: retrieval-grounded chat over the user's own uploaded papers."""
import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MENTOR_TOP_K
from app.models.ai import Conversation, Message
from app.models.hypothesis import Hypothesis
from app.models.paper import Paper
from app.models.relationship import Relationship
from app.services import chunk_service, graph_service, llm_service, relationship_view
from app.services.paper_view import display_title, get_analysis

SUGGESTIONS = [
    "Explain this research paper in simple language.",
    "Why are these two papers connected?",
    "What are the major limitations across my uploaded papers?",
    "What research questions can I investigate?",
    "Suggest final-year project ideas based on these papers.",
    "Which research direction is feasible with limited computing resources?",
    "Compare the methodologies used in these papers.",
    "Explain a technical concept from these papers with an example.",
    "What should I read next?",
]

SYSTEM = (
    "You are Research Mentor, a patient tutor for students who are reading the research papers they uploaded. "
    "You get SOURCES (numbered passages from the PDFs with page numbers) and STRUCTURED CONTEXT (extracted summaries, "
    "relationships and research opportunities). Rules: "
    "1) Every claim about what the papers say must carry a source tag such as [S2], using only tags that exist. "
    "2) Start paragraphs with one of these labels when it applies: 'From your papers:' (backed by SOURCES), "
    "'My inference:' (your suggestion or reasoning beyond the sources), 'General knowledge:' (a standard concept "
    "explained without a source), 'Not found in your papers:' (the sources do not contain the answer; say so plainly). "
    "3) Never invent paper titles, page numbers, citations, numbers or results. "
    "4) Use plain language, explain jargon with an example, and keep the answer under 350 words. "
    "5) Research directions are hypotheses to be validated, never verified gaps.")

_TAG = re.compile(r"\[S(\d+)\]")


def _context(db: Session, papers: list[Paper], opportunity_id: int | None) -> str:
    lines = []
    for p in papers[:8]:
        a = get_analysis(p)
        t = display_title(p, a)[0]
        lines.append(f"- {t} ({a.publication_year or 'year n/a'}, {a.article_type or 'type n/a'}): problem: {a.research_problem or 'n/a'}; "
                     f"topics: {', '.join(a.topics[:5])}; methods: {', '.join((a.methodologies + a.algorithms)[:5])}; "
                     f"limitations: {'; '.join(a.limitations[:2])}")
    ids = {p.id for p in papers}
    titles = {p.id: display_title(p, get_analysis(p))[0] for p in papers}
    rels = [r for r in db.scalars(select(Relationship)) if r.source_id in ids and r.target_id in ids][:15]
    rel_lines = [f"- {titles[r.source_id]} <-> {titles[r.target_id]}: "
                 f"{relationship_view.display(r.type, r.score, relationship_view.shared_of(r))['detail']}" for r in rels]
    opp = []
    for h in db.scalars(select(Hypothesis).order_by(Hypothesis.id)).all()[:8]:
        d = json.loads(h.details_json or "{}")
        opp.append(f"- [{h.kind}, confidence {h.confidence}, review {h.review_status}] {d.get('title') or h.hypothesis}")
    sel = ""
    if opportunity_id:
        h = db.get(Hypothesis, opportunity_id)
        if h:
            d = json.loads(h.details_json or "{}")
            sel = ("\nSELECTED OPPORTUNITY:\n" + json.dumps({k: d.get(k) for k in ("title", "problem", "research_question",
                                                                                   "possible_methodology", "student_direction")}, ensure_ascii=False))
            if h.feasibility_json:
                sel += "\nFEASIBILITY (AI estimate): " + json.dumps(json.loads(h.feasibility_json).get("analysis"), ensure_ascii=False)[:1500]
    return ("PAPERS:\n" + "\n".join(lines) + "\nRELATIONSHIPS:\n" + ("\n".join(rel_lines) or "none yet")
            + "\nRESEARCH OPPORTUNITIES (AI hypotheses):\n" + ("\n".join(opp) or "none yet") + sel)


def index_status(db: Session) -> dict:
    papers = graph_service.analyzed_papers(db)
    from app.models.ai import Chunk
    indexed = {r for (r,) in db.execute(select(Chunk.paper_id).distinct())}
    return {"papers": len(papers), "indexed_papers": sum(1 for p in papers if p.id in indexed)}


def chat(db: Session, message: str | None, conversation_id: int | None, paper_ids: list[int] | None,
         opportunity_id: int | None, regenerate: bool) -> dict:
    analyzed = graph_service.analyzed_papers(db)
    papers = [p for p in analyzed if not paper_ids or p.id in paper_ids]
    if not papers:
        raise graph_service.GraphError("Analyze at least one paper first. Research Mentor answers from your uploaded papers.")

    conv = db.get(Conversation, conversation_id) if conversation_id else None
    if conversation_id and not conv:
        raise KeyError(conversation_id)
    if regenerate:
        if not conv:
            raise graph_service.GraphError("Nothing to regenerate yet.")
        msgs = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)).all()
        if msgs and msgs[-1].role == "assistant":
            db.delete(msgs[-1]); db.commit()
        last_user = next((m for m in reversed(msgs) if m.role == "user"), None)
        if not last_user:
            raise graph_service.GraphError("Nothing to regenerate yet.")
        message = last_user.content
    else:
        if not message or not message.strip():
            raise graph_service.GraphError("Please type a question.")
        if not conv:
            conv = Conversation(title=message.strip()[:80])
            db.add(conv); db.commit(); db.refresh(conv)
        db.add(Message(conversation_id=conv.id, role="user", content=message.strip())); db.commit()

    chunk_service.ensure_indexed(db, papers)
    chunks = chunk_service.retrieve(db, message, [p.id for p in papers], MENTOR_TOP_K)
    titles = {p.id: display_title(p, get_analysis(p))[0] for p in papers}
    sources = [{"tag": f"S{i}", "paper_id": c.paper_id, "paper_title": titles.get(c.paper_id, ""), "page": c.page or None,
                "section": c.section, "text": c.text} for i, c in enumerate(chunks, 1)]
    src_block = "\n".join(f"[{s['tag']}] {s['paper_title']}, p.{s['page'] or '?'} ({s['section']}): {s['text'][:700]}" for s in sources)

    history = db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)).all()[-7:-1]
    msgs = [{"role": m.role, "content": m.content} for m in history]
    msgs.append({"role": "user", "content": f"STRUCTURED CONTEXT:\n{_context(db, papers, opportunity_id)}\n\n"
                                            f"SOURCES:\n{src_block or 'none retrieved'}\n\nQUESTION: {message}"})
    answer = llm_service.call_text("mentor", SYSTEM, msgs)

    warnings = []
    valid = {s["tag"] for s in sources}
    cited = set()
    def fix(m):
        if f"S{m.group(1)}" in valid:
            cited.add(f"S{m.group(1)}")
            return m.group(0)
        warnings.append(f"The answer referred to a source [S{m.group(1)}] that was not provided; the tag was removed.")
        return ""
    answer = _TAG.sub(fix, answer).strip()
    if not cited:
        warnings.append("This answer cites no passages from your papers. Treat it as general guidance, not evidence from them.")
    for s in sources:
        s["cited"] = s["tag"] in cited
    msg = Message(conversation_id=conv.id, role="assistant", content=answer,
                  sources_json=json.dumps(sources), warnings_json=json.dumps(sorted(set(warnings))))
    db.add(msg); db.commit(); db.refresh(msg)
    return {"conversation_id": conv.id, "message": message_out(msg)}


def message_out(m: Message) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content,
            "sources": json.loads(m.sources_json) if m.sources_json else [],
            "warnings": json.loads(m.warnings_json) if m.warnings_json else []}

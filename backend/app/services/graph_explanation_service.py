"""Student-friendly explanations for the graph.

Every response has two halves, kept apart on purpose:
  * deterministic data taken straight from the PDFs (shared terms, quotes with page numbers, extracted fields)
  * an AI-written explanation (cached; absent with an error message when Ollama is unavailable)
"""
from app.utils.text import norm, term_key
from app.services.research_extraction_service import load_document
from app.services.paper_view import display_title, get_analysis
from app.services import cache_service, graph_service, ai_client, llm_service, relationship_view
from app.models.relationship import Relationship
from app.models.paper import Paper
import json
from collections import Counter

from sqlalchemy.orm import Session

from app.config import GEMINI_MODEL, GROQ_MODEL

LLM_MODEL = f"{GROQ_MODEL} / {GEMINI_MODEL}"

PLAIN = ("Write for an undergraduate student who is new to this field: short sentences, plain words, explain any "
         "technical term in a few words. Use ONLY the facts provided. If something is not stated, say 'Not stated "
         "in the paper' instead of guessing. Never invent results, numbers, citations or paper titles.")


class NodeExplanation(llm_service.LLMModel):
    about: str = ""
    problem: str = ""
    importance: str = ""
    approach: str = ""
    findings: str = ""
    limitations: str = ""
    student_takeaways: list[str] = []
    connections: str = ""


class EdgeExplanation(llm_service.LLMModel):
    connected: str = ""
    in_common: list[str] = []
    differences: list[str] = []
    why_read_both: str = ""


class GraphOverview(llm_service.LLMModel):
    research_area: str = ""
    common_themes: list[str] = []
    differences: list[str] = []
    common_methods: list[str] = []
    key_limitations: list[str] = []
    what_to_learn: str = ""


def _paper_facts(p: Paper, a, n_findings=3, n_limits=3) -> dict:
    title, _ = display_title(p, a)
    return {"id": p.id, "title": title, "year": a.publication_year, "article_type": a.article_type,
            "research_problem": a.research_problem, "topics": a.topics[:8],
            "methods": (a.methodologies + a.algorithms)[:8], "findings": a.findings[:n_findings],
            "limitations": a.limitations[:n_limits], "future_work": a.future_work[:3]}


def _run(db: Session, task: str, kind: str, key_parts, system: str, prompt: str, model_cls, refresh: bool):
    key = cache_service.make_key(kind, key_parts)
    if not refresh:
        hit = cache_service.get(db, key)
        if hit is not None:
            return hit, True, None
    try:
        res = llm_service.call_json(
            task, system, prompt, model_cls).model_dump()
    except (ai_client.AIError, ValueError) as exc:
        return None, False, str(exc)
    cache_service.put(db, key, kind, res)
    return res, False, None


# ---------------------------------------------------------------- node
def node_explanation(db: Session, paper_id: int, refresh: bool = False) -> dict:
    p = db.get(Paper, paper_id)
    a = get_analysis(p) if p else None
    if a is None:
        raise KeyError(paper_id)
    try:
        neighbors = graph_service.neighbors_payload(db, paper_id)["neighbors"]
    except KeyError:
        neighbors = []
    nb = [{"title": n["title"], "relations": [r["display"]["detail"]
                                              for r in n["relationships"]]} for n in neighbors]
    facts = {**_paper_facts(p, a), "abstract": (a.abstract or "")[:1200], "objectives": a.objectives[:4],
             "connected_papers": nb[:8]}
    system = (f"{PLAIN}\nReturn JSON with keys: about (what is this paper about, 2 sentences), problem (what problem it "
              "addresses), importance (why that problem matters, using only what the paper says), approach (what the "
              "researchers did), findings (what they found or concluded), limitations (weaknesses the paper states), "
              "student_takeaways (list of 2-4 things a student should understand), connections (how it relates to "
              "the other uploaded papers listed, or 'No connections yet').")
    res, cached, err = _run(db, "node_explain", "node", facts, system,
                            "Paper facts (JSON):\n" + json.dumps(facts, ensure_ascii=False), NodeExplanation, refresh)
    return {"paper_id": paper_id, "ai": res, "cached": cached, "error": err, "model": LLM_MODEL}


# ---------------------------------------------------------------- edge
def _term_quote(p: Paper, term: str):
    doc = load_document(p)
    order = ("abstract", "methodology", "introduction",
             "results", "experiments", "discussion", "conclusion")
    best = None
    for s in doc.sentences:
        if norm(term) in norm(s.text):
            rank = order.index(s.section) if s.section in order else 99
            if best is None or rank < best[0]:
                best = (rank, s)
    return best[1] if best else None


def _evidence(rel: Relationship, pa: Paper, pb: Paper, aa, ab, shared: list[str]) -> list[dict]:
    out = []
    for p, a in ((pa, aa), (pb, ab)):
        title, _ = display_title(p, a)
        n = 0
        for term in shared[:2] if rel.type in ("shared_topic", "shared_methodology", "semantic_similarity") else []:
            s = _term_quote(p, term)
            if s:
                out.append({"paper_id": p.id, "paper_title": title, "term": term, "quote": s.text,
                            "page": s.page or None, "section": s.section})
                n += 1
        if n == 0:
            for e in a.evidence:
                if e.verified and e.field in ("research_problem", "findings", "methodologies"):
                    out.append({"paper_id": p.id, "paper_title": title, "term": None, "quote": e.quote,
                                "page": e.page, "section": e.section})
                    break
    if rel.type == "citation" and shared:
        out.append({"paper_id": rel.source_id, "paper_title": display_title(pa, aa)[0], "term": "reference entry",
                    "quote": shared[0], "page": None, "section": "references"})
    return out


def edge_detail(db: Session, edge_id: int, refresh: bool = False) -> dict:
    rel = db.get(Relationship, edge_id)
    if not rel:
        raise KeyError(edge_id)
    pa, pb = db.get(Paper, rel.source_id), db.get(Paper, rel.target_id)
    aa, ab = get_analysis(pa), get_analysis(pb)
    if aa is None or ab is None:
        raise KeyError(edge_id)
    shared = relationship_view.shared_of(rel)
    disp = relationship_view.display(rel.type, rel.score, shared)
    facts = {"relationship": rel.type, "detail": disp["detail"], "shared_items": shared,
             "paper_a": _paper_facts(pa, aa, 2, 2) | {"abstract": (aa.abstract or "")[:700]},
             "paper_b": _paper_facts(pb, ab, 2, 2) | {"abstract": (ab.abstract or "")[:700]}}
    system = (f"{PLAIN}\nExplain why TWO papers are connected in the graph. Return JSON with keys: connected (why are "
              "these papers connected, 2 sentences; if the relationship is 'citation' say that A lists B in its "
              "references), in_common (list of 2-3 specific things they share), differences (list of 2-3 specific "
              "differences in focus, method or scope, naming each paper by title), why_read_both (why a student "
              "benefits from reading both). Do not explain the numeric score.")
    ai, cached, err = _run(db, "edge_explain", "edge", facts, system,
                           "Facts about the two papers (JSON):\n" +
                           json.dumps(facts, ensure_ascii=False),
                           EdgeExplanation, refresh)
    return {"edge_id": f"edge_{rel.id}", "type": rel.type, "display": disp, "shared_items": shared,
            "papers": [{"id": pa.id, "title": display_title(pa, aa)[0], "year": aa.publication_year},
                       {"id": pb.id, "title": display_title(pb, ab)[0], "year": ab.publication_year}],
            "evidence": _evidence(rel, pa, pb, aa, ab, shared), "ai": ai, "cached": cached, "error": err,
            "model": LLM_MODEL}


# ---------------------------------------------------------------- overview
def _common(sets: list[tuple[int, list[str]]], top: int = 8) -> list[dict]:
    seen: dict[str, str] = {}
    papers: dict[str, set[int]] = {}
    for pid, terms in sets:
        for t in terms:
            k = term_key(t)
            seen.setdefault(k, t)
            papers.setdefault(k, set()).add(pid)
    ranked = sorted(papers.items(), key=lambda kv: (-len(kv[1]), seen[kv[0]]))
    return [{"term": seen[k], "papers": len(v)} for k, v in ranked if len(v) >= 2][:top]


def overview(db: Session, paper_ids: list[int] | None = None, refresh: bool = False) -> dict:
    papers = [p for p in graph_service.analyzed_papers(
        db) if not paper_ids or p.id in paper_ids]
    if not papers:
        raise KeyError("no analyzed papers")
    ids = {p.id for p in papers}
    analyses = {p.id: get_analysis(p) for p in papers}
    rels = [r for r in db.query(Relationship).all(
    ) if r.source_id in ids and r.target_id in ids]
    titles = {p.id: display_title(p, analyses[p.id])[0] for p in papers}
    facts = {
        "n_papers": len(papers),
        "n_connections": len(rels),
        "common_topics": _common([(p.id, analyses[p.id].topics + analyses[p.id].keywords) for p in papers]),
        "common_methods": _common([(p.id, analyses[p.id].methodologies + analyses[p.id].algorithms) for p in papers]),
        "papers": [{"id": p.id, "title": titles[p.id]} for p in papers],
    }
    llm_facts = {"papers": [_paper_facts(p, analyses[p.id], 2, 2) for p in papers[:12]],
                 "connections": [{"between": [titles[r.source_id], titles[r.target_id]],
                                  "detail": relationship_view.display(r.type, r.score, relationship_view.shared_of(r))["detail"]}
                                 for r in rels[:20]]}
    system = (f"{PLAIN}\nYou are given several uploaded papers and how they are connected. Return JSON with keys: "
              "research_area (what overall research area they explore, 2 sentences), common_themes (list of 2-4), "
              "differences (list of 2-4 major differences between the papers, naming them by title), common_methods "
              "(list of methods several papers use, or an empty list), key_limitations (list of 2-4 important "
              "limitations the papers state), what_to_learn (what a student can learn by reading these papers "
              "together, 2 sentences). If only one paper is given, describe that paper and leave comparisons empty.")
    ai, cached, err = _run(db, "graph_overview", "overview", llm_facts, system,
                           "Uploaded papers and their connections (JSON):\n" + json.dumps(
                               llm_facts, ensure_ascii=False),
                           GraphOverview, refresh)
    return {"facts": facts, "ai": ai, "cached": cached, "error": err, "model": LLM_MODEL}

"""Builds relationships, persists them, and exposes the graph through NetworkX."""
from collections import Counter

import json
import re

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models.paper import Paper
from app.models.relationship import Relationship
from app.services import citation_service, embedding_service, relationship_view
from app.services.paper_view import display_title, get_analysis
from app.services.similarity_service import Edge, PaperFeatures, compute_edges


class GraphError(Exception):
    """User-facing problem (maps to HTTP 400)."""


def analyzed_papers(db: Session) -> list[Paper]:
    return [p for p in db.scalars(select(Paper).order_by(Paper.id)) if get_analysis(p) is not None]


def generate(db: Session) -> dict:
    papers = analyzed_papers(db)
    if len(papers) < 2:
        raise GraphError(f"Analyze at least 2 papers before generating a graph (currently {len(papers)} analyzed).")

    newly_embedded = embedding_service.ensure_embeddings(db, papers)

    feats, titles, analyses = [], {}, {}
    for p in papers:
        a = get_analysis(p)
        title, _ = display_title(p, a)
        titles[p.id], analyses[p.id] = title, a
        feats.append(PaperFeatures(p.id, title, a.topics + a.keywords, a.methodologies + a.algorithms,
                                   embedding_service.load_vector(p)))
    edges = compute_edges(feats)

    # citations: explicit reference list + confident title match only (never from similarity)
    for p in papers:
        targets = [(q.id, titles[q.id]) for q in papers
                   if q.id != p.id and display_title(q, analyses[q.id])[1] != "filename"]
        for tid, (conf, entry) in citation_service.find_citations(p.raw_text, targets).items():
            snippet = entry if len(entry) <= 200 else entry[:200] + "..."
            edges.append(Edge(p.id, tid, "citation", conf,
                              f"The reference list of '{titles[p.id]}' contains an entry matching the title of "
                              f"'{titles[tid]}' (match confidence {conf:.2f}). Matched entry: \"{snippet}\"", shared=[snippet]))

    db.query(Relationship).delete()
    seen = set()
    for e in edges:
        key = (e.source, e.target, e.type)
        if key in seen:
            continue
        seen.add(key)
        db.add(Relationship(source_id=e.source, target_id=e.target, type=e.type,
                            score=e.score, explanation=e.explanation, shared_json=json.dumps(e.shared)))
    db.commit()
    return {"papers": len(papers), "newly_embedded": newly_embedded, "edges": len(seen),
            "by_type": dict(Counter(k[2] for k in seen)),
            "thresholds": {"similarity": config.SIM_THRESHOLD, "topic_min_shared": config.TOPIC_MIN_SHARED,
                           "method_min_shared": config.METHOD_MIN_SHARED,
                           "citation_min_confidence": config.CITATION_MIN_CONFIDENCE}}


def build_graph(db: Session) -> nx.MultiDiGraph:
    G = nx.MultiDiGraph()
    papers = analyzed_papers(db)
    ids = {p.id for p in papers}
    for p in papers:
        a = get_analysis(p)
        title, src = display_title(p, a)
        G.add_node(p.id, title=title, title_source=src, year=a.publication_year, authors=a.authors,
                   topics=a.topics, methods=a.methodologies + a.algorithms, status=p.status)
    for r in db.scalars(select(Relationship).order_by(Relationship.id)):
        if r.source_id in ids and r.target_id in ids:
            G.add_edge(r.source_id, r.target_id, key=r.type, id=r.id, type=r.type,
                       score=r.score, explanation=r.explanation, shared=relationship_view.shared_of(r))
    return G


def _neighbors(G: nx.MultiDiGraph, n: int) -> set[int]:
    return set(G.successors(n)) | set(G.predecessors(n))


def graph_payload(db: Session) -> dict:
    G = build_graph(db)
    nodes = [{
        "id": f"paper_{n}", "paper_id": n, "title": d["title"], "title_source": d["title_source"],
        "year": d["year"], "authors": d["authors"], "topics": d["topics"], "methods": d["methods"],
        "main_topic": d["topics"][0] if d["topics"] else None,
        "connections": len(_neighbors(G, n)), "status": d["status"],
    } for n, d in G.nodes(data=True)]
    edges = [{
        "id": f"edge_{d['id']}", "source": f"paper_{u}", "target": f"paper_{v}", "type": d["type"],
        "score": d["score"], "explanation": d["explanation"], "shared": d["shared"],
        "display": relationship_view.display(d["type"], d["score"], d["shared"]),
    } for u, v, d in G.edges(data=True)]
    total = db.query(Paper).count()
    return {"nodes": nodes, "edges": edges,
            "meta": {"analyzed_papers": len(nodes), "total_papers": total, "edge_count": len(edges)}}


def neighbors_payload(db: Session, paper_id: int) -> dict:
    G = build_graph(db)
    if paper_id not in G:
        raise KeyError(paper_id)
    out = []
    for n in sorted(_neighbors(G, paper_id)):
        rels = [d for u, v, d in G.edges(data=True) if {u, v} == {paper_id, n}]
        out.append({"id": f"paper_{n}", "paper_id": n, "title": G.nodes[n]["title"],
                    "year": G.nodes[n]["year"],
                    "relationships": [{"id": f"edge_{d['id']}", "type": d["type"], "score": d["score"],
                                       "explanation": d["explanation"], "shared": d["shared"],
                                       "display": relationship_view.display(d["type"], d["score"], d["shared"])}
                                      for d in rels]})
    return {"paper_id": paper_id, "title": G.nodes[paper_id]["title"], "neighbors": out}

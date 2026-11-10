"""Pairwise relationships: embedding similarity, topic overlap, methodology overlap."""
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app import config
from app.utils.text import term_key, terms_match


@dataclass
class PaperFeatures:
    id: int
    title: str
    topics: list[str]      # topics + keywords
    methods: list[str]     # methodologies + algorithms
    vector: list[float]


@dataclass
class Edge:
    source: int
    target: int
    type: str
    score: float | None
    explanation: str
    shared: list[str] = field(default_factory=list)


def overlap(a: list[str], b: list[str]) -> tuple[list[str], float]:
    """Shared terms (greedy one-to-one match) and Jaccard score."""
    ua = list({term_key(x): x for x in a}.values())
    ub = list({term_key(x): x for x in b}.values())
    used: set[int] = set()
    shared: list[str] = []
    for x in ua:
        for j, y in enumerate(ub):
            if j not in used and terms_match(x, y):
                used.add(j)
                shared.append(x)
                break
    union = len(ua) + len(ub) - len(shared)
    return shared, (len(shared) / union if union else 0.0)


def cosine_matrix(vectors: list[list[float]]) -> np.ndarray:
    return cosine_similarity(np.array(vectors, dtype=float))


def _fmt(items: list[str], n: int = 6) -> str:
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more)" if len(items) > n else "")


def compute_edges(papers: list[PaperFeatures], cfg=config) -> list[Edge]:
    """At most one edge per (pair, type). Pairs are stored with the smaller id first."""
    edges: list[Edge] = []
    if len(papers) < 2:
        return edges
    sims = cosine_matrix([p.vector for p in papers])

    # semantic similarity, capped per node so the graph stays readable
    cand = sorted(
        ((float(sims[i, j]), i, j) for i, j in combinations(range(len(papers)), 2)
         if sims[i, j] >= cfg.SIM_THRESHOLD),
        reverse=True,
    )
    count = [0] * len(papers)
    sim_pairs: set[tuple[int, int]] = set()
    for score, i, j in cand:
        if count[i] < cfg.SIM_MAX_EDGES_PER_NODE or count[j] < cfg.SIM_MAX_EDGES_PER_NODE:
            count[i] += 1
            count[j] += 1
            sim_pairs.add((i, j))
            a, b = sorted((papers[i], papers[j]), key=lambda p: p.id)
            st, _ = overlap(a.topics, b.topics)
            sm, _ = overlap(a.methods, b.methods)
            edges.append(Edge(a.id, b.id, "semantic_similarity", round(score, 4),
                              f"Cosine similarity {score:.2f} (threshold {cfg.SIM_THRESHOLD:.2f}) between the combined "
                              f"title, abstract, research problem, topics, methods and findings of "
                              f"'{a.title}' and '{b.title}'.", shared=st + sm))

    for i, j in combinations(range(len(papers)), 2):
        a, b = sorted((papers[i], papers[j]), key=lambda p: p.id)
        shared_t, jt = overlap(a.topics, b.topics)
        if len(shared_t) >= cfg.TOPIC_MIN_SHARED:
            edges.append(Edge(a.id, b.id, "shared_topic", round(jt, 4),
                              f"Both papers list these topics/keywords: {_fmt(shared_t)}.", shared=shared_t))
        shared_m, jm = overlap(a.methods, b.methods)
        if len(shared_m) >= cfg.METHOD_MIN_SHARED:
            edges.append(Edge(a.id, b.id, "shared_methodology", round(jm, 4),
                              f"Both papers use these methods/algorithms: {_fmt(shared_m)}.", shared=shared_m))
    return edges

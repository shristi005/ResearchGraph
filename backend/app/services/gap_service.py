"""Research OPPORTUNITIES (hypotheses) from the stored analyses of the uploaded collection.

Four categories: limitation, methodological, combination (exploratory), future_work.

Design rules
 * Evidence is never written by a model: every quote is a sentence found in the stored PDF text, with its page.
   Statements that could not be matched to a PDF sentence (verified=False) are never used as evidence.
 * Candidates are found by code. The model (optional, background) only phrases the student-facing fields
   from the evidence it is given; a template is used when it is unavailable or fails.
 * Confidence is computed from evidence quality, not from how many papers mention an idea, and is never "high".
"""
import hashlib
import json
from dataclasses import dataclass, field
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MAX_GAP_HYPOTHESES
from app.models.hypothesis import Hypothesis
from app.schemas.extraction import PaperExtraction
from app.services import ai_client, graph_service, llm_service
from app.services.paper_view import display_title, get_analysis
from app.services.research_extraction_service import load_document
from app.services.section_service import Document
from app.services.similarity_service import overlap
from app.utils.text import norm, term_key, tokens

DISCLAIMER = ("These are AI-assisted research hypotheses based on your uploaded papers, not verified discoveries of "
              "research gaps. A topic that is missing from your papers may be well studied elsewhere. Validate every "
              "direction against the wider scientific literature.")
REVIEW_STATES = {"new", "accepted", "rejected", "needs_investigation"}
CATEGORIES = {"limitation": "Limitation-based", "methodological": "Methodological",
              "combination": "Exploratory combination", "future_work": "Future work"}
LEGACY_CATEGORY = {"repeated_limitation": "limitation", "repeated_future_work": "future_work",
                   "unaddressed_future_work": "future_work", "methodology_difference": "methodological",
                   "isolated_problem": "combination", "sparse_topic": "combination"}
DEDICATED = {"limitations", "challenges", "future_work", "conclusion"}


@dataclass
class Ctx:
    id: int
    title: str
    a: PaperExtraction
    doc: Document
    text: str = ""  # normalised full text, for co-occurrence checks


def _ev(c: Ctx, section, quote, page, field_name=None, term=None) -> dict:
    return {"paper_id": c.id, "paper_title": c.title, "section": section, "quote": quote,
            "page": page or None, "field": field_name, "term": term}


def verified(c: Ctx, field_name: str) -> list[tuple[str, dict]]:
    return [(e.item, _ev(c, e.section, e.quote, e.page, field_name))
            for e in c.a.evidence if e.field == field_name and e.verified and e.quote]


def term_evidence(c: Ctx, term: str) -> dict | None:
    order = ("abstract", "methodology", "introduction", "results", "experiments", "discussion", "conclusion")
    best = None
    for s in c.doc.sentences:
        if norm(term) in norm(s.text):
            rank = order.index(s.section) if s.section in order else 99
            if best is None or rank < best[0]:
                best = (rank, s)
    return _ev(c, best[1].section, best[1].text, best[1].page, term=term) if best else None


def _jaccard(a: str, b: str) -> float:
    x, y = set(tokens(a)), set(tokens(b))
    return len(x & y) / len(x | y) if x and y else 0.0


def _related(a: str, b: str) -> bool:
    x, y = set(tokens(a)), set(tokens(b))
    inter = x & y
    return bool(x and y) and len(inter) >= 2 and len(inter) / len(x | y) >= 0.25


def _group(items: list[tuple[Ctx, str, dict]]) -> list[list[tuple[Ctx, str, dict]]]:
    """Union-find over statements from DIFFERENT papers that share content words."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j in combinations(range(len(items)), 2):
        if items[i][0].id != items[j][0].id and _related(items[i][1], items[j][1]):
            parent[find(i)] = find(j)
    groups: dict[int, list] = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), []).append(it)
    return list(groups.values())


def _scope(n: int) -> str:
    return (f"This reflects only the {n} uploaded papers. Not seeing a direction in them does not show it is "
            f"unstudied elsewhere.")


def _confidence(cand: dict, ctxs: dict[int, Ctx]) -> tuple[float, str, list[str]]:
    ev, ids = cand["evidence"], cand["papers"]
    n = len(ids)
    base = {1: 0.10, 2: 0.25}.get(n, 0.35)
    stmts = [e["quote"] for e in ev if e.get("quote")]
    pairs = list(combinations(stmts, 2))
    agree = (sum(_jaccard(a, b) for a, b in pairs) / len(pairs)) if pairs else 0.0
    agree_pts = min(0.2, agree * 0.4) if n > 1 else 0.0
    quality = (sum(1 for e in ev if e["section"] in DEDICATED) / len(ev)) if ev else 0.0
    conf_vals = [ctxs[i].a.extraction_confidence for i in ids if ctxs[i].a.extraction_confidence is not None]
    extraction = sum(conf_vals) / len(conf_vals) if conf_vals else 0.5
    score = base + agree_pts + 0.2 * quality + 0.15 * extraction
    reasons = [f"Supported by {n} paper{'s' if n != 1 else ''}.",
               f"Wording across the quoted statements overlaps {'noticeably' if agree >= 0.25 else 'only a little'}"
               f" (similarity {agree:.2f})." if n > 1 else "Only one paper states this, so it has not been cross-checked.",
               f"{sum(1 for e in ev if e['section'] in DEDICATED)} of {len(ev)} quotes come from dedicated "
               f"Limitations / Challenges / Future work / Conclusion sections.",
               f"Average extraction confidence of the source papers: {extraction:.2f}."]
    if cand["category"] == "combination":
        score = min(score, 0.30)
        reasons.append("Exploratory combination: confidence is capped at low because nothing in the papers directly supports it.")
    if n == 1:
        score = min(score, 0.44)
        reasons.append("Single-source evidence is capped at low confidence until another paper or the wider literature agrees.")
    label = "medium" if score >= 0.45 else "low"
    return round(min(score, 0.85), 2), label, reasons


def _uncertainties(cand: dict, n: int) -> list[str]:
    u = [_scope(n), "Fields were extracted by a small local language model and may be incomplete; check the quotes against the PDFs."]
    cat = cand["category"]
    if cat == "limitation":
        u.append("Similar wording can hide different underlying problems; matching is lexical, not a judgement of equivalence.")
    if cat == "methodological":
        u.append("Method names were extracted automatically; the same technique may appear under different names, and "
                 "the two papers may already be comparable through work outside this collection.")
    if cat == "combination":
        u.append("Exploratory only: the two ideas never appear together in your papers, but they may well be combined "
                 "in literature you have not uploaded. It is a prompt for investigation, not a finding.")
    if cat == "future_work":
        u.append("Authors may already have pursued this in later work, and other uploaded papers may touch on it only indirectly.")
        if cand.get("coverage") == "partly_discussed":
            u.append("Other uploaded papers appear to discuss related topics; read them to see whether this is already addressed.")
    if len(cand["papers"]) == 1:
        u.append("Only one paper supports this, so support is thin.")
    return u


def _validation(cand: dict) -> list[str]:
    cat = cand["category"]
    common = ["Search Google Scholar / arXiv / PubMed for recent work on this exact question before investing time."]
    if cat == "limitation":
        return ["Read the limitation passages in the supporting papers side by side.",
                "Check whether the papers measured the limitation the same way."] + common
    if cat == "methodological":
        return ["Check whether either paper already benchmarks against the other's method.",
                "Compare their datasets and metrics to see whether a fair comparison is possible."] + common
    if cat == "combination":
        return ["Search for papers that combine both ideas; if many exist, reject this direction.",
                "Ask a supervisor whether the combination is meaningful, not just possible."] + common
    return ["Look for follow-up papers by the same authors.", "Check whether the proposed direction has since been published."] + common


def _template(cand: dict, n: int) -> dict:
    """Honest fallback wording, used when the model is unavailable. Fills only what the evidence supports."""
    s, cat = cand["statement"], cand["category"]
    short = s if len(s) <= 110 else s[:107] + "…"
    ds = ["Not stated in the papers. Check the datasets the supporting papers used and look for public alternatives (verify manually)."]
    base = dict(datasets_resources=ds, feasibility_considerations=[
        "Reproducing earlier results may need the original code and data.", "Computing needs are not stated in the papers."])
    if cat == "limitation":
        return {**base, "title": f"Reduce this limitation: {short}",
                "problem": f"The uploaded papers report a weakness: “{s}”",
                "why_matters": "A weakness reported by more than one paper may limit how well current approaches work in practice.",
                "research_question": f"How could the limitation “{short}” be reduced or measured more carefully?",
                "possible_methodology": "Reproduce the limitation on a small public dataset, then change one factor at a time and compare.",
                "student_direction": "Start by reproducing the reported limitation, then test one specific change."}
    if cat == "methodological":
        return {**base, "title": f"Compare different methods: {short}",
                "problem": s, "why_matters": "Papers on similar topics that use different methods are hard to compare directly.",
                "research_question": "Under which conditions does each of the two approaches work better?",
                "possible_methodology": "Run both approaches on the same dataset with the same evaluation metrics.",
                "student_direction": "Implement both methods with an existing library and compare them on one public dataset."}
    if cat == "combination":
        return {**base, "title": f"Exploratory: {short}",
                "problem": s, "why_matters": "Combining ideas from different papers can reveal new questions, but this one is only a prompt.",
                "research_question": "What happens when the two ideas are used together, and is it already studied elsewhere?",
                "possible_methodology": "First do a literature check, then run a small pilot combining the two ideas.",
                "student_direction": "Treat this as a literature-search exercise before any implementation."}
    return {**base, "title": f"Follow up on: {short}",
            "problem": f"The authors suggest as future work: “{s}”",
            "why_matters": "Authors point to next steps they consider useful; this one may still be open.",
            "research_question": f"Can the suggested direction (“{short}”) be carried out and evaluated?",
            "possible_methodology": "Define a small, measurable version of the suggestion and test it against the paper's baseline.",
            "student_direction": "Pick the smallest testable part of the suggestion and evaluate it on a public dataset."}


# ------------------------------------------------------------------ candidate generation
def build(ctxs: list[Ctx], cap: int = MAX_GAP_HYPOTHESES) -> list[dict]:
    n = len(ctxs)
    by_id = {c.id: c for c in ctxs}
    cands: list[dict] = []

    # 1. limitation-based
    lim = [(c, item, ev) for c in ctxs for item, ev in verified(c, "limitations")]
    groups = [g for g in _group(lim) if len({c.id for c, _, _ in g}) >= 2]
    for g in groups:
        cands.append({"category": "limitation", "subtype": "recurring", "statement": g[0][1],
                      "papers": sorted({c.id for c, _, _ in g}), "evidence": [e for _, _, e in g]})
    if len(groups) < 2:
        used = {id(x) for g in groups for x in g}
        singles = [x for x in lim if id(x) not in used][:2]
        for c, item, ev in singles:
            cands.append({"category": "limitation", "subtype": "single_source", "statement": item,
                          "papers": [c.id], "evidence": [ev]})

    # 2. methodological: same topics, different methods
    pairs = []
    for x, y in combinations(ctxs, 2):
        shared_t, _ = overlap(x.a.topics + x.a.keywords, y.a.topics + y.a.keywords)
        mx, my = x.a.methodologies + x.a.algorithms, y.a.methodologies + y.a.algorithms
        if len(shared_t) >= 2 and mx and my and not overlap(mx, my)[0]:
            pairs.append((len(shared_t), x, y, shared_t, mx, my))
    for _, x, y, shared_t, mx, my in sorted(pairs, key=lambda t: (-t[0], t[1].id, t[2].id))[:6]:
        ex, ey = next((e for m in mx if (e := term_evidence(x, m))), None), next((e for m in my if (e := term_evidence(y, m))), None)
        if not ex or not ey:
            continue  # no quotable evidence for the methods -> no opportunity
        cands.append({"category": "methodological", "subtype": "different_methods",
                      "statement": f"“{x.title}” and “{y.title}” study overlapping topics ({', '.join(shared_t[:4])}) but use "
                                   f"different methods ({', '.join(mx[:3])} vs {', '.join(my[:3])}).",
                      "papers": sorted([x.id, y.id]), "evidence": [ex, ey]})

    # 3. exploratory combinations: an ALGORITHM named in one paper x a TOPIC of a RELATED paper (they share a topic
    #    or method) that never appear together in any single uploaded paper
    algos: dict[str, dict] = {}
    topics: dict[str, dict] = {}
    for c in ctxs:
        for pool, vals in ((algos, c.a.algorithms), (topics, c.a.topics)):
            for v in vals:
                k = term_key(v)
                if len(k) >= 3:
                    t = pool.setdefault(k, {"name": v, "papers": set()})
                    t["papers"].add(c.id)
    def support(name):
        return sum(1 for c in ctxs if norm(name) in c.text)
    related = {(x.id, y.id) for x, y in combinations(ctxs, 2)
               if overlap(x.a.topics + x.a.keywords, y.a.topics + y.a.keywords)[0] or overlap(x.a.algorithms + x.a.methodologies, y.a.algorithms + y.a.methodologies)[0]}
    related |= {(b, a) for a, b in related}
    combos = []
    for ka, ta in algos.items():
        for kt, tt in topics.items():
            if ka in kt or kt in ka:
                continue
            if any(norm(ta["name"]) in c.text and norm(tt["name"]) in c.text for c in ctxs):
                continue  # already discussed together somewhere
            pair = next(((i, j) for i in sorted(ta["papers"]) for j in sorted(tt["papers"]) if i != j and (i, j) in related), None)
            if pair:
                combos.append((min(support(ta["name"]), support(tt["name"])), ka, kt, pair))
    taken, shown = set(), 0
    for _, ka, kt, (i, j) in sorted(combos, key=lambda t: (-t[0], t[1], t[2])):
        if shown >= 3 or ka in taken or kt in taken:
            continue
        ta, tt = algos[ka], topics[kt]
        ci, cj = by_id[i], by_id[j]
        e1, e2 = term_evidence(ci, ta["name"]), term_evidence(cj, tt["name"])
        if not e1 or not e2:
            continue
        taken |= {ka, kt}; shown += 1
        cands.append({"category": "combination", "subtype": "never_together",
                      "statement": f"The method “{ta['name']}” (from “{ci.title}”) and the topic “{tt['name']}” (from “{cj.title}”) "
                                   f"are never discussed together in your uploaded papers.",
                      "papers": sorted({i, j}), "evidence": [e1, e2]})

    # 4. future work: repeated or single, and whether other uploaded papers seem to cover it
    fw = [(c, item, ev) for c in ctxs for item, ev in verified(c, "future_work")]
    fw_groups = _group(fw)
    singles_shown = 0
    for g in fw_groups:
        members = sorted({c.id for c, _, _ in g})
        repeated = len(members) >= 2
        if not repeated:
            if singles_shown >= 3:
                continue
            singles_shown += 1
        text = g[0][1]
        pool_hit = [c.id for c in ctxs if c.id not in members and len(set(tokens(text)) & set(tokens(" ".join(
            c.a.topics + c.a.keywords + c.a.methodologies + c.a.algorithms + c.a.objectives + c.a.findings)))) >= 2]
        cands.append({"category": "future_work", "subtype": "repeated" if repeated else "single_source",
                      "statement": text, "papers": members, "evidence": [e for _, _, e in g],
                      "coverage": "partly_discussed" if pool_hit else "not_discussed", "related_papers": pool_hit})

    # score, order (interleave categories so one category cannot crowd out the rest), cap
    quota = {"limitation": 4, "methodological": 3, "combination": 3, "future_work": 4}
    per: dict[str, list[dict]] = {k: [] for k in quota}
    for cd in cands:
        cd["confidence_score"], cd["confidence"], cd["confidence_reasons"] = _confidence(cd, by_id)
        per[cd["category"]].append(cd)
    for k in per:
        per[k] = sorted(per[k], key=lambda d: -d["confidence_score"])[:quota[k]]
    out, i = [], 0
    while len(out) < cap and any(per.values()):
        k = list(quota)[i % 4]
        if per[k]:
            out.append(per[k].pop(0))
        i += 1
    for cd in out:
        cd["key"] = hashlib.sha1(json.dumps([cd["category"], cd["subtype"], cd["papers"],
                                             [e["quote"] for e in cd["evidence"]]]).encode()).hexdigest()[:20]
        cd["uncertainties"], cd["validation_steps"] = _uncertainties(cd, n), _validation(cd)
        cd["reasoning"] = _reasoning(cd)
    return out


def _reasoning(cd: dict) -> str:
    n = len(cd["papers"])
    return {
        "limitation": f"{n} paper(s) state similar weaknesses in their own words (quoted below). A problem that repeats across papers may not be solved by the approaches in this collection.",
        "methodological": "The two papers share topics but list no common method, so a direct comparison may not exist in this collection.",
        "combination": "Each idea appears in your papers, but never together in the same paper. This is an exploratory prompt, not evidence of a gap.",
        "future_work": f"The authors recommend this next step. {'Several papers suggest similar directions.' if n > 1 else 'Only one paper suggests it.'} "
                       + ("Other uploaded papers seem to discuss related topics." if cd.get("coverage") == "partly_discussed"
                          else "The other uploaded papers do not clearly discuss it (which does not mean it is unexplored)."),
    }[cd["category"]]


# ------------------------------------------------------------------ persistence + AI wording
def _contexts(db: Session) -> list[Ctx]:
    ctxs = []
    for p in graph_service.analyzed_papers(db):
        a = get_analysis(p)
        ctxs.append(Ctx(p.id, display_title(p, a)[0], a, load_document(p), norm(p.raw_text)))
    return ctxs


def generate(db: Session) -> list[Hypothesis]:
    ctxs = _contexts(db)
    if len(ctxs) < 2:
        raise graph_service.GraphError(
            f"Analyze at least 2 papers before generating research opportunities (currently {len(ctxs)}).")
    cands = build(ctxs)
    old = {h.key: h for h in db.scalars(select(Hypothesis))}
    for h in old.values():
        db.delete(h)
    db.flush()
    rows = []
    for cd in cands:
        details = {**_template(cd, len(ctxs)), "subtype": cd["subtype"], "source": "template",
                   "confidence_score": cd["confidence_score"], "confidence_reasons": cd["confidence_reasons"],
                   "coverage": cd.get("coverage"), "related_papers": cd.get("related_papers", []),
                   "facts": {"category": cd["category"], "statement": cd["statement"], "papers": [by.title for by in ctxs if by.id in cd["papers"]],
                             "evidence": [{"paper": e["paper_title"], "page": e["page"], "section": e["section"], "quote": e["quote"]} for e in cd["evidence"]],
                             "coverage": cd.get("coverage")}}
        prev = old.get(cd["key"])
        row = Hypothesis(
            key=cd["key"], kind=cd["category"], hypothesis=cd["statement"],
            supporting_paper_ids=json.dumps(cd["papers"]), evidence=json.dumps(cd["evidence"]),
            reasoning=cd["reasoning"], uncertainties=json.dumps(cd["uncertainties"]),
            validation_steps=json.dumps(cd["validation_steps"]), confidence=cd["confidence"],
            review_status=prev.review_status if prev else "new", details_json=json.dumps(details),
            feasibility_json=prev.feasibility_json if prev else None, enrichment_status="template")
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


class GapDetails(llm_service.LLMModel):
    title: str = ""
    problem: str = ""
    why_matters: str = ""
    research_question: str = ""
    possible_methodology: str = ""
    datasets_resources: list[str] = []
    student_direction: str = ""
    feasibility_considerations: list[str] = []


GAP_SYSTEM = (
    "You help students turn evidence from research papers into a possible research direction. Use ONLY the evidence "
    "given. Write plain language for an undergraduate. Hedge: say 'could', 'might', 'one option'. Never claim the "
    "direction is novel, unexplored or a verified gap. Mention datasets or tools ONLY if the evidence names them; "
    "otherwise write 'Not stated in the papers; verify manually'. Return JSON with keys: title (short), problem (simple "
    "language), why_matters, research_question, possible_methodology, datasets_resources (list), student_direction "
    "(a concrete small project), feasibility_considerations (list).")


def enrich_all(ids: list[int], session_factory) -> None:
    """Background job: replace template wording with model-written wording grounded in each opportunity's evidence."""
    for hid in ids:
        db = session_factory()
        try:
            h = db.get(Hypothesis, hid)
            if not h:
                continue
            details = json.loads(h.details_json or "{}")
            facts = details.get("facts", {})
            try:
                res = llm_service.call_json("gap_details", GAP_SYSTEM,
                                            "Evidence and context (JSON):\n" + json.dumps(facts, ensure_ascii=False), GapDetails)
            except (ai_client.AIError, ValueError) as exc:
                h.enrichment_status = "failed"
                details["note"] = f"AI wording unavailable ({exc}). Showing evidence-based template text."
                h.details_json = json.dumps(details)
                db.commit()
                continue
            for k, v in res.model_dump().items():
                if v:
                    details[k] = v
            details["source"] = "ai"
            h.details_json = json.dumps(details)
            h.enrichment_status = "done"
            db.commit()
        finally:
            db.close()

"""Independent analysis service.

stored layout -> sections (section_service) -> text within the context budget + candidate limitation /
future-work sentences -> Ollama (JSON) -> Pydantic validation -> grounding + evidence lookup.
"""
import threading

from pydantic import ValidationError

from app.models.paper import Paper
from app.schemas.extraction import EvidenceItem, PaperExtraction, SectionStatus
from app.services import ai_client, section_service as ss
from app.services.pdf_service import paras_from_layout
from app.utils.text import norm

# Only one LLM job talks to Ollama at a time (small local models cannot parallelise well).
ANALYSIS_LOCK = threading.Lock()

HEAD_CHARS = 4500
BUDGET = {"abstract": 1800, "introduction": 1200, "background": 600, "methodology": 1500, "experiments": 800,
          "results": 1500, "discussion": 800, "conclusion": 1000, "limitations": 800, "challenges": 900,
          "future_work": 800}

SYSTEM = (
    "You extract structured information from research papers. "
    "Use ONLY information stated in the provided text. If something is not stated, use null "
    "(or an empty list). Never invent titles, authors, years, findings, limitations or future work. "
    "'limitations' are weaknesses, constraints or open challenges the authors state about the existing work or "
    "their own. 'future_work' are explicit recommendations for what should be done next. Do not put the same "
    "statement in both lists. Copy statements close to the original wording. "
    "Reply with a single JSON object and nothing else."
)

SCHEMA_HINT = """{
 "title": "", "authors": [], "publication_year": null, "abstract": "",
 "research_problem": "", "objectives": [], "topics": [], "keywords": [],
 "methodologies": [], "algorithms": [], "findings": [], "limitations": [], "future_work": []
}"""


def paras_from_text(text: str) -> list[ss.Para]:
    return [ss.Para(0, t.strip()) for t in text.split("\n\n") if t.strip()]


def load_document(p: Paper) -> ss.Document:
    return ss.analyze(paras_from_layout(p.layout_json) or paras_from_text(p.raw_text))


def build_excerpt(doc: ss.Document, raw_text: str) -> tuple[str, list[str]]:
    body = [s for s in BUDGET if s in doc.sections and s != "abstract"]
    if len(body) < 2:  # unstructured paper: fall back to start + end
        tail = raw_text[-3000:] if len(raw_text) > HEAD_CHARS + 3000 else ""
        return (f"### FRONT MATTER\n{raw_text[:HEAD_CHARS]}" + (f"\n\n### END OF PAPER\n{tail}" if tail else ""),
                ["front_matter"] + (["end_of_paper"] if tail else []))
    front = "\n".join(p.text for p in doc.front)[:1200]
    parts, used = [f"### FRONT MATTER\n{front}"], ["front_matter"]
    for name, cap in BUDGET.items():
        t = doc.sections.get(name)
        if t:
            if len(t) > cap:
                t = t[: cap // 2] + " [...] " + t[-cap // 2:] if name == "introduction" else t[:cap]
            parts.append(f"### {name.upper()}\n{t}")
            used.append(name)
    for kind, label in (("limitation", "CANDIDATE LIMITATION SENTENCES"), ("future", "CANDIDATE FUTURE-WORK SENTENCES")):
        c = ss.candidates(doc, kind, cap=10)
        if c:
            parts.append(f"### {label}\n" + "\n".join(f"[p.{s.page}] {s.text}" for s in c))
            used.append(label.lower().replace(" ", "_"))
    return "\n\n".join(parts), used


def ground(ex: PaperExtraction, text: str) -> PaperExtraction:
    """Drop title/authors/year the model could not have read from the paper's opening text."""
    head = norm(text[:HEAD_CHARS])
    warnings = list(ex.warnings)
    if ex.title and norm(ex.title) not in head:
        warnings.append(f"Title '{ex.title}' was not found in the paper's opening text and was removed.")
        ex.title = None
    kept = [a for a in ex.authors if norm(a) in head]
    if len(kept) != len(ex.authors):
        warnings.append("Some authors were not found in the paper's opening text and were removed.")
    ex.authors = kept
    if ex.publication_year and str(ex.publication_year) not in text:
        warnings.append(f"Year {ex.publication_year} does not appear in the paper text and was removed.")
        ex.publication_year = None
    ex.warnings = warnings
    return ex


EVIDENCE_FIELDS = ("research_problem", "objectives", "methodologies", "findings", "limitations", "future_work")


def enrich_analysis(a: PaperExtraction, doc: ss.Document) -> PaperExtraction:
    """Deterministic post-processing (no LLM): verbatim abstract, article type, section report, page-referenced
    evidence for every extracted statement, limitation/future-work separation and an extraction confidence."""
    a.warnings = [w for w in a.warnings if "abstract" not in w.lower() and "could not be matched" not in w
                  and "moved" not in w]
    a.abstract, a.abstract_source, a.abstract_page = doc.abstract, doc.abstract_source, doc.abstract_page
    if not doc.abstract:
        why = next((r["reason"] for r in doc.report if r["section"] == "abstract"), "")
        a.warnings.append(f"Abstract left empty: {why}")
    elif doc.abstract_source == "inferred":
        a.warnings.append("The PDF has no Abstract heading. The abstract shown is the first long paragraph of the front matter, copied word for word. Please check it.")
    a.article_type, a.article_type_reason = doc.article_type, doc.article_type_reason
    a.section_report = [SectionStatus(**r) for r in doc.report]

    # limitation vs future-work separation (a statement is judged by the PDF sentence it comes from)
    def sentence_kind(item, fld):
        s = ss.locate(item, doc, fld)
        return (s, ss.classify_sentence(s.text)) if s else (None, None)
    moved = 0
    for item in list(a.future_work):
        s, kind = sentence_kind(item, "future_work")
        if s and kind == "limitation" and not ss.FUTURE_CUE.search(item):
            a.future_work.remove(item)
            if item not in a.limitations:
                a.limitations.append(item)
            moved += 1
    for item in list(a.limitations):
        s, kind = sentence_kind(item, "limitations")
        if s and kind == "future" and not ss.LIMIT_CUE.search(item):
            a.limitations.remove(item)
            if item not in a.future_work:
                a.future_work.append(item)
            moved += 1
    if moved:
        a.warnings.append(f"{moved} statement(s) were moved between limitations and future work based on their wording in the PDF.")

    ev: list[EvidenceItem] = []
    for fld in EVIDENCE_FIELDS:
        raw = getattr(a, fld)
        for item in ([raw] if isinstance(raw, str) and raw else raw if isinstance(raw, list) else []):
            s = ss.locate(item, doc, fld)
            ev.append(EvidenceItem(field=fld, item=item, quote=s.text if s else None,
                                   page=(s.page or None) if s else None, section=s.section if s else None,
                                   verified=bool(s)))
    a.evidence = ev
    checked = [e for e in ev if e.field in ("limitations", "future_work", "findings")]
    unverified = [e for e in checked if not e.verified]
    if unverified:
        a.warnings.append(f"{len(unverified)} of {len(checked)} limitation / future-work / finding statements could not be matched to a sentence in the PDF. They are shown but are not used as evidence for research opportunities.")
    expected = ["abstract", "introduction"] + (["methodology", "results"] if doc.article_type == "research article" else []) \
        + ["conclusion" if "conclusion" in doc.sections or "discussion" not in doc.sections else "discussion"]
    cover = sum(1 for e in expected if e in doc.sections) / len(expected)
    verif = (sum(e.verified for e in checked) / len(checked)) if checked else 0.5
    a.extraction_confidence = round(0.45 * cover + 0.55 * verif, 2)
    return a


def extract_paper_info(raw_text: str, layout_json: str | None = None) -> PaperExtraction:
    paras = paras_from_layout(layout_json) or paras_from_text(raw_text)
    doc = ss.analyze(paras)
    excerpt, used = build_excerpt(doc, raw_text)
    prompt = (f"Fill in this JSON structure using only the paper excerpt below. Sections are labelled with ###. "
              f"Article type guess: {doc.article_type}.\n{SCHEMA_HINT}\n\nPAPER EXCERPT:\n{excerpt}")
    last_err: Exception | None = None
    for _ in range(2):  # one retry on bad JSON / schema
        try:
            data = ai_client.chat_json(prompt, SYSTEM, "extraction")
            ex = ground(PaperExtraction.model_validate(data), raw_text)
            ex = enrich_analysis(ex, doc)
            ex.sections_used = used
            return ex
        except (ValueError, ValidationError) as exc:
            last_err = exc
    raise ValueError(f"The model's output was not valid after 2 attempts ({last_err}). Try analyzing again.")


def run_analysis(paper_id: int, session_factory) -> None:
    """Background job: analyze one paper and persist the result (or the error)."""
    db = session_factory()
    try:
        p: Paper | None = db.get(Paper, paper_id)
        if not p:
            return
        try:
            with ANALYSIS_LOCK:
                result = extract_paper_info(p.raw_text, p.layout_json)
        except (ai_client.AIError, ValueError) as exc:
            p.error = str(exc)
            p.status = "analyzed" if p.extraction_json else "failed"  # keep an older good analysis
        else:
            p.extraction_json = result.model_dump_json()
            p.status = "analyzed"
            p.error = None
            p.embedding_json = None  # new analysis invalidates the old embedding
        db.commit()
    finally:
        db.close()

"""Section detection on layout-aware paragraphs (works on the output of pdf_service).

Handles: numbered / upper-case / run-in headings, structured abstracts, abstracts with NO heading
(inferred from the front matter), article-type detection, limitation vs future-work sentence candidates,
and locating a quote + page for any extracted statement. Nothing here calls an LLM.
"""
import re
from dataclasses import dataclass, field

from app.utils.text import norm, tokens


@dataclass
class Para:
    page: int
    text: str
    bold: bool = False
    size: float = 0.0
    y: float = 0.0  # vertical position as a fraction of page height


@dataclass
class Sentence:
    page: int
    section: str
    text: str


SECTION_PATTERNS = {
    "abstract": r"abstract|summary|executive summary",
    "introduction": r"introduction",
    "background": r"background|preliminaries|problem (?:statement|formulation)",
    "related_work": r"related work|literature review|prior work|related studies|state of the art",
    "methodology": r"methodology|methods?(?: and materials)?|materials and methods|proposed (?:method|approach|model|framework|system)|approach|model architecture|study design|experimental setup",
    "experiments": r"experiments?|experimental (?:results|evaluation|setup)|evaluation",
    "results": r"results?(?: and discussion)?|findings|analysis",
    "discussion": r"discussion|discussion and conclusions?",
    "limitations": r"(?:study |research )?limitations?|threats to validity",
    "challenges": r"(?:open |key |technical |main )?(?:challenges|problems|questions)(?: and (?:opportunities|future (?:directions|work|research)))?|opportunities and challenges|challenges and opportunities",
    "conclusion": r"conclusions?|concluding remarks|summary and conclusions?",
    "future_work": r"future (?:work|directions|research|perspectives?|outlook)|outlook and future (?:work|directions)|outlook",
    "references": r"references|bibliography|literature cited|works cited",
    "back_matter": r"acknowledge?ments?|appendix(?: [a-z])?|supplementary (?:material|information)|data availability(?: statement)?|code availability|author contributions?|competing interests?|conflicts? of interest|funding|ethics statement|additional information|reporting summary",
}
_COMPILED = [(k, re.compile(v, re.I)) for k, v in SECTION_PATTERNS.items()]
_NUM = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?|[IVXivx]{1,5}\.|[A-H]\.)\s+")
_INLINE = re.compile(r"^\s*(abstract|summary)\s*[:.\u2014\u2013-]\s*(\S.{40,})$", re.I | re.S)
ABSTRACT_SUB = {"background", "methods", "method", "results", "conclusion", "conclusions", "objective", "objectives",
                "purpose", "aim", "aims", "design", "findings", "interpretation", "importance", "context", "setting",
                "participants", "measurements"}

_META = re.compile(
    r"universit|institut|department|school of|faculty|hospital|laborator|centre\b|center for|college|©|copyright|"
    r"creative commons|licen[sc]e|\bdoi\b|https?://|www\.|@[\w.-]+\.|received[: ]|accepted[: ]|published( online)?[: ]|"
    r"corresponding author|e-?mail|orcid|correspondence|contributed equally|open access|check for updates|"
    r"journal homepage|elsevier|springer|nature portfolio|\bieee\b|\barxiv\b|\bvol\.|\bissn\b|all rights reserved|"
    r"peer review|publisher.s note|^keywords?\b|^index terms|^\d+\s*[a-z]+.*\b(usa|uk|germany|china|india|canada)\b",
    re.I)

LIMIT_CUE = re.compile(
    r"\b(limitations?|limited (?:by|to)|is limited|are limited|constraints?|drawbacks?|shortcomings?|"
    r"cannot|can ?not|unable to|fails? to|does not (?:address|account|handle|generali[sz]e)|"
    r"(?:not|yet) (?:been )?(?:addressed|solved|resolved)|remains? (?:challenging|difficult|unclear|an open)|"
    r"lack(?:s|ing)? of|heterogene\w+|biases?|challenges?)\b", re.I)
FUTURE_CUE = re.compile(
    r"\b(future (?:work|research|studies|directions|investigation|efforts)|further (?:research|work|studies|investigation)|"
    r"remains? to be (?:explored|seen|determined|investigated)|should be (?:explored|investigated|studied|addressed|evaluated)|"
    r"will (?:need|require)|needs? to be|we plan to|we intend to|promising (?:direction|avenue)|next steps?|"
    r"open (?:question|problem)s?|worth (?:exploring|investigating)|warrants? (?:further|investigation))\b", re.I)

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\u201c\"(\[])")


def heading_name(line: str) -> str | None:
    s = (line or "").strip()
    if not s or len(s) > 70:
        return None
    s = _NUM.sub("", s).rstrip(":. \u2013-").strip()
    if not s:
        return None
    for name, rx in _COMPILED:
        if rx.fullmatch(s):
            return name
    return None


def is_meta_line(text: str) -> bool:
    return len(text) < 300 and bool(_META.search(text))


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(re.sub(r"\s+", " ", text)) if len(s.strip()) > 25]


def _alpha_ratio(t: str) -> float:
    return sum(c.isalpha() or c == " " for c in t) / max(len(t), 1)


@dataclass
class Document:
    sections: dict[str, str] = field(default_factory=dict)
    section_pages: dict[str, int] = field(default_factory=dict)
    section_method: dict[str, str] = field(default_factory=dict)  # heading | inferred
    paras: dict[str, list[Para]] = field(default_factory=dict)
    front: list[Para] = field(default_factory=list)
    abstract: str | None = None
    abstract_source: str | None = None
    abstract_page: int | None = None
    article_type: str = "unknown"
    article_type_reason: str = ""
    sentences: list[Sentence] = field(default_factory=list)
    report: list[dict] = field(default_factory=list)

    def section_text(self, name: str, limit: int | None = None) -> str:
        t = self.sections.get(name, "")
        return t if limit is None or len(t) <= limit else t[:limit]


def analyze(paragraphs: list[Para]) -> Document:
    doc = Document()
    body_sizes = sorted(p.size for p in paragraphs if len(p.text) > 150 and p.size)
    body = body_sizes[len(body_sizes) // 2] if body_sizes else 0.0
    secs: dict[str, list[Para]] = {}
    cur: str | None = None
    seen: set[str] = set()
    for p in paragraphs:
        m = _INLINE.match(p.text)
        if m and "abstract" not in seen and cur is None:
            seen.add("abstract"); cur = "abstract"
            secs["abstract"] = [Para(p.page, m.group(2).strip(), p.bold, p.size, p.y)]
            doc.section_method["abstract"] = "heading"
            continue
        name = heading_name(p.text)
        if name and body and p.size > 1.35 * body and p.page == 1 and not seen:
            name = None  # title-sized text (e.g. a wrapped title line such as "... perspective"), not a section heading
        if name:
            if name == "abstract" and "abstract" in seen:
                name = "conclusion"
            label = _NUM.sub("", p.text).strip().rstrip(":. ").lower()
            if cur == "abstract" and label in ABSTRACT_SUB and not _NUM.match(p.text) and "introduction" not in seen \
                    and sum(len(x.text) for x in secs["abstract"]) < 3500:
                secs["abstract"].append(Para(p.page, p.text.strip(), True, p.size, p.y))  # sub-label stays in abstract
                continue
            cur = name
            seen.add(name)
            secs.setdefault(name, [])
            doc.section_method.setdefault(name, "heading")
            continue
        if cur is None:
            doc.front.append(p)
        elif cur not in ("references", "back_matter"):
            secs[cur].append(p)

    for name, ps in secs.items():
        if name in ("references", "back_matter"):
            doc.sections[name] = ""
            doc.section_pages[name] = 0
            continue
        ps = [x for x in ps if x.text.strip()]
        doc.paras[name] = ps
        doc.sections[name] = "\n\n".join(x.text for x in ps).strip()
        if ps:
            doc.section_pages[name] = ps[0].page
    doc.sections = {k: v for k, v in doc.sections.items() if v or k in ("references", "back_matter")}

    # --- abstract: heading-based, else inferred from the front matter ---
    ab = doc.sections.get("abstract", "")
    if ab and len(ab) >= 80:
        doc.abstract, doc.abstract_source = ab, "heading"
        doc.abstract_page = doc.section_pages.get("abstract")
    else:
        cands = [p for p in doc.front if p.page <= 2 and len(p.text) >= 350 and not is_meta_line(p.text)
                 and len(split_sentences(p.text)) >= 3 and _alpha_ratio(p.text) > 0.8]
        if cands:
            best = next((p for p in cands if p.bold), cands[0])
            text = re.split(r"\n?\s*(?:Keywords?|Index Terms)\s*[:\u2014-]", best.text, maxsplit=1, flags=re.I)[0].strip()
            doc.abstract, doc.abstract_source, doc.abstract_page = text, "inferred", best.page
            doc.sections["abstract"], doc.section_pages["abstract"] = text, best.page
            doc.section_method["abstract"] = "inferred"

    # --- sentence index (for evidence lookup) ---
    for name, ps in doc.paras.items():
        if name in ("references", "back_matter"):
            continue
        for p in ps:
            for s in split_sentences(p.text):
                doc.sentences.append(Sentence(p.page, name, s))
    if doc.abstract_source == "inferred":
        for s in split_sentences(doc.abstract):
            doc.sentences.append(Sentence(doc.abstract_page or 1, "abstract", s))

    doc.article_type, doc.article_type_reason = detect_article_type(doc, paragraphs)
    doc.report = build_report(doc)
    return doc


def detect_article_type(doc: Document, paragraphs: list[Para]) -> tuple[str, str]:
    head = " ".join(p.text for p in paragraphs[:12]).lower()
    body = (doc.abstract or "") .lower() + " " + doc.sections.get("introduction", "")[:1500].lower()
    has_m, has_r = "methodology" in doc.sections, ("results" in doc.sections or "experiments" in doc.sections)
    for word, label in (("systematic review", "review"), ("meta-analysis", "review"), ("survey", "survey"),
                        ("literature review", "review"), ("perspective", "perspective"), ("viewpoint", "perspective"),
                        ("position paper", "perspective"), ("case study", "case study")):
        if re.search(rf"\b{word}\b", head[:600]):
            return label, f"Front matter mentions “{word}”."
    if re.search(r"\b(this|the present) (review|survey|overview)\b|\bwe (review|survey)\b", body):
        return "review", "Abstract/introduction describes the paper as a review or survey."
    if re.search(r"\b(this|our) (perspective|viewpoint|commentary)\b|\bwe (argue|discuss the opportunities)\b", body):
        return "perspective", "Abstract/introduction frames the paper as a perspective or discussion piece."
    if has_m and has_r and re.search(r"\b(we (propose|present|evaluate|trained|train|develop|conducted|collected|show)|our (method|approach|model|results))\b",
                                      body + " " + doc.sections.get("methodology", "")[:800].lower()):
        return "research article", "Has Methods and Results sections and describes the authors' own experiments."
    if has_m and has_r:
        return "research article", "Has Methods and Results sections."
    if "introduction" in doc.sections and not has_m and not has_r:
        return "review", "No Methods/Results sections; looks like a review, perspective or discussion paper (low confidence)."
    return "unknown", "Not enough section structure to decide."


def build_report(doc: Document) -> list[dict]:
    rep = []
    nonresearch = doc.article_type in ("review", "survey", "perspective")
    cand_l = len(candidates(doc, "limitation"))
    cand_f = len(candidates(doc, "future"))
    for name in ("abstract", "introduction", "methodology", "results", "discussion", "limitations", "conclusion",
                 "future_work", "references"):
        found = bool(doc.sections.get(name)) or (name == "references" and "references" in doc.section_method)
        method = doc.section_method.get(name)
        reason = None
        if not found:
            if name == "abstract":
                reason = "No “Abstract” heading and no abstract-like paragraph (long, non-metadata) before the first section heading."
            elif name in ("methodology", "results") and nonresearch:
                reason = f"Not expected in a {doc.article_type}; such papers usually have no Methods/Results sections."
            elif name == "limitations":
                reason = (f"No dedicated Limitations section; {cand_l} limitation-like sentence(s) found in other sections."
                          if cand_l else "No dedicated Limitations section and no limitation-like sentences found.")
            elif name == "future_work":
                reason = (f"No dedicated Future Work section; {cand_f} sentence(s) with future-work wording found in other sections."
                          if cand_f else "No dedicated Future Work section and no future-work wording found.")
            else:
                reason = f"No heading matching “{name.replace('_', ' ')}” was found."
        elif method == "inferred":
            reason = "Inferred from the front matter (no heading in the PDF); check it."
        rep.append({"section": name, "found": found, "method": method if found else None,
                    "page": doc.section_pages.get(name) or None, "reason": reason})
    return rep


def classify_sentence(s: str) -> str | None:
    f, l = bool(FUTURE_CUE.search(s)), bool(LIMIT_CUE.search(s))
    if f:
        return "future"
    return "limitation" if l else None


def candidates(doc: Document, kind: str, cap: int = 14) -> list[Sentence]:
    """Sentences that may state limitations ('limitation') or future-work recommendations ('future')."""
    dedicated = ("limitations", "challenges") if kind == "limitation" else ("future_work",)
    loose = ("discussion", "conclusion", "results", "experiments") if kind == "limitation" else ("discussion", "conclusion", "challenges")
    out = []
    for s in doc.sentences:
        if s.section in dedicated and 30 <= len(s.text) <= 450:
            out.append(s)
        elif s.section in loose and classify_sentence(s.text) == kind and 30 <= len(s.text) <= 450:
            out.append(s)
    seen, uniq = set(), []
    for s in out:
        k = norm(s.text)
        if k not in seen:
            seen.add(k); uniq.append(s)
    return uniq[:cap]


# which sections to prefer when searching for the source sentence of an extracted field
PREFER = {
    "limitations": ("limitations", "challenges", "discussion", "conclusion", "results", "experiments"),
    "future_work": ("future_work", "conclusion", "discussion", "challenges"),
    "findings": ("results", "experiments", "abstract", "conclusion", "discussion"),
    "methodologies": ("methodology", "experiments", "abstract", "introduction"),
    "objectives": ("abstract", "introduction"),
    "research_problem": ("abstract", "introduction", "background"),
}


def locate(item: str, doc: Document, field_name: str) -> Sentence | None:
    """Best matching sentence in the PDF for an extracted statement, or None (never guesses)."""
    toks = set(tokens(item))
    if not toks:
        return None
    order = {s: i for i, s in enumerate(PREFER.get(field_name, ()))}
    best, best_key = None, None
    short = len(toks) <= 3
    for s in doc.sentences:
        if short:
            if norm(item) in norm(s.text):
                score = 1.0
            else:
                continue
        else:
            score = len(toks & set(tokens(s.text))) / len(toks)
            if score < 0.6:
                continue
        key = (-score if not short else 0, order.get(s.section, 99), s.page)
        if best is None or key < best_key:
            best, best_key = s, key
    return best

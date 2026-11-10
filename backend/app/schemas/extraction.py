from pydantic import AliasChoices, BaseModel, Field, field_validator


def _clean_list(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out, seen = [], set()
    for item in v:
        s = str(item).strip()
        if s and s.lower() not in seen and s.lower() not in {"null", "none", "n/a", "unknown"}:
            seen.add(s.lower())
            out.append(s)
    return out


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if not s or s.lower() in {"null", "none", "n/a", "unknown"} else s


class EvidenceItem(BaseModel):
    """An extracted statement and the sentence in the PDF it was matched to (verified=False: no match found)."""
    field: str
    item: str
    quote: str | None = None
    page: int | None = None
    section: str | None = None
    verified: bool = False


class SectionStatus(BaseModel):
    section: str
    found: bool
    method: str | None = None  # heading | inferred
    page: int | None = None
    reason: str | None = None  # why it is missing, or a caution


class PaperExtraction(BaseModel):
    """Every field is optional: unknown stays empty, never guessed."""
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    # 'year' accepted too so analyses saved by the earlier version still load
    publication_year: int | None = Field(default=None, ge=1900, le=2100,
                                         validation_alias=AliasChoices("publication_year", "year"))
    abstract: str | None = None
    research_problem: str | None = None
    objectives: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    methodologies: list[str] = Field(default_factory=list)
    algorithms: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    future_work: list[str] = Field(default_factory=list)
    # Added by the service, not by the model:
    article_type: str | None = None
    article_type_reason: str | None = None
    abstract_source: str | None = None   # heading | inferred
    abstract_page: int | None = None
    section_report: list[SectionStatus] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    extraction_confidence: float | None = None
    sections_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("title", "abstract", "research_problem", mode="before")
    @classmethod
    def _s(cls, v):
        return _clean_str(v)

    @field_validator("publication_year", mode="before")
    @classmethod
    def _y(cls, v):
        try:
            return int(str(v).strip()[:4]) if v not in (None, "", "null") else None
        except ValueError:
            return None

    @field_validator("authors", "objectives", "topics", "keywords", "methodologies",
                     "algorithms", "findings", "limitations", "future_work", mode="before")
    @classmethod
    def _l(cls, v):
        return _clean_list(v)


class AnalysisOut(BaseModel):
    paper_id: int
    status: str
    error: str | None = None
    analysis: PaperExtraction | None = None

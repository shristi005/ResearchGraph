from pydantic import BaseModel, Field


class Evidence(BaseModel):
    paper_id: int
    paper_title: str = ""
    section: str | None = None
    quote: str | None = None   # a sentence found in the PDF
    page: int | None = None
    field: str | None = None
    term: str | None = None


class FeasibilityRequest(BaseModel):
    compute: str | None = Field(default=None, max_length=200)      # e.g. "laptop, CPU only"
    experience: str | None = Field(default=None, max_length=200)   # e.g. "final-year undergraduate, Python"


class HypothesisOut(BaseModel):
    id: int
    category: str
    category_label: str
    subtype: str | None = None
    title: str
    hypothesis: str                      # the evidence-based statement behind the card
    supporting_paper_ids: list[int]
    evidence: list[Evidence]
    reasoning: str
    problem: str = ""
    why_matters: str = ""
    research_question: str = ""
    possible_methodology: str = ""
    datasets_resources: list[str] = []
    student_direction: str = ""
    feasibility_considerations: list[str] = []
    confidence: str                      # "low" | "medium" (never "high": nothing here is verified)
    confidence_score: float | None = None
    confidence_reasons: list[str] = []
    uncertainties: list[str]
    validation_steps: list[str]
    review_status: str                   # new | accepted | rejected | needs_investigation
    details_source: str = "template"     # ai | template
    enrichment_status: str | None = None  # pending | done | template | failed
    note: str | None = None
    coverage: str | None = None
    feasibility: dict | None = None
    legacy: bool = False
    label: str = "AI-generated hypothesis. Requires human validation."


class GapsResponse(BaseModel):
    disclaimer: str
    paper_count: int
    enriching: bool = False
    hypotheses: list[HypothesisOut]


class ReviewUpdate(BaseModel):
    review_status: str

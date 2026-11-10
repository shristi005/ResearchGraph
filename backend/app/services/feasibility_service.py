"""Student feasibility analysis for one research opportunity (AI-written, cached, never claims verification)."""
import json

from sqlalchemy.orm import Session

from app.models.hypothesis import Hypothesis
from app.services import ai_client, llm_service

MANUAL = ["Dataset availability, computing needs and novelty were NOT checked against external sources. "
          "Search for existing studies and public datasets yourself before committing.",
          "Complexity and undergraduate suitability are the model's estimates from the evidence quotes only. "
          "Ask your supervisor."]


class Feasibility(llm_service.LLMModel):
    complexity: str = ""
    technical_knowledge: list[str] = []
    dataset_availability: str = ""
    computing_requirements: str = ""
    tools: list[str] = []
    implementation_approach: list[str] = []
    challenges: list[str] = []
    evaluation_metrics: list[str] = []
    undergraduate_suitability: str = ""


SYSTEM = (
    "You assess whether a student could carry out a research direction. Use ONLY the opportunity details and "
    "evidence given plus well-known general practice. Do not claim any dataset exists unless the evidence names it; "
    "otherwise write 'Not stated in the papers; must be verified manually'. Do not claim the idea is novel. Be "
    "honest about difficulty. Return JSON with keys: complexity (Low/Medium/High and one sentence why), "
    "technical_knowledge (list), dataset_availability (string), computing_requirements (string), tools (list of "
    "common tools/libraries), implementation_approach (ordered list of 3-6 steps), challenges (list), "
    "evaluation_metrics (list), undergraduate_suitability (Yes/Maybe/No and one sentence why).")


def analyze(db: Session, hid: int, compute: str | None, experience: str | None, refresh: bool) -> dict:
    h = db.get(Hypothesis, hid)
    if not h:
        raise KeyError(hid)
    ctx = {"compute": (compute or "").strip(), "experience": (experience or "").strip()}
    if h.feasibility_json and not refresh:
        saved = json.loads(h.feasibility_json)
        if saved.get("context") == ctx and saved.get("analysis"):
            return {**saved, "cached": True, "error": None}
    d = json.loads(h.details_json or "{}")
    payload = {"opportunity": {k: d.get(k) for k in ("title", "problem", "research_question", "possible_methodology",
                                                       "datasets_resources", "student_direction")},
               "category": h.kind, "evidence": d.get("facts", {}).get("evidence", []),
               "student_context": ctx}
    try:
        res = llm_service.call_json("feasibility", SYSTEM, "Opportunity (JSON):\n" + json.dumps(payload, ensure_ascii=False),
                                    Feasibility).model_dump()
    except (ai_client.AIError, ValueError) as exc:
        return {"context": ctx, "analysis": None, "manual_validation": MANUAL, "cached": False, "error": str(exc)}
    out = {"context": ctx, "analysis": res, "manual_validation": MANUAL}
    h.feasibility_json = json.dumps(out)
    db.commit()
    return {**out, "cached": False, "error": None}

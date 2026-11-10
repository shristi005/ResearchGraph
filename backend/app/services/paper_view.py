"""Small read helpers shared by routes and services."""
import json
from pathlib import Path

from app.models.paper import Paper
from app.schemas.extraction import PaperExtraction


def get_analysis(p: Paper) -> PaperExtraction | None:
    if not p.extraction_json:
        return None
    try:
        return PaperExtraction.model_validate(json.loads(p.extraction_json))
    except Exception:
        return None


def display_title(p: Paper, a: PaperExtraction | None) -> tuple[str, str]:
    """Never invent a title: analysis title > embedded PDF metadata title > filename."""
    if a and a.title:
        return a.title, "analysis"
    t = (p.pdf_title or "").strip()
    low = t.lower()
    junk = low.startswith("microsoft word") or low.startswith("untitled") or low.endswith(
        (".doc", ".docx", ".pdf", ".tex", ".dvi"))
    if len(t) >= 5 and not junk:
        return t, "pdf_metadata"
    return Path(p.original_filename).stem, "filename"

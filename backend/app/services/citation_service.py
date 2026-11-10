"""Citation edges come ONLY from the paper's own reference list matched against other uploaded papers' titles."""
import re

from app.config import CITATION_MIN_CONFIDENCE
from app.utils.text import norm, tokens

_REF_HEAD = re.compile(r"^\s*(?:\d+\.?\s*)?(references|bibliography|works cited)\s*:?\s*$", re.I | re.M)
_SPLIT = re.compile(r"\n\s*(?=\[\d+\]|\d+\.\s)")


def reference_entries(text: str) -> list[str]:
    heads = list(_REF_HEAD.finditer(text))
    if not heads:
        return []
    section = text[heads[-1].end():]
    parts = _SPLIT.split(section)
    if len(parts) < 2:
        parts = re.split(r"\n\s*\n", section)
    entries = [re.sub(r"\s+", " ", p).strip() for p in parts]
    return [e for e in entries if len(e) > 20][:300]


def match_confidence(title: str, entry: str) -> float:
    tt = tokens(title)
    if len(tt) < 3:  # too short/generic to match safely
        return 0.0
    if norm(title) in norm(entry):
        return 1.0
    et = set(tokens(entry))
    cover = sum(1 for t in tt if t in et) / len(tt)
    return round(cover, 3) if len(tt) >= 4 and cover >= CITATION_MIN_CONFIDENCE else 0.0


def find_citations(source_text: str, targets: list[tuple[int, str]]) -> dict[int, tuple[float, str]]:
    """targets = [(paper_id, title)]. Returns {target_id: (confidence, matched reference entry)}."""
    entries = reference_entries(source_text)
    found: dict[int, tuple[float, str]] = {}
    for pid, title in targets:
        best = (0.0, "")
        for e in entries:
            c = match_confidence(title, e)
            if c > best[0]:
                best = (c, e)
        if best[0] >= CITATION_MIN_CONFIDENCE:
            found[pid] = best
    return found

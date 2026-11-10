"""How a relationship is shown to a student: actual shared items + plain-language strength.
Scores are never presented as percentages of agreement."""
import json
import re


def shared_of(rel) -> list[str]:
    """Shared items stored on a relationship row (older rows: recovered from the explanation text)."""
    if getattr(rel, "shared_json", None):
        try:
            return json.loads(rel.shared_json)
        except Exception:
            pass
    if rel.type in ("shared_topic", "shared_methodology"):
        m = re.search(r": (.+)\.$", rel.explanation or "")
        if m:
            return [x.strip() for x in re.sub(r"\(\+\d+ more\)", "", m.group(1)).split(",") if x.strip()]
    return []


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


SEMANTIC_MEANING = ("A similarity score between 0 and 1 computed by an embedding model from the meaning of each "
                    "paper's title, abstract, topics, methods and findings. Higher means the texts are closer in "
                    "meaning. It is a model-derived indicator, not a percentage of scientific agreement, and scores "
                    "can differ between collections.")


def display(rtype: str, score: float | None, shared: list[str]) -> dict:
    n = len(shared)
    if rtype == "semantic_similarity":
        s = score or 0.0
        strength = ("Very close in meaning" if s >= 0.85 else "Close in meaning" if s >= 0.75
                    else "Moderately close" if s >= 0.65 else "Loosely related")
        return {"label": "Similar meaning", "short": f"similar {s:.2f}", "strength": strength,
                "detail": f"Model similarity {s:.2f} out of 1 ({strength.lower()})."
                          + (f" Shared terms: {', '.join(shared[:4])}." if shared else ""),
                "score_meaning": SEMANTIC_MEANING, "numeric": True, "shared_items": shared}
    if rtype == "shared_topic":
        return {"label": "Shared topics", "short": f"{_plural(n, 'topic')}: {shared[0] if shared else ''}"[:44],
                "strength": "Several topics in common" if n >= 4 else "A few topics in common",
                "detail": f"{_plural(n, 'common topic')}: {', '.join(shared)}",
                "score_meaning": "Counts the topics/keywords both papers list. The fraction behind the line "
                                 "(shared ÷ all distinct topics) is only used for ordering, so the shared topics are shown instead.",
                "numeric": False, "shared_items": shared}
    if rtype == "shared_methodology":
        return {"label": "Shared methods", "short": f"{_plural(n, 'method')}: {shared[0] if shared else ''}"[:44],
                "strength": "Several methods in common" if n >= 3 else "A method in common",
                "detail": f"{_plural(n, 'common methodology')}: {', '.join(shared)}"
                          if n == 1 else f"{_plural(n, 'common method')}: {', '.join(shared)}",
                "score_meaning": "Counts the methods/algorithms both papers use. Names are matched after simple "
                                 "normalisation, so different names for the same technique can be missed.",
                "numeric": False, "shared_items": shared}
    return {"label": "Cites", "short": "cites", "strength": "Verified citation",
            "detail": "The citing paper's own reference list contains an entry matching the other paper's title.",
            "score_meaning": f"Match confidence {score:.2f} between the reference entry and the cited paper's title. "
                             "Only references actually printed in the PDF are used; similarity never creates a citation."
                             if score is not None else "",
            "numeric": False, "shared_items": []}

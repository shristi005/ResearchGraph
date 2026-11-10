import re

STOP = set(
    "a an the of and or for in on to with by from at as is are was were be been this that these those it its "
    "into using use used based via over under between than their our we can may not no more most less such "
    "which also both each other paper papers study studies approach approaches model models method methods only one many much very still while could would should does did has have had been being".split()
)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def stem(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(s: str) -> list[str]:
    return [stem(w) for w in norm(s).split() if w not in STOP and len(w) > 2]


def term_key(s: str) -> str:
    return " ".join(tokens(s)) or norm(s)


def terms_match(a: str, b: str) -> bool:
    ka, kb = term_key(a), term_key(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    # whole-word containment, e.g. "bert" inside "bert based classifier"
    return (len(ka) >= 4 and f" {ka} " in f" {kb} ") or (len(kb) >= 4 and f" {kb} " in f" {ka} ")

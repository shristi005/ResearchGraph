"""Layout-aware PDF extraction. No LLM, no DB, no HTTP here.

Uses PyMuPDF's 'dict' output (blocks -> lines -> spans with font size/bold) so we can:
 * read two-column pages in the right order,
 * keep every paragraph's page number,
 * split headings from body text,
 * drop repeated headers/footers and page numbers.
"""
import json
import re
from dataclasses import dataclass, field

import pymupdf

from app.services.section_service import Para, heading_name


class PDFExtractionError(Exception):
    pass


@dataclass
class PDFContent:
    text: str
    page_count: int
    title: str | None = None
    author: str | None = None
    paras: list[Para] = field(default_factory=list)

    @property
    def layout_json(self) -> str:
        return json.dumps([[p.page, p.text, int(p.bold), round(p.size, 1), round(p.y, 3)] for p in self.paras])


def paras_from_layout(layout_json: str | None) -> list[Para]:
    if not layout_json:
        return []
    try:
        return [Para(int(r[0]), r[1], bool(r[2]), float(r[3]), float(r[4])) for r in json.loads(layout_json)]
    except Exception:
        return []


def _order_blocks(blocks: list[dict], width: float) -> list[dict]:
    """Reading order: full-width blocks split the page into bands; inside a band, left column then right."""
    full = sorted((b for b in blocks if b["bbox"][2] - b["bbox"]
                  [0] >= 0.62 * width), key=lambda b: b["bbox"][1])
    narrow = [b for b in blocks if b not in full]
    ys = [b["bbox"][1] for b in full]
    bands: list[list[dict]] = [[] for _ in range(len(full) + 1)]
    for b in narrow:
        bands[sum(1 for y in ys if y <= b["bbox"][1])].append(b)
    mid, out = width / 2, []
    for k, band in enumerate(bands):
        left = sorted((b for b in band if b["bbox"][0] < mid - 5),
                      key=lambda b: (b["bbox"][1], b["bbox"][0]))
        right = sorted(
            (b for b in band if b["bbox"][0] >= mid - 5), key=lambda b: (b["bbox"][1], b["bbox"][0]))
        out += left + right
        if k < len(full):
            out.append(full[k])
    return out


def _join(lines: list[str]) -> str:
    text = ""
    for ln in lines:
        if text.endswith("-") and ln[:1].islower():
            # de-hyphenate a word broken across lines
            text = text[:-1] + ln
        else:
            text = (text + " " + ln).strip()
    return re.sub(r"\s+", " ", text.replace("\x00", ""))


def _block_paragraphs(block: dict, page_no: int, height: float) -> list[Para]:
    out: list[Para] = []
    cur: list[str] = []
    cur_meta = [0.0, False, 0.0]  # size, bold, y

    def flush():
        if cur:
            out.append(Para(page_no, _join(cur),
                       cur_meta[1], cur_meta[0], cur_meta[2]))
            cur.clear()

    for line in block.get("lines", []):
        spans = [s for s in line["spans"] if s["text"].strip()]
        if not spans:
            continue
        text = re.sub(r"\s+", " ", "".join(s["text"] for s in spans)).strip()
        size = max(s["size"] for s in spans)
        bold = all((s["flags"] & 16) or "bold" in s["font"].lower()
                   for s in spans)
        y = line["bbox"][1] / height
        is_heading = bool(heading_name(text)) or (bold and len(
            text) < 90 and not text.endswith((".", ",", ";")))
        if is_heading:
            flush()
            out.append(Para(page_no, text, True, size, y))
            continue
        if not cur:
            cur_meta[:] = [size, bold, y]
        cur.append(text)
    flush()
    return out


def extract_text(pdf_bytes: bytes) -> PDFContent:
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFExtractionError(
            f"Could not open PDF (corrupt or encrypted?): {exc}") from exc

    try:
        if doc.needs_pass:
            raise PDFExtractionError("PDF is password-protected.")
        paras: list[Para] = []
        for i, page in enumerate(doc, 1):
            d = page.get_text("dict")
            blocks = [b for b in d["blocks"] if b["type"] == 0]
            for b in _order_blocks(blocks, page.rect.width):
                paras += _block_paragraphs(b, i, page.rect.height)
        meta = doc.metadata or {}
        n_pages = doc.page_count
    finally:
        doc.close()

    # drop page numbers and headers/footers repeated on several pages
    zone = [p for p in paras if p.y < 0.07 or p.y > 0.92]
    counts: dict[str, set[int]] = {}
    for p in zone:
        counts.setdefault(
            re.sub(r"\d+", "#", p.text.lower()), set()).add(p.page)
    drop = {id(p) for p in zone
            if re.fullmatch(r"(page )?\d{1,4}( of \d+)?", p.text.strip().lower())
            or (len(counts[re.sub(r"\d+", "#", p.text.lower())]) >= 3 and len(p.text) < 120)}
    paras = [p for p in paras if id(p) not in drop and p.text.strip()]

    return PDFContent(
        text="\n\n".join(p.text for p in paras).replace("\x00", "").strip(),
        page_count=n_pages,
        title=(meta.get("title") or "").replace("\x00", "").strip() or None,
        author=(meta.get("author") or "").replace("\x00", "").strip() or None,
        paras=paras,
    )

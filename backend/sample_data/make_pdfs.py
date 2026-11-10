"""Writes the synthetic demo papers to ../sample_papers/*.pdf  (run from backend/: python -m sample_data.make_pdfs)"""
import re
import textwrap
from pathlib import Path

import pymupdf

from sample_data.samples import SAMPLES, paper_text

OUT = Path(__file__).resolve().parent.parent.parent / "sample_papers"


def make_pdf(text: str, title: str, author: str | None) -> bytes:
    lines = []
    for raw in text.splitlines():
        lines += textwrap.wrap(raw, 92) or [""]
    doc = pymupdf.open()
    for i in range(0, len(lines), 58):
        page = doc.new_page()
        y = 60
        for ln in lines[i:i + 58]:
            page.insert_text((60, y), ln, fontsize=10, fontname="helv")
            y += 12.5
    if author:
        doc.set_metadata({"title": title, "author": author})
    data = doc.tobytes()
    doc.close()
    return data


def main():
    OUT.mkdir(exist_ok=True)
    for i, s in enumerate(SAMPLES, 1):
        name = f"{i:02d}_" + re.sub(r"[^a-z0-9]+", "_", s["title"].lower())[:50].strip("_") + ".pdf"
        (OUT / name).write_bytes(make_pdf(paper_text(s), s["title"], ", ".join(s["authors"]) if s["meta"] else None))
        print("wrote", name)


if __name__ == "__main__":
    main()

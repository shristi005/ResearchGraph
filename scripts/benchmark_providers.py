#!/usr/bin/env python3
"""Development-time benchmark: Groq vs Gemini on REAL paper extraction (separate from production traffic).
Needs the backend dependencies installed (PyMuPDF, pydantic, sqlalchemy) and both API keys in the environment.

    cd backend && python ../scripts/benchmark_providers.py --pdf-dir /path/to/your/six/pdfs --sleep 8

For each PDF and each provider it sends the SAME extraction prompt the app uses and records: valid JSON?, schema-valid?,
share of limitation/future-work/finding statements that are found verbatim in the PDF (evidence grounding), number of
topics/methods/datasets found, latency, tokens. Results: benchmark_results/extraction.json + extraction.md.
It uses about 2 requests per PDF (one per provider) - keep --sleep above your free requests-per-minute window.
Use the table to set FEATURE_PROVIDER in backend/app/ai/router.py (or AI_PRIMARY_PROVIDER / *_MODEL_<FEATURE> env vars)."""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env  # noqa: E402
_env.load()
from pydantic import ValidationError  # noqa: E402
from app import config  # noqa: E402
from app.ai.providers import PROVIDERS  # noqa: E402
from app.schemas.extraction import PaperExtraction  # noqa: E402
from app.services import research_extraction_service as rx, section_service as ss  # noqa: E402
from app.services.pdf_service import extract_text  # noqa: E402


def one(provider, pdf: Path, models: dict):
    c = extract_text(pdf.read_bytes())
    paras = rx.paras_from_layout(c.layout_json) or rx.paras_from_text(c.text)
    doc = ss.analyze(paras)
    excerpt, _ = rx.build_excerpt(doc, c.text)
    prompt = (f"Fill in this JSON structure using only the paper excerpt below. Sections are labelled with ###. "
              f"Article type guess: {doc.article_type}.\n{rx.SCHEMA_HINT}\n\nPAPER EXCERPT:\n{excerpt}")
    row = {"pdf": pdf.name, "provider": provider.name, "model": models.get(provider.name) or provider.default_model(),
           "json_ok": False, "schema_ok": False}
    try:
        r = provider.chat(rx.SYSTEM, [{"role": "user", "content": prompt}], json_mode=True, temperature=0, model=row["model"])
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return row
    row.update(latency_s=round(r.latency_s, 2), tokens=r.total_tokens)
    try:
        data = json.loads(r.text); row["json_ok"] = isinstance(data, dict)
        ex = rx.ground(PaperExtraction.model_validate(data), c.text); row["schema_ok"] = True
        ex = rx.enrich_analysis(ex, doc)
        chk = [e for e in ex.evidence if e.field in ("limitations", "future_work", "findings")]
        row.update(grounded=round(sum(e.verified for e in chk) / len(chk), 2) if chk else None, n_checked=len(chk),
                   topics=len(ex.topics), methods=len(ex.methodologies) + len(ex.algorithms), datasets=len(ex.datasets),
                   limitations=len(ex.limitations), future_work=len(ex.future_work), confidence=ex.extraction_confidence)
    except (ValueError, ValidationError) as exc:
        row["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--pdf-dir", required=True); ap.add_argument("--sleep", type=float, default=8)
    a = ap.parse_args()
    pdfs = sorted(Path(a.pdf_dir).glob("*.pdf"))
    if not pdfs:
        sys.exit("No PDFs found.")
    provs = [p for p in PROVIDERS.values() if p.configured()]
    rows = []
    for pdf in pdfs:
        for p in provs:
            rows.append(one(p, pdf, {})); print(rows[-1], flush=True); time.sleep(a.sleep)
    out = Path("benchmark_results"); out.mkdir(exist_ok=True)
    (out / "extraction.json").write_text(json.dumps(rows, indent=1))
    md = ["| PDF | provider | model | json | schema | grounded | topics | methods | s | tokens | error |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['pdf'][:40]} | {r['provider']} | {r['model']} | {r['json_ok']} | {r['schema_ok']} | {r.get('grounded')} | {r.get('topics')} | {r.get('methods')} | {r.get('latency_s')} | {r.get('tokens')} | {r.get('error', '')} |")
    (out / "extraction.md").write_text("\n".join(md)); print("\n".join(md))

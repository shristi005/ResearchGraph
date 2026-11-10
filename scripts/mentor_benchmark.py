#!/usr/bin/env python3
"""The seven Research Mentor benchmark checks, run against a RUNNING backend with your six benchmark PDFs uploaded+analyzed.
    python scripts/mentor_benchmark.py --api http://127.0.0.1:8000 [--token <supabase access token>]
Papers are located by title substrings below (this is test selection only - nothing like it exists in production code).
Automatic checks catch structural failures (wrong paper in sources, missing page, uncited answer, quote not found in a source).
ANSWER QUALITY STILL NEEDS YOUR READING: the report prints every answer and its sources to benchmark_results/mentor.md."""
import argparse, json, re, sys, urllib.request
from pathlib import Path

KEY = {"crop": "crop disease", "bridge": "bridge defect", "m1": "music mixing", "m2": "text-to-music",
       "m3": "confrontation", "m4": "transfer learning"}


def call(api, path, token, body=None):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--api", default="http://127.0.0.1:8000"); ap.add_argument("--token", default="")
    a = ap.parse_args()
    papers = call(a.api, "/api/papers", a.token)
    ids = {}
    for k, sub in KEY.items():
        m = [p for p in papers if sub in (p["title"] or "").lower() or sub in p["original_filename"].lower()]
        if not m:
            sys.exit(f"Benchmark paper not found for '{sub}'. Upload all six PDFs and analyze them first.")
        ids[k] = m[0]["id"]
    call(a.api, "/api/mentor/index", a.token, {})
    music = [ids[k] for k in ("m1", "m2", "m3", "m4")]
    tests = [
        ("1 crop-paper explanation", "Explain this paper in simple language.", [ids["crop"]], "only", [ids["crop"]]),
        ("2 crop source isolation", "What dataset and methods does this paper use?", [ids["crop"]], "only", [ids["crop"]]),
        ("3 bridge vs crop comparison", "Compare these two papers' methods and limitations.", [ids["bridge"], ids["crop"]], "both", [ids["bridge"], ids["crop"]]),
        ("4 music cluster synthesis", "What do these four papers have in common and how do they differ?", music, "most", music),
        ("5 unanswerable (must abstain)", "What was the exact monetary cost of the clinical trial reported in these papers?", [ids["crop"], ids["bridge"]], "abstain", []),
        ("6 exact limitation + page (transfer-learning paper)", "Quote the limitation this paper states, and give the page.", [ids["m4"]], "quote", [ids["m4"]]),
        ("7 bridge-only dataset/metrics", "Which dataset and evaluation metrics does the bridge paper report?", [ids["bridge"]], "only", [ids["bridge"]]),
    ]
    out, fails = ["# Mentor benchmark (answers need human review)\n"], 0
    for name, q, sel, rule, allowed in tests:
        r = call(a.api, "/api/mentor/chat", a.token, {"message": q, "paper_ids": sel})["message"]
        src, ans, checks = r["sources"], r["content"], []
        used = {s["paper_id"] for s in src}
        if rule != "abstain":
            checks.append(("all sources from selected papers", used <= set(allowed)))
            checks.append(("every source has a page", all(s["page"] for s in src if s["section"] != "references")))
            checks.append(("answer cites a retrieved source", any(s["cited"] for s in src)))
        if rule == "both":
            checks.append(("both papers represented", used >= set(allowed)))
        if rule == "most":
            checks.append(("at least 3 of 4 music papers represented", len(used & set(allowed)) >= 3))
        if rule == "abstain":
            checks.append(("says evidence is insufficient", bool(re.search(r"not (stated|mention|report|provide|contain|found)|no (information|evidence)|cannot|insufficient|do(es)? not", ans, re.I))))
            checks.append(("no confident cited number", not re.search(r"\$\s?\d", ans)))
        if rule == "quote":
            quotes = re.findall(r"[\"“]([^\"”]{25,})[\"”]", ans)
            checks.append(("quoted text appears verbatim in a retrieved source", bool(quotes) and all(any(re.sub(r"\s+", " ", q).strip().lower() in re.sub(r"\s+", " ", s["text"]).lower() for s in src) for q in quotes)))
        ok = all(c[1] for c in checks); fails += (not ok)
        out.append(f"## {name}: {'AUTO-PASS' if ok else 'AUTO-FAIL'}\n**Q:** {q}\n\n**A:** {ans}\n\nchecks: " + "; ".join(f"{'✓' if v else '✗'} {n}" for n, v in checks) + "\n\nsources:\n" +
                   "\n".join(f"- [{s['tag']}] paper {s['paper_id']} p.{s['page']} ({s['section']}) cited={s['cited']}: {s['text'][:120]}…" for s in src) + f"\n\nwarnings: {r['warnings']}\n")
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    Path("benchmark_results").mkdir(exist_ok=True); Path("benchmark_results/mentor.md").write_text("\n".join(out))
    print(f"\n{7 - fails}/7 automatic checks passed. Read benchmark_results/mentor.md - automatic checks are necessary, not sufficient.")


if __name__ == "__main__":
    main()

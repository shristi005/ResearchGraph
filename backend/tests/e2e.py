"""End-to-end run against a LIVE server. Usage: python tests/e2e.py [phase]  (phase: main | persist | outage)"""
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
SAMPLES = sorted((Path(__file__).resolve().parent.parent.parent / "sample_papers").glob("*.pdf"))
c = httpx.Client(base_url=BASE, timeout=120)


def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


def main():
    ok(c.get("/api/health").json() == {"status": "ok"}, "health")
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in SAMPLES]
    r = c.post("/api/papers/upload", files=files).json()["results"]
    ok([x["outcome"] for x in r] == ["created"] * 7, "uploaded 7 PDFs")
    dup = c.post("/api/papers/upload", files=files[:1]).json()["results"][0]
    ok(dup["outcome"] == "duplicate", "duplicate upload detected")
    papers = c.get("/api/papers").json()
    ok(papers[0]["pdf_title"] and papers[2]["pdf_title"] is None, "PDF metadata title captured only when present")
    ok(papers[2]["title_source"] == "filename", "title falls back to filename, never invented")
    pid = papers[0]["id"]
    ok("Abstract" not in c.get(f"/api/papers/{pid}/text").json()["text"][:5] and
       c.get(f"/api/papers/{pid}/file").headers["content-type"] == "application/pdf", "text + original PDF retrievable")

    ok(c.get("/api/graph").json()["nodes"] == [], "graph empty before analysis")
    ok(c.post("/api/graph/generate").status_code == 400, "graph generate refused with <2 analyzed papers")
    ok(c.post("/api/gaps/generate").status_code == 400, "gaps refused with <2 analyzed papers")

    for p in papers:
        ok(c.post(f"/api/papers/{p['id']}/analyze").status_code == 202, f"analyze started for paper {p['id']}")
    for _ in range(60):
        st = {x["id"]: x["status"] for x in c.get("/api/papers").json()}
        if all(v != "analyzing" for v in st.values()):
            break
        time.sleep(0.5)
    ok(all(v == "analyzed" for v in st.values()), f"all papers analyzed {set(st.values())}")
    a = c.get(f"/api/papers/{papers[4]['id']}/analysis").json()["analysis"]
    ok(a["publication_year"] == 2022 and "BERT" in a["algorithms"] and a["abstract"].startswith("We combine BERT"),
       "analysis fields + verbatim abstract")
    ok("future_work" in a["sections_used"] and "limitations" in a["sections_used"], f"sections detected {a['sections_used']}")

    g = c.post("/api/graph/generate").json()
    print("  generate:", g)
    ok(g["papers"] == 7 and g["newly_embedded"] == 7, "embeddings generated for 7 papers")
    graph = c.get("/api/graph").json()
    keys = [(e["source"], e["target"], e["type"]) for e in graph["edges"]]
    ok(len(keys) == len(set(keys)), "no duplicate edges")
    types = {e["type"] for e in graph["edges"]}
    print("  edge types:", {t: sum(1 for e in graph["edges"] if e["type"] == t) for t in types})
    ok({"semantic_similarity", "shared_topic", "shared_methodology", "citation"} <= types, "all 4 relationship types present")
    cites = {(e["source"], e["target"]) for e in graph["edges"] if e["type"] == "citation"}
    id_of = {n["title"]: n["id"] for n in graph["nodes"]}
    t = lambda x: next(v for k, v in id_of.items() if k.startswith(x))
    ok((t("Hybrid BERT"), t("A Survey")) in cites and (t("Graph Neural"), t("Hybrid BERT")) in cites, "expected citations found")
    ok((t("A Survey"), t("Hybrid BERT")) not in cites and not any(t("Lightweight") in e for e in cites),
       "no citation edge from mere similarity (survey->hybrid absent, unrelated paper uncited)")
    ok(all(e["explanation"] for e in graph["edges"]), "every edge has an explanation")
    n = c.get(f"/api/graph/paper/{papers[4]['id']}/neighbors").json()
    ok(len(n["neighbors"]) >= 3, f"neighbors endpoint ({len(n['neighbors'])} neighbors)")
    ok(c.get("/api/graph/paper/9999/neighbors").status_code == 404, "unknown paper neighbors -> 404")

    gaps = c.post("/api/gaps/generate").json()
    ok(len(gaps["hypotheses"]) >= 3 and "not verified discoveries" in gaps["disclaimer"], f"{len(gaps['hypotheses'])} hypotheses + disclaimer")
    kinds = sorted({h["category"] for h in gaps["hypotheses"]})
    print("  kinds:", kinds)
    ok(all(h["evidence"] and h["uncertainties"] and h["validation_steps"] and h["confidence"] in ("low", "medium")
           for h in gaps["hypotheses"]), "each hypothesis has evidence, uncertainties, validation steps, no 'high' confidence")
    good = {x["id"] for x in graph["nodes"] and [{"id": n["paper_id"]} for n in graph["nodes"]]}
    ok(all(set(h["supporting_paper_ids"]) <= good for h in gaps["hypotheses"]), "supporting paper IDs exist")
    r = c.patch(f"/api/gaps/{gaps['hypotheses'][0]['id']}", json={"review_status": "accepted"})
    ok(r.json()["review_status"] == "accepted", "review status saved")
    ok(c.patch("/api/gaps/1", json={"review_status": "proven"}).status_code == 422, "invalid review status rejected")
    again = c.post("/api/gaps/generate").json()
    ok(again["hypotheses"][0]["review_status"] == "accepted", "review survives regeneration")

    # --- v3 features ---
    cats = {h["category"] for h in gaps["hypotheses"]}
    ok(cats <= {"limitation", "methodological", "combination", "future_work"} and len(cats) >= 3, f"opportunity categories {sorted(cats)}")
    for _ in range(40):  # background wording
        cur = c.get("/api/gaps").json()
        if not cur["enriching"]:
            break
        time.sleep(0.5)
    h0 = cur["hypotheses"][0]
    ok(h0["details_source"] == "ai" and h0["title"] and h0["research_question"], "AI wording filled in the background")
    ok(all(e["quote"] and e["page"] for h in cur["hypotheses"] for e in h["evidence"]), "every evidence item has a PDF quote and page")
    ok(all(h["confidence"] in ("low", "medium") and h["confidence_reasons"] for h in cur["hypotheses"]), "confidence has reasons, never high")
    combo = [h for h in cur["hypotheses"] if h["category"] == "combination"]
    ok(all(h["confidence"] == "low" for h in combo), "exploratory combinations capped at low")

    ov = c.get("/api/graph/overview").json()
    ok(ov["ai"]["research_area"] and ov["facts"]["n_papers"] == 7 and ov["facts"]["common_methods"], "graph overview (AI + deterministic facts)")
    ok(c.get("/api/graph/overview").json()["cached"] is True, "overview served from cache the second time")
    eid = next(e["id"] for e in graph["edges"] if e["type"] == "shared_methodology")
    ed = c.get(f"/api/graph/edge/{eid}/detail").json()
    ok(ed["ai"]["connected"] and ed["shared_items"] and ed["display"]["score_meaning"] and ed["evidence"], "edge detail (explanation, shared items, evidence)")
    ok(any(x["page"] for x in ed["evidence"]), "edge evidence carries page numbers")
    nx = c.get(f"/api/papers/{papers[4]['id']}/explanation").json()
    ok(nx["ai"]["about"] and nx["error"] is None, "node explanation")
    sem = next(e for e in graph["edges"] if e["type"] == "semantic_similarity")
    ok("not a percentage" in sem["display"]["score_meaning"], "similarity score explained as non-percentage")
    mt = next(e for e in graph["edges"] if e["type"] == "shared_methodology")
    ok(mt["display"]["numeric"] is False and "common" in mt["display"]["detail"], "shared method shown as actual shared items")

    ok(c.post("/api/mentor/index").json()["indexed_papers"] == 7, "mentor index built for 7 papers")
    r = c.post("/api/mentor/chat", json={"message": "What are the limitations of the hybrid BERT-CNN paper?"}).json()
    ok(r["message"]["sources"] and any(s["cited"] for s in r["message"]["sources"]) and "[S" in r["message"]["content"], "mentor answers with cited sources")
    ok(all(s["page"] for s in r["message"]["sources"]), "mentor sources carry page numbers")
    r2 = c.post("/api/mentor/chat", json={"message": "Why are these connected?", "conversation_id": r["conversation_id"]}).json()
    r3 = c.post("/api/mentor/chat", json={"conversation_id": r["conversation_id"], "regenerate": True}).json()
    conv = c.get(f"/api/mentor/conversations/{r['conversation_id']}").json()
    ok(len(conv["messages"]) == 4 and r3["conversation_id"] == r["conversation_id"], "conversation kept, regenerate replaced last answer")
    fe = c.post(f"/api/gaps/{cur['hypotheses'][0]['id']}/feasibility", json={"compute": "laptop CPU only"}).json()
    ok(fe["analysis"]["complexity"] and fe["manual_validation"], "feasibility analysis with manual-validation notes")
    ok(c.post(f"/api/gaps/{cur['hypotheses'][0]['id']}/feasibility", json={"compute": "laptop CPU only"}).json()["cached"], "feasibility cached")


def persist():
    ok(len(c.get("/api/papers").json()) == 7, "papers persisted after restart")
    ok(len(c.get("/api/graph").json()["edges"]) > 0, "graph persisted after restart")
    gaps = c.get("/api/gaps").json()["hypotheses"]
    ok(any(h["review_status"] == "accepted" for h in gaps), "hypothesis reviews persisted after restart")
    ok(c.get("/api/papers/1/analysis").json()["analysis"]["title"], "analysis persisted after restart")
    ok(len(c.get("/api/mentor/conversations").json()) >= 1, "mentor conversations persisted after restart")
    ok(c.get("/api/gaps").json()["hypotheses"][0]["feasibility"] is not None, "feasibility persisted after restart")


def outage():
    s = c.get("/api/ai/status").json()
    ok(s["llm_ready"] is True and s["routing"]["mentor"] in ("groq", "gemini"), "status reports configured providers + routing")
    r = c.post("/api/papers/1/analyze")
    ok(r.status_code == 202, "analyze accepted (providers are only discovered to be down in the background)")
    for _ in range(40):
        a = c.get("/api/papers/1/analysis").json()
        if a["status"] != "analyzing":
            break
        time.sleep(0.5)
    ok(a["error"] and "temporarily" in a["error"], "analysis failure is a readable 'temporarily unavailable' message")
    r = c.delete("/api/papers/7")
    ok(r.status_code == 200 and len(c.get("/api/graph").json()["nodes"]) == 6, "delete cascades into graph")
    ok(c.get("/api/graph").status_code == 200, "graph still readable while both AI providers are down")
    ov = c.get("/api/graph/overview?refresh=true").json()
    ok(ov["ai"] is None and "temporarily" in ov["error"] and ov["facts"]["n_papers"] == 6, "overview degrades to facts + error when both AI providers are down")
    r = c.post("/api/mentor/chat", json={"message": "hello"})
    ok(r.status_code == 503, "mentor -> readable 503 when both AI providers are down")
    g = c.post("/api/gaps/generate").json()
    ok(g["hypotheses"] and all(h["details_source"] == "template" and h["note"] for h in g["hypotheses"]), "opportunities fall back to evidence-based templates")


{"main": main, "persist": persist, "outage": outage}[sys.argv[1] if len(sys.argv) > 1 else "main"]()

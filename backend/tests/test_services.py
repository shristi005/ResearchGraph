import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config
from app.auth import scoped_db
from app.database import session as dbsession
from app.database.session import Base
from app.main import app
from app.models.ai import Chunk
from app.models.paper import Paper
from app.schemas.extraction import PaperExtraction
from app.services import citation_service as cs
from app.services import graph_explanation_service as explain
from app.services import ai_client, llm_service, relationship_view, research_extraction_service as svc
from app.services import section_service as ss
from app.services.pdf_service import extract_text
from app.services.reprocess import reprocess_missing
from app.services.similarity_service import PaperFeatures, compute_edges, overlap
from app.utils.text import norm
from sample_data.make_pdfs import make_pdf
from sample_data.samples import SAMPLES, analysis_for, paper_text
from tests import pdf_factory

STATUS_OK = {"llm_ready": True, "embedding_ready": True, "message": ""}
AI_DOWN = {**STATUS_OK, "llm_ready": False, "message": "No AI provider configured: set GROQ_API_KEY and/or GEMINI_API_KEY on the backend."}


# ------------------------------------------------------------------ Phase 1: extraction
def doc_of(pdf: bytes):
    c = extract_text(pdf)
    return c, ss.analyze(c.paras)


def test_abstract_without_heading_is_inferred_from_two_column_page():
    c, doc = doc_of(pdf_factory.two_column_no_abstract_heading())
    assert doc.abstract_source == "inferred" and doc.abstract_page == 1
    assert doc.abstract.startswith("Machine learning on medical data")
    assert "Received" not in doc.abstract and "University" not in doc.abstract  # publisher/affiliation text excluded
    assert doc.article_type == "perspective"
    rep = {r["section"]: r for r in doc.report}
    assert rep["abstract"]["method"] == "inferred" and "Inferred" in rep["abstract"]["reason"]
    assert "Not expected" in rep["methodology"]["reason"]  # missing Methods explained, not fabricated


def test_wrapped_title_word_is_not_a_section_heading():
    c, doc = doc_of(pdf_factory.two_column_no_abstract_heading())
    assert "future_work" not in doc.sections or "Testwell" not in doc.sections["future_work"]
    assert any("synthetic" in p.text.lower() for p in c.paras[:3])  # title kept as front matter


def test_future_work_is_only_cue_sentences_not_whole_discussion():
    _, doc = doc_of(pdf_factory.two_column_no_abstract_heading())
    fut = ss.candidates(doc, "future")
    assert fut and all(ss.FUTURE_CUE.search(s.text) for s in fut)
    assert all(s.page == 2 for s in fut)  # page numbers preserved


def test_structured_abstract_and_numbered_sections():
    _, doc = doc_of(pdf_factory.conventional_structured())
    assert doc.abstract_source == "heading" and "Background" in doc.abstract and "Results" in doc.abstract
    assert {"introduction", "methodology", "results", "limitations", "conclusion"} <= set(doc.sections)
    assert doc.article_type == "research article"


def test_limitation_and_future_cues_are_distinct():
    assert ss.classify_sentence("Future work should study X.") == "future"
    assert ss.classify_sentence("The study is limited by small datasets.") == "limitation"
    assert ss.classify_sentence("We trained three classifiers.") is None


def test_locate_returns_page_and_never_matches_invented_text():
    _, doc = doc_of(pdf_factory.conventional_structured())
    hit = ss.locate("The study is limited by the small size of the datasets", doc, "limitations")
    assert hit and hit.page >= 1 and hit.section == "limitations"
    assert ss.locate("Quantum blockchain improves everything dramatically", doc, "findings") is None


def test_enrich_marks_unverified_and_moves_misfiled_items():
    _, doc = doc_of(pdf_factory.conventional_structured())
    a = PaperExtraction.model_validate({"limitations": ["The study is limited by the small size of the datasets", "Invented weakness about GPUs overheating badly"],
                                        "future_work": ["Careful comparison matters for reproducible progress"], "findings": []})
    a = svc.enrich_analysis(a, doc)
    ver = {e.item: e.verified for e in a.evidence}
    assert ver["The study is limited by the small size of the datasets"] and not ver["Invented weakness about GPUs overheating badly"]
    assert any("could not be matched" in w for w in a.warnings)
    assert 0 <= a.extraction_confidence <= 1


def test_grounding_removes_invented_metadata():
    text = paper_text(SAMPLES[1])
    ex = PaperExtraction.model_validate({"title": "Invented Title", "authors": ["Nobody Real", "Jordan Samplewood"], "year": 1999})
    ex = svc.ground(ex, text)
    assert ex.title is None and ex.authors == ["Jordan Samplewood"] and ex.publication_year is None


def test_sample_pdf_roundtrip_has_pages_and_sections():
    c, doc = doc_of(make_pdf(paper_text(SAMPLES[0]), SAMPLES[0]["title"], None))
    assert doc.abstract_source == "heading" and {"limitations", "future_work", "references"} <= set(doc.sections) | {"references"}
    assert all(p.page >= 1 for p in c.paras)


def test_legacy_paper_is_reprocessed_without_losing_analysis(tmp_path, monkeypatch):
    """A v2 database row: no layout, old 'year' key, empty abstract with the old warning."""
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(pdf_factory.two_column_no_abstract_heading())
    old = {"title": None, "authors": [], "year": 2020, "abstract": None, "topics": ["federated learning"],
           "limitations": ["Data from different institutions often follows different distributions"],
           "warnings": ["No abstract section was detected, so the abstract is left empty."]}
    with S() as db:
        db.add(Paper(original_filename="p.pdf", stored_path=str(pdf), file_hash="x", size_bytes=1, raw_text="old text",
                     extraction_json=json.dumps(old), embedding_json="[1]", status="embedded"))
        db.commit()
        assert reprocess_missing(db) == 1
        p = db.query(Paper).one()
        a = PaperExtraction.model_validate(json.loads(p.extraction_json))
    assert p.layout_json and a.abstract.startswith("Machine learning on medical data") and a.abstract_source == "inferred"
    assert a.topics == ["federated learning"] and a.publication_year == 2020  # AI fields untouched
    assert not any("No abstract section was detected" in w for w in a.warnings)
    assert any(e.field == "limitations" and e.page for e in a.evidence)
    assert p.embedding_json is None and p.status == "analyzed"


# ------------------------------------------------------------------ relationships
def test_overlap_and_edges():
    shared, j = overlap(["Neural Networks", "BERT"], ["neural network", "BERT-based classifier", "SVM"])
    assert len(shared) == 2 and 0 < j < 1
    f = lambda i, v, t, m: PaperFeatures(i, f"P{i}", t, m, v)
    papers = [f(1, [1, 0], ["a b", "c d"], ["bert"]), f(2, [1, 0.1], ["a b", "c d"], ["BERT"]), f(3, [0, 1], ["x y"], ["svm"])]
    edges = compute_edges(papers)
    keys = [(e.source, e.target, e.type) for e in edges]
    assert len(keys) == len(set(keys)) and not any(e.type == "citation" for e in edges)
    assert not any(3 in (e.source, e.target) for e in edges)
    assert next(e for e in edges if e.type == "shared_methodology").shared == ["bert"]


def test_relationship_display_is_not_an_unexplained_score():
    d = relationship_view.display("shared_methodology", 0.2, ["Federated Learning"])
    assert d["detail"] == "1 common methodology: Federated Learning" and d["numeric"] is False and "0.2" not in d["detail"]
    s = relationship_view.display("semantic_similarity", 0.82, [])
    assert s["numeric"] and "0.82" in s["short"] and "not a percentage" in s["score_meaning"]
    assert relationship_view.display("citation", 1.0, [])["strength"] == "Verified citation"


def test_citation_needs_explicit_reference_and_confident_match():
    text = "Body mentioning Hybrid BERT-CNN Architecture for Misinformation Detection in prose.\n\nReferences\n[1] J. Example, Something Else Entirely About Cats, 2015.\n"
    assert cs.find_citations(text, [(2, "Hybrid BERT-CNN Architecture for Misinformation Detection")]) == {}
    ref = text + "[2] A. Demo, Hybrid BERT-CNN Architecture for Misinformation Detection, Journal, 2022.\n"
    assert 2 in cs.find_citations(ref, [(2, "Hybrid BERT-CNN Architecture for Misinformation Detection")])


def test_llm_model_coerces_sloppy_output():
    class M(llm_service.LLMModel):
        a: str = ""
        b: list[str] = []
    m = M.model_validate({"a": ["x", "y"], "b": "- one\n- two", "extra": 1})
    assert m.a == "x; y" and m.b == ["one", "two"]


# ------------------------------------------------------------------ API-level (mocked AI layer)
@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr(config, "AUTH_DISABLED", True)

    def override():
        db = Session(info={"user_id": config.LOCAL_USER_ID})
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(dbsession, "SessionLocal", Session)
    app.dependency_overrides[scoped_db] = override
    s = Session(info={"user_id": config.LOCAL_USER_ID})
    for i, smp in enumerate(SAMPLES, 1):
        pdf = tmp_path / f"{i}.pdf"
        pdf.write_bytes(make_pdf(paper_text(smp), smp["title"], None))
        c = extract_text(pdf.read_bytes())
        a = svc.enrich_analysis(PaperExtraction.model_validate(analysis_for(smp)), ss.analyze(c.paras))
        s.add(Paper(original_filename=f"{i}.pdf", stored_path=str(pdf), file_hash=f"h{i}", size_bytes=1,
                    raw_text=c.text, layout_json=c.layout_json, extraction_json=a.model_dump_json(), status="analyzed"))
    s.commit()
    yield TestClient(app), Session
    app.dependency_overrides.clear()


class FakeLLM:
    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr(ai_client, "status", lambda: STATUS_OK)
        monkeypatch.setattr(ai_client, "chat_json", self.chat_json)
        monkeypatch.setattr(ai_client, "chat_text", self.chat_text)
        monkeypatch.setattr(ai_client, "embed_documents", lambda texts: [self.vec(t) for t in texts])
        monkeypatch.setattr(ai_client, "embed_query", lambda t: self.vec(t))
        self.reply = "From your papers: it is discussed [S1]. Also [S99]."

    @staticmethod
    def vec(t):
        v = [0.0] * 16
        for w in norm(t).split():
            v[hash(w) % 16] += 1
        return v

    def chat_json(self, prompt, system, feature="extraction"):
        task = system.split("\n")[0]
        self.calls.append(task)
        return {"about": "A", "research_area": "R", "connected": "C", "title": "T", "complexity": "Medium"}

    def chat_text(self, messages, system, feature="mentor"):
        self.calls.append("mentor")
        return self.reply


def test_node_explanation_is_cached_and_refreshable(env, monkeypatch):
    c, _ = env
    llm = FakeLLM(monkeypatch)
    a = c.get("/api/papers/5/explanation").json()
    b = c.get("/api/papers/5/explanation").json()
    assert a["ai"]["about"] == "A" and not a["cached"] and b["cached"] and llm.calls.count("TASK:node_explain") == 1
    c.get("/api/papers/5/explanation?refresh=true")
    assert llm.calls.count("TASK:node_explain") == 2


def test_overview_and_edge_detail_degrade_without_ai(env, monkeypatch):
    c, _ = env
    def down(prompt, system, feature="extraction"): raise ai_client.AIUnavailable("The free AI quota is temporarily used up")
    monkeypatch.setattr(ai_client, "chat_json", down)
    ov = c.get("/api/graph/overview").json()
    assert ov["ai"] is None and "temporarily" in ov["error"] and ov["facts"]["n_papers"] == 7
    assert c.get("/api/graph/overview?paper_ids=1,2").json()["facts"]["n_papers"] == 2  # selected papers only


def test_edge_detail_has_evidence_pages_and_shared_items(env, monkeypatch):
    c, Session = env
    FakeLLM(monkeypatch)
    monkeypatch.setattr("app.config.SIM_THRESHOLD", 0.0)
    assert c.post("/api/graph/generate").status_code == 200
    g = c.get("/api/graph").json()
    e = next(x for x in g["edges"] if x["type"] == "shared_methodology")
    d = c.get(f"/api/graph/edge/{e['id']}/detail").json()
    assert d["shared_items"] and d["evidence"] and all(x["page"] for x in d["evidence"] if x["section"] != "references")
    assert "common" in d["display"]["detail"]
    cit = next(x for x in g["edges"] if x["type"] == "citation")
    cd = c.get(f"/api/graph/edge/{cit['id']}/detail").json()
    assert cd["display"]["strength"] == "Verified citation" and any(x["term"] == "reference entry" for x in cd["evidence"])


def test_opportunities_use_only_verified_evidence_and_review_persists(env, monkeypatch):
    c, Session = env
    monkeypatch.setattr(ai_client, "status", lambda: AI_DOWN)
    s = Session()
    p = s.get(Paper, 1)
    a = PaperExtraction.model_validate(json.loads(p.extraction_json))
    a.limitations.append("Fabricated limitation about unicorn datasets and cheese")
    a.evidence.append(a.evidence[0].model_copy(update={"field": "limitations", "item": a.limitations[-1], "quote": None, "page": None, "verified": False}))
    p.extraction_json = a.model_dump_json(); s.commit()
    g = c.post("/api/gaps/generate").json()
    assert g["hypotheses"] and not g["enriching"]
    blob = json.dumps(g)
    assert "unicorn" not in blob  # unverified statements never become evidence
    for h in g["hypotheses"]:
        assert h["evidence"] and all(e["quote"] and e["paper_id"] for e in h["evidence"])
        assert h["confidence"] in ("low", "medium") and h["uncertainties"] and h["confidence_reasons"]
        assert h["details_source"] == "template" and h["note"]
        if len(h["supporting_paper_ids"]) == 1 or h["category"] == "combination":
            assert h["confidence"] == "low"
    # quotes really come from the PDFs
    docs = {p.id: ss.analyze(extract_text(Path(p.stored_path).read_bytes()).paras) for p in s.query(Paper)}
    for h in g["hypotheses"]:
        for e in h["evidence"]:
            assert any(norm(e["quote"]) == norm(sn.text) for sn in docs[e["paper_id"]].sentences)
    hid = g["hypotheses"][0]["id"]
    assert c.patch(f"/api/gaps/{hid}", json={"review_status": "needs_investigation"}).json()["review_status"] == "needs_investigation"
    assert c.get("/api/gaps").json()["hypotheses"][0]["review_status"] == "needs_investigation"
    assert c.patch(f"/api/gaps/{hid}", json={"review_status": "proven"}).status_code == 422


def test_legacy_opportunity_rows_still_load(env):
    c, Session = env
    from app.models.hypothesis import Hypothesis
    s = Session()
    s.add(Hypothesis(key="old", kind="repeated_limitation", hypothesis="Old statement", supporting_paper_ids="[1]",
                     evidence=json.dumps([{"paper_id": 1, "paper_title": "T", "section": "limitations", "text": "old quote"}]),
                     reasoning="r", uncertainties="[]", validation_steps="[]", confidence="low", review_status="accepted"))
    s.commit()
    h = c.get("/api/gaps").json()["hypotheses"][0]
    assert h["legacy"] and h["category"] == "limitation" and h["review_status"] == "accepted" and h["evidence"][0]["quote"] == "old quote"


def test_feasibility_notes_manual_validation_and_caches(env, monkeypatch):
    c, _ = env
    llm = FakeLLM(monkeypatch)
    monkeypatch.setattr(ai_client, "status", lambda: AI_DOWN)
    hid = c.post("/api/gaps/generate").json()["hypotheses"][0]["id"]
    r = c.post(f"/api/gaps/{hid}/feasibility", json={"compute": "CPU only"}).json()
    assert r["analysis"]["complexity"] == "Medium" and "NOT checked" in r["manual_validation"][0] and not r["cached"]
    assert c.post(f"/api/gaps/{hid}/feasibility", json={"compute": "CPU only"}).json()["cached"]
    assert not c.post(f"/api/gaps/{hid}/feasibility", json={"compute": "GPU"}).json()["cached"]  # different context


def test_mentor_rag_citations_history_and_regenerate(env, monkeypatch):
    c, Session = env
    llm = FakeLLM(monkeypatch)
    r = c.post("/api/mentor/chat", json={"message": "What are the limitations of the survey?", "paper_ids": [1, 2]}).json()
    msg = r["message"]
    assert msg["sources"] and {s["paper_id"] for s in msg["sources"]} <= {1, 2}      # only selected papers retrieved
    assert any(s["cited"] for s in msg["sources"]) and "[S99]" not in msg["content"]  # invalid tag stripped
    assert any("S99" in w for w in msg["warnings"])
    assert all(s["page"] for s in msg["sources"])
    llm.reply = "My inference: do something."
    r2 = c.post("/api/mentor/chat", json={"message": "Ideas?", "conversation_id": r["conversation_id"]}).json()
    assert any("cites no passages" in w for w in r2["message"]["warnings"])
    r3 = c.post("/api/mentor/chat", json={"conversation_id": r["conversation_id"], "regenerate": True}).json()
    conv = c.get(f"/api/mentor/conversations/{r['conversation_id']}").json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant", "user", "assistant"]
    assert llm.calls.count("mentor") == 3 and conv["messages"][-1]["content"] == r3["message"]["content"]  # regenerated, not duplicated
    s = Session()
    assert s.query(Chunk).count() > 0  # chunks are built once and reused
    n = s.query(Chunk).count()
    c.post("/api/mentor/chat", json={"message": "again", "conversation_id": r["conversation_id"]})
    assert Session().query(Chunk).count() == n
    assert c.post("/api/mentor/chat", json={"message": "x", "conversation_id": 999}).status_code == 404
    assert c.post("/api/mentor/chat", json={"message": "  "}).status_code == 400
    assert len(c.get("/api/mentor/suggestions").json()["suggestions"]) == 9


def test_mentor_without_analyzed_papers_and_with_ai_down(env, monkeypatch):
    c, Session = env
    FakeLLM(monkeypatch)
    def down(texts): raise ai_client.AIUnavailable("The free AI quota is temporarily used up")
    monkeypatch.setattr(ai_client, "embed_documents", down)
    assert c.post("/api/mentor/chat", json={"message": "hi"}).status_code == 503
    s = Session()
    for p in s.query(Paper): p.extraction_json = None
    s.commit()
    assert c.post("/api/mentor/chat", json={"message": "hi"}).status_code == 400


def test_analyze_background_flow_and_failure_keeps_old_result(env, monkeypatch):
    c, _ = env
    monkeypatch.setattr(ai_client, "status", lambda: STATUS_OK)
    monkeypatch.setattr(ai_client, "chat_json", lambda p, s, f="extraction": analysis_for(SAMPLES[0]))
    assert c.post("/api/papers/1/analyze").status_code == 202
    body = c.get("/api/papers/1/analysis").json()
    a = body["analysis"]
    assert body["status"] == "analyzed" and a["publication_year"] == 2021 and a["abstract_source"] == "heading"
    assert a["section_report"] and a["evidence"] and a["article_type"]
    def boom(p, s, f="extraction"): raise ValueError("bad json")
    monkeypatch.setattr(ai_client, "chat_json", boom)
    c.post("/api/papers/1/analyze")
    body = c.get("/api/papers/1/analysis").json()
    assert body["analysis"]["title"] and "not valid" in body["error"] and body["status"] == "analyzed"


def test_no_ai_provider_configured_gives_readable_503(env, monkeypatch):
    c, _ = env
    monkeypatch.setattr(ai_client, "status", lambda: AI_DOWN)
    r = c.post("/api/papers/1/analyze")
    assert r.status_code == 503 and "GROQ_API_KEY" in r.json()["detail"]


def test_graph_embed_failure_is_503(env, monkeypatch):
    c, _ = env
    def down(texts): raise ai_client.AIUnavailable("The embedding service is temporarily unavailable.")
    monkeypatch.setattr(ai_client, "embed_documents", down)
    r = c.post("/api/graph/generate")
    assert r.status_code == 503 and "temporarily" in r.json()["detail"]


def test_reprocess_endpoint_and_paper_delete_cleans_chunks(env, monkeypatch):
    c, Session = env
    FakeLLM(monkeypatch)
    c.post("/api/mentor/index")
    assert Session().query(Chunk).filter(Chunk.paper_id == 1).count() > 0
    assert c.post("/api/papers/1/reprocess").status_code == 200
    assert Session().query(Chunk).filter(Chunk.paper_id == 1).count() == 0  # stale chunks dropped
    c.post("/api/mentor/index")
    assert c.delete("/api/papers/1").status_code == 200
    assert Session().query(Chunk).filter(Chunk.paper_id == 1).count() == 0

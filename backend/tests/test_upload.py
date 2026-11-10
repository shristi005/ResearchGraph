import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import config
from app.auth import scoped_db
from app.database.session import Base
from app.main import app
from app.services import storage_service


def make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 780), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


LONG_TEXT = ("Attention based models for document classification. " * 20)


@pytest.fixture()
def client(tmp_path, monkeypatch):
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

    monkeypatch.setattr(storage_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(config, "STORAGE_BACKEND", "local")
    app.dependency_overrides[scoped_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def up(client, files):
    return client.post("/api/papers/upload", files=[("files", f) for f in files])


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_upload_valid_and_preserved(client, tmp_path):
    pdf = make_pdf(LONG_TEXT)
    r = up(client, [("a.pdf", pdf, "application/pdf")])
    res = r.json()["results"][0]
    assert res["outcome"] == "created"
    assert res["paper"]["page_count"] == 1
    assert len(list(tmp_path.rglob("*.pdf"))) == 1  # original preserved


def test_duplicate_detected(client):
    pdf = make_pdf(LONG_TEXT)
    up(client, [("a.pdf", pdf, "application/pdf")])
    res = up(client, [("copy.pdf", pdf, "application/pdf")]).json()["results"][0]
    assert res["outcome"] == "duplicate"
    assert len(client.get("/api/papers").json()) == 1


def test_rejects_bad_files(client):
    res = up(client, [
        ("notes.txt", b"hello", "text/plain"),
        ("fake.pdf", b"this is not a pdf at all", "application/pdf"),
        ("empty.pdf", b"", "application/pdf"),
        ("scan.pdf", make_pdf("hi"), "application/pdf"),
    ]).json()["results"]
    assert [x["outcome"] for x in res] == ["rejected"] * 4
    assert "scanned" in res[3]["message"].lower()
    assert client.get("/api/papers").json() == []


def test_multiple_mixed_upload(client):
    res = up(client, [
        ("one.pdf", make_pdf(LONG_TEXT), "application/pdf"),
        ("two.pdf", make_pdf(LONG_TEXT + " variant two"), "application/pdf"),
        ("bad.txt", b"x", "text/plain"),
    ]).json()["results"]
    assert [x["outcome"] for x in res] == ["created", "created", "rejected"]


def test_get_and_delete(client):
    pid = up(client, [("a.pdf", make_pdf(LONG_TEXT), "application/pdf")]).json()["results"][0]["paper"]["id"]
    d = client.get(f"/api/papers/{pid}").json()
    assert d["text_length"] > 200 and "Attention" in d["text_preview"]
    assert client.delete(f"/api/papers/{pid}").status_code == 200
    assert client.get(f"/api/papers/{pid}").status_code == 404

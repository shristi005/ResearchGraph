"""Two-user isolation at the ORM layer (needs the backend dependencies: `pip install -r requirements.txt`).
NOT RUN in the authoring sandbox (SQLAlchemy was not installable there) - run it before deploying: `pytest tests/test_isolation.py`."""
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database.session import Base
from app.models.ai import Chunk, Conversation
from app.models.paper import Paper
from app.services import chunk_service
from app.ai import embeddings

A, B = "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


@pytest.fixture()
def engine(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path/'iso.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    return e


def paper(h):
    return Paper(original_filename=f"{h}.pdf", stored_path="x", file_hash=h, size_bytes=1, raw_text="t")


def test_rows_are_stamped_and_invisible_to_other_users(engine):
    with Session(engine, info={"user_id": A}) as a:
        a.add(paper("same-hash")); a.add(Conversation(title="mine")); a.commit()
        pid = a.scalar(select(Paper.id))
        assert a.scalar(select(Paper.user_id)) == A
    with Session(engine, info={"user_id": B}) as b:
        assert b.scalars(select(Paper)).all() == []
        assert b.get(Paper, pid) is None                      # direct id access is filtered too
        assert b.scalars(select(Conversation)).all() == []
        b.add(paper("same-hash")); b.commit()                 # same PDF for another user is allowed (unique per user)
        assert b.query(Paper).count() == 1


def test_other_user_cannot_delete_or_update(engine):
    with Session(engine, info={"user_id": A}) as a:
        a.add(paper("h1")); a.commit(); pid = a.scalar(select(Paper.id))
    with Session(engine, info={"user_id": B}) as b:
        assert b.query(Paper).filter(Paper.id == pid).delete() == 0
        b.commit()
    with Session(engine, info={"user_id": A}) as a:
        assert a.get(Paper, pid) is not None


def test_cannot_write_row_owned_by_someone_else(engine):
    with Session(engine, info={"user_id": A}) as a:
        p = paper("h2"); p.user_id = B; a.add(p)
        with pytest.raises(PermissionError):
            a.commit()


def test_mentor_retrieval_never_crosses_users_or_unselected_papers(engine, monkeypatch):
    monkeypatch.setattr("app.config.EMBED_PROVIDER", "hash")
    monkeypatch.setattr(chunk_service, "IS_POSTGRES", False)
    model = embeddings.model_id()
    vec = lambda t: embeddings.embed_documents([t])[0]
    with Session(engine, info={"user_id": A}) as a:
        pa1, pa2 = paper("a1"), paper("a2"); a.add_all([pa1, pa2]); a.commit()
        for p, txt in ((pa1, "crop disease detection using drones"), (pa2, "music mixing with artificial intelligence")):
            a.add(Chunk(paper_id=p.id, idx=0, page=1, section="abstract", text=txt, embed_model=model, embedding_json=json.dumps(vec(txt))))
        a.commit(); ids = [pa1.id, pa2.id]
    with Session(engine, info={"user_id": B}) as b:
        b.add(paper("b1")); b.commit(); pb = b.scalar(select(Paper.id))
        txt = "crop disease detection using drones"
        b.add(Chunk(paper_id=pb, idx=0, page=1, section="abstract", text=txt, embed_model=model, embedding_json=json.dumps(vec(txt)))); b.commit()
        assert chunk_service.retrieve(b, "crop disease drones", ids, 6) == []          # A's papers: invisible to B
        assert {c.paper_id for c in chunk_service.retrieve(b, "crop disease drones", [pb], 6)} == {pb}
    with Session(engine, info={"user_id": A}) as a:
        got = chunk_service.retrieve(a, "crop disease drones", [ids[0]], 6)             # only the selected paper
        assert {c.paper_id for c in got} == {ids[0]}


def test_embedding_model_mismatch_is_not_searched(engine, monkeypatch):
    monkeypatch.setattr("app.config.EMBED_PROVIDER", "hash")
    with Session(engine, info={"user_id": A}) as a:
        p = paper("m1"); a.add(p); a.commit()
        a.add(Chunk(paper_id=p.id, idx=0, page=1, section="abstract", text="old model chunk",
                    embed_model="local:other-model:768", embedding_json=json.dumps([0.1] * 768))); a.commit()
        assert chunk_service.retrieve(a, "anything", [p.id], 6) == []

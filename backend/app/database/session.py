from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker, with_loader_criteria
from sqlalchemy import String

from app.config import DATABASE_URL, DATA_DIR, IS_POSTGRES, UPLOAD_DIR


class Base(DeclarativeBase):
    pass


class OwnedMixin:
    """Every user-owned table carries the Supabase auth user id (auth.users.id, a UUID as text)."""
    user_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)


DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)  # local dev / temp processing only; production PDFs live in Supabase Storage

if IS_POSTGRES:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=1800)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---- Automatic per-user scoping -------------------------------------------------------------------------------
# A session opened with open_session(user_id) transparently (a) adds `user_id = :uid` to every SELECT/UPDATE/DELETE on
# an owned table and (b) stamps user_id on new rows. Route code therefore cannot read another user's rows by accident.
# This is application-level isolation; Row Level Security in the SQL migration is the second, database-level layer.
@event.listens_for(Session, "do_orm_execute")
def _scope_to_user(state):
    uid = state.session.info.get("user_id")
    if uid is None or state.is_column_load or state.is_relationship_load:
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(OwnedMixin, lambda cls: cls.user_id == uid, include_aliases=True))


@event.listens_for(Session, "before_flush")
def _stamp_owner(session, flush_context, instances):
    uid = session.info.get("user_id")
    if uid is None:
        return
    for obj in session.new:
        if isinstance(obj, OwnedMixin):
            if obj.user_id is None:
                obj.user_id = uid
            elif obj.user_id != uid:
                raise PermissionError("Refusing to write a row owned by another user.")


def open_session(user_id: str | None = None) -> Session:
    """user_id=None gives an UNSCOPED session - only for startup maintenance, never for request handling."""
    return SessionLocal(info={"user_id": user_id} if user_id else {})


def session_factory_for(user_id: str):
    """Callable for background tasks (they open their own session; it must stay scoped to the same user)."""
    return lambda: open_session(user_id)


def init_db() -> None:
    from app.models import ai, hypothesis, paper, relationship  # noqa: F401

    if IS_POSTGRES:
        # Postgres schema is owned by supabase/migrations/*.sql (tables, pgvector, RLS). Nothing is created or altered here.
        return
    Base.metadata.create_all(bind=engine)
    # Additive-only migration for old local SQLite files (nullable columns, nothing is dropped).
    insp = inspect(engine)
    adds = {
        "papers": [("pdf_title", "VARCHAR(512)"), ("pdf_author", "VARCHAR(512)"), ("layout_json", "TEXT"), ("user_id", "VARCHAR(36)")],
        "relationships": [("shared_json", "TEXT"), ("user_id", "VARCHAR(36)")],
        "hypotheses": [("details_json", "TEXT"), ("feasibility_json", "TEXT"), ("enrichment_status", "VARCHAR(16)"), ("user_id", "VARCHAR(36)")],
        "chunks": [("user_id", "VARCHAR(36)"), ("embed_model", "VARCHAR(80)")],
        "conversations": [("user_id", "VARCHAR(36)")],
        "messages": [("user_id", "VARCHAR(36)")],
    }
    with engine.begin() as conn:
        for table, cols in adds.items():
            have = {c["name"] for c in insp.get_columns(table)}
            for name, typ in cols:
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {typ}"))
        conn.execute(text(
            "UPDATE papers SET status = CASE WHEN extraction_json IS NOT NULL "
            "THEN 'analyzed' ELSE 'uploaded' END WHERE status = 'analyzing'"
        ))
        conn.execute(text("UPDATE hypotheses SET enrichment_status = 'template' WHERE enrichment_status = 'pending'"))

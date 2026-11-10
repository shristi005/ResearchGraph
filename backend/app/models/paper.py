from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base, OwnedMixin


class Paper(OwnedMixin, Base):
    __tablename__ = "papers"
    __table_args__ = (UniqueConstraint("user_id", "file_hash", name="uq_paper_user_hash"),)  # same PDF may exist for different users

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))  # local path (dev) or Supabase Storage object key "<user_id>/<hash>.pdf"
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    # uploaded -> analyzing -> analyzed -> embedded ; or failed
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_title: Mapped[str | None] = mapped_column(String(512), nullable=True)   # embedded PDF metadata, if any
    pdf_author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Layout-aware paragraphs with page numbers: [[page, text, bold, size, y_fraction], ...]
    layout_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

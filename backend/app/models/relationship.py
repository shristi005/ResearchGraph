from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base, OwnedMixin


class Relationship(OwnedMixin, Base):
    __tablename__ = "relationships"
    # One edge per (pair, type): this is what guarantees no duplicate edges.
    __table_args__ = (UniqueConstraint("source_id", "target_id", "type", name="uq_edge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(32))
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text)
    shared_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # the actual shared topics/methods (v3)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

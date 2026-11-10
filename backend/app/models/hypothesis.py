from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base, OwnedMixin


class Hypothesis(OwnedMixin, Base):
    """A research opportunity. (Table name kept from v1 so existing reviews survive.)"""
    __tablename__ = "hypotheses"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_hyp_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), index=True)  # stable id so reviews survive regeneration
    kind: Mapped[str] = mapped_column(String(40))          # category
    hypothesis: Mapped[str] = mapped_column(Text)          # one-sentence statement
    supporting_paper_ids: Mapped[str] = mapped_column(Text)  # JSON list
    evidence: Mapped[str] = mapped_column(Text)              # JSON list (quote, page, section...)
    reasoning: Mapped[str] = mapped_column(Text)
    uncertainties: Mapped[str] = mapped_column(Text)         # JSON list
    validation_steps: Mapped[str] = mapped_column(Text)      # JSON list
    confidence: Mapped[str] = mapped_column(String(16), default="low")
    review_status: Mapped[str] = mapped_column(String(32), default="new")
    # added in v3 (nullable so old rows still load):
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)       # title, problem, question, methodology...
    feasibility_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # pending|done|template|failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

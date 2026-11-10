from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    size_bytes: int
    page_count: int
    status: str
    error: str | None = None
    title: str
    title_source: str  # analysis | pdf_metadata | filename
    pdf_title: str | None = None
    pdf_author: str | None = None
    publication_year: int | None = None
    topics: list[str] = []
    has_extraction: bool = False
    has_embedding: bool = False
    created_at: datetime


class PaperDetail(PaperOut):
    text_preview: str = ""
    text_length: int = 0


class PaperText(BaseModel):
    paper_id: int
    text: str


class UploadResult(BaseModel):
    filename: str
    outcome: str  # "created" | "duplicate" | "rejected"
    message: str
    paper: PaperOut | None = None


class UploadResponse(BaseModel):
    results: list[UploadResult]

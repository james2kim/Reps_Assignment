from pydantic import BaseModel

from backend.app.models.enums import QueryIntent, RetrievalStrategy


class SearchRequest(BaseModel):
    company_id: str
    user_id: str
    query: str


class Citation(BaseModel):
    source_file: str  # e.g. "amproxin_guide.pdf"
    source_type: str  # "pdf", "video", "audio", "image", "text", "submission", "feedback"
    label: str  # e.g. "[PDF: amproxin_guide.pdf, Page 1]"
    asset_id: str | None = None  # for precise chunk-to-citation matching
    page: int | None = None
    start: str | None = None  # timestamp
    end: str | None = None
    section: str | None = None


class ThoughtTrace(BaseModel):
    intent: QueryIntent
    strategy: RetrievalStrategy
    confidence: float
    reason: str
    chunks_retrieved: int
    structured_data: bool


class SearchResponse(BaseModel):
    answer: str
    citations: list[Citation]
    disclaimer: str | None = None
    thought_trace: ThoughtTrace

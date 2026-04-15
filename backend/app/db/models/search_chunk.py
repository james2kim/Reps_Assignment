from sqlalchemy import Column, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB

from backend.app.db.base import Base


class SearchChunk(Base):
    __tablename__ = "search_chunks"

    id = Column(String, primary_key=True)
    content = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # asset | submission | feedback
    source_id = Column(String, nullable=False)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=True, index=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

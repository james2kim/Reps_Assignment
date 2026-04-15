from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Rep(Base):
    __tablename__ = "reps"

    id = Column(String, primary_key=True)
    prompt_text = Column(String, nullable=False)
    prompt_title = Column(String, nullable=False)
    prompt_type = Column(String, nullable=False)  # watch | practice
    play_id = Column(String, ForeignKey("plays.id"), nullable=False, index=True)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    asset_id = Column(String, ForeignKey("assets.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)

    play = relationship("Play", back_populates="reps")
    asset = relationship("Asset")

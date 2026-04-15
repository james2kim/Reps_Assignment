from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(String, primary_key=True)
    submission_id = Column(
        String, ForeignKey("submissions.id"), nullable=False, index=True
    )
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    score = Column(Integer, nullable=False)
    text = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False)

    submission = relationship("Submission")

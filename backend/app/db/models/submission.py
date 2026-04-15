from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    rep_id = Column(String, ForeignKey("reps.id"), nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    submission_type = Column(String, nullable=False)  # video | audio | text
    asset_id = Column(String, ForeignKey("assets.id"), nullable=False, index=True)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)

    user = relationship("User")
    rep = relationship("Rep")
    asset = relationship("Asset")

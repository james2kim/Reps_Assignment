from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class PlayAssignment(Base):
    __tablename__ = "play_assignments"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    play_id = Column(String, ForeignKey("plays.id"), nullable=False, index=True)
    assigned_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, default="assigned")
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User")
    play = relationship("Play")

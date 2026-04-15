from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    segment = Column(String, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    company = relationship("Company", back_populates="users")

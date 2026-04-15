from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Asset(Base):
    __tablename__ = "assets"

    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)

    company = relationship("Company")

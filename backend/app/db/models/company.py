from sqlalchemy import Column, String
from sqlalchemy.orm import relationship

from backend.app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False, default="")

    users = relationship("User", back_populates="company")
    plays = relationship("Play", back_populates="company")

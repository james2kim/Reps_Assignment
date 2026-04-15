from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.config import settings

engine = create_engine(settings.database_url, echo=settings.sql_echo)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

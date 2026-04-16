from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.schemas.company import CompanyResponse
from backend.app.db.session import get_db

router = APIRouter()


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT id, name, description FROM companies ORDER BY name")
    ).all()
    return [CompanyResponse(id=r[0], name=r[1], description=r[2]) for r in rows]

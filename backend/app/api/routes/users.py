from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.schemas.user import UserResponse
from backend.app.db.session import get_db

router = APIRouter()


@router.get("/companies/{company_id}/users", response_model=list[UserResponse])
def list_users(company_id: str, db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            "SELECT id, username, display_name, role, segment "
            "FROM users WHERE company_id = :cid AND is_active = true "
            "ORDER BY display_name"
        ),
        {"cid": company_id},
    ).all()
    return [
        UserResponse(id=r[0], username=r[1], display_name=r[2], role=r[3], segment=r[4])
        for r in rows
    ]

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    segment: str

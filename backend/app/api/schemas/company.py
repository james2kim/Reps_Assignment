from pydantic import BaseModel


class CompanyResponse(BaseModel):
    id: str
    name: str
    description: str

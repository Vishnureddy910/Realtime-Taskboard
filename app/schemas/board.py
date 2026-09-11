from pydantic import BaseModel
from typing import Optional

class BoardCreate(BaseModel):
    name: str
    description: Optional[str] = None

class BoardOut(BoardCreate):
    id: int
    
    class Config:
        from_attributes = True
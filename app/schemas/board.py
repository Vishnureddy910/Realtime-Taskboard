from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

class BoardCreate(BaseModel):
    name: str
    description: Optional[str] = None

class BoardOut(BoardCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

class BoardSummaryOut(BoardOut):
    """A board as seen by one member: includes that member's role."""
    role: str
    member_count: int

class BoardMemberCreate(BaseModel):
    username: str
    role: Literal["editor", "viewer"] = "editor"

class BoardMemberUpdate(BaseModel):
    role: Literal["editor", "viewer"]

class BoardMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    username: str
    role: str

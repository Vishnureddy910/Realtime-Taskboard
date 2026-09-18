from typing import List

from pydantic import BaseModel, ConfigDict, EmailStr

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str

class UserSearchOut(BaseModel):
    """Public view of a user: never exposes email to other users."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    # Names of boards both the searcher and this user belong to
    shared_boards: List[str] = []

class Token(BaseModel):
    access_token: str
    token_type: str

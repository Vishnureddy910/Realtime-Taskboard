from pydantic import BaseModel
from typing import Optional

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    list_id: int

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    list_id: Optional[int] = None
    expected_version: int  # <-- ADD THIS: The version the client thinks they are editing

class TaskOut(TaskCreate):
    id: int
    version: int
    
    class Config:
        from_attributes = True
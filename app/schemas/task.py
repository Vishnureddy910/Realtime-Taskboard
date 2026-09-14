from pydantic import BaseModel
from typing import Optional

# NEW: A small schema just to safely send the username
class TaskUserOut(BaseModel):
    username: str
    class Config:
        from_attributes = True

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    list_id: int

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    list_id: Optional[int] = None
    expected_version: int 

class TaskOut(TaskBase):
    id: int
    version: int
    
    # --- NEW CODE: Include the creator data in the output ---
    creator_id: Optional[int] = None
    creator: Optional[TaskUserOut] = None

    class Config:
        from_attributes = True
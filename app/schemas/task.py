from pydantic import BaseModel, ConfigDict
from typing import Optional

# A small schema just to safely send the username
class TaskUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str

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
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    creator_id: Optional[int] = None
    creator: Optional[TaskUserOut] = None

from pydantic import BaseModel, ConfigDict

class ListCreate(BaseModel):
    name: str
    board_id: int

class ListOut(ListCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int

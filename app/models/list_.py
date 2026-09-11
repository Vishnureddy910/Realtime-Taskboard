from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.base import Base

class List(Base):
    __tablename__ = "lists"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False) # e.g., To Do, In Progress, Done
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
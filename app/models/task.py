from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.base import Base

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    list_id = Column(Integer, ForeignKey("lists.id"), nullable=False)
    
    # Crucial for Phase 6 (Optimistic Concurrency)
    version = Column(Integer, default=1, nullable=False)
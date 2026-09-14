from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base import Base # Or wherever your Base is imported from

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String, nullable=True)
    list_id = Column(Integer, ForeignKey("lists.id"))
    version = Column(Integer, default=1)
    
    # --- NEW CODE: Link the task to the user ---
    creator_id = Column(Integer, ForeignKey("users.id"))
    creator = relationship("User")
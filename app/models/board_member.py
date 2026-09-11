from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.base import Base

class BoardMember(Base):
    __tablename__ = "board_members"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    board_id = Column(Integer, ForeignKey("boards.id"), nullable=False)
    role = Column(String, nullable=False, default="viewer") # owner, editor, viewer
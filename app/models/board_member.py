from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from app.db.base import Base

class BoardMember(Base):
    __tablename__ = "board_members"
    __table_args__ = (
        # One membership per user per board; also serves as the index for access checks
        UniqueConstraint("board_id", "user_id", name="uq_board_members_board_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    board_id = Column(Integer, ForeignKey("boards.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False, default="viewer") # owner, editor, viewer

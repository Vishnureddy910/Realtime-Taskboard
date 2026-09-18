from sqlalchemy import Column, Index, String, Integer, func
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    __table_args__ = (
        # Serves case-insensitive prefix search: lower(username) LIKE 'abc%'.
        # text_pattern_ops makes LIKE usable as an index range scan regardless of collation.
        Index(
            "ix_users_username_lower_prefix",
            func.lower(username),
            postgresql_ops={"lower_1": "text_pattern_ops"},
        ),
    )

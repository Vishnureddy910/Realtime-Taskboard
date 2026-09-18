from typing import List as TypingList, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import authorize_board, get_current_user
from app.core.rate_limit import user_search_rate_limit
from app.db.session import get_db
from app.models.board_member import BoardMember
from app.models.user import User
from app.schemas.user import UserSearchOut

router = APIRouter()

SEARCH_RESULT_LIMIT = 8


def _escape_like(value: str) -> str:
    # Without this, a query of "%" or "_" would act as a wildcard and match every user
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search", response_model=TypingList[UserSearchOut], dependencies=[Depends(user_search_rate_limit)])
def search_users(
    q: str = Query(..., min_length=2, max_length=50, description="Username prefix, case-insensitive"),
    board_id: Optional[int] = Query(None, description="Exclude users who are already members of this board"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Username autocomplete for inviting people to a board.

    Limits exposure of the user directory: prefix match only, at least 2 characters,
    a small result cap, usernames only (never emails) and a per-user rate limit.
    """
    query = db.query(User).filter(
        func.lower(User.username).like(f"{_escape_like(q.strip().lower())}%", escape="\\"),
        User.id != current_user.id,
    )

    if board_id is not None:
        # Only the owner can invite, so only the owner gets board-scoped suggestions
        authorize_board(db, board_id, current_user, min_role="owner")
        existing_member = (
            db.query(BoardMember.id)
            .filter(BoardMember.board_id == board_id, BoardMember.user_id == User.id)
            .exists()
        )
        query = query.filter(~existing_member)

    return query.order_by(User.username).limit(SEARCH_RESULT_LIMIT).all()

from typing import List as TypingList, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session, aliased

from app.core.deps import authorize_board, get_current_user
from app.core.rate_limit import user_search_rate_limit
from app.db.session import get_db
from app.models.board import Board
from app.models.board_member import BoardMember
from app.models.user import User
from app.schemas.user import UserSearchOut

router = APIRouter()

SEARCH_RESULT_LIMIT = 8


def _escape_like(value: str) -> str:
    # Without this, a query of "%" or "_" would act as a wildcard and match every user
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _shared_boards_subquery(db: Session, user_id: int):
    """
    For every other user, the boards they share with `user_id` (a self-join on memberships).

    Only boards the searcher is a member of can appear, so this never reveals
    anything about boards the searcher can't already see.
    """
    mine = aliased(BoardMember)
    theirs = aliased(BoardMember)
    return (
        db.query(
            theirs.user_id.label("user_id"),
            func.count().label("shared_count"),
            func.array_agg(aggregate_order_by(Board.name, Board.name)).label("shared_boards"),
        )
        .select_from(mine)
        .join(theirs, (theirs.board_id == mine.board_id) & (theirs.user_id != mine.user_id))
        .join(Board, Board.id == mine.board_id)
        .filter(mine.user_id == user_id)
        .group_by(theirs.user_id)
        .subquery()
    )


@router.get("/search", response_model=TypingList[UserSearchOut], dependencies=[Depends(user_search_rate_limit)])
def search_users(
    q: str = Query(..., min_length=1, max_length=50, description="Username prefix, case-insensitive"),
    board_id: Optional[int] = Query(None, description="Exclude users who are already members of this board"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Username autocomplete for inviting people to a board.

    People you already collaborate with rank first, annotated with the boards you share.
    Exposure of the user directory is limited: prefix match only, a small result cap,
    usernames only (never emails) and a per-user rate limit.
    """
    shared = _shared_boards_subquery(db, current_user.id)
    shared_count = func.coalesce(shared.c.shared_count, 0)

    query = (
        db.query(User.id, User.username, shared.c.shared_boards)
        .outerjoin(shared, shared.c.user_id == User.id)
        .filter(
            func.lower(User.username).like(f"{_escape_like(q.strip().lower())}%", escape="\\"),
            User.id != current_user.id,
        )
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

    rows = query.order_by(shared_count.desc(), User.username).limit(SEARCH_RESULT_LIMIT).all()
    return [UserSearchOut(id=row.id, username=row.username, shared_boards=row.shared_boards or []) for row in rows]

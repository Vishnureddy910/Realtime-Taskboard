import json
from typing import List as TypingList

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from app.core.deps import authorize_board, get_current_user, get_membership
from app.db.session import get_db
from app.models.board import Board
from app.models.board_member import BoardMember
from app.models.list_ import List as DBList
from app.models.task import Task
from app.models.user import User
from app.schemas.board import BoardCreate, BoardMemberCreate, BoardMemberOut, BoardMemberUpdate, BoardOut, BoardSummaryOut
from app.schemas.list_ import ListOut
from app.schemas.task import TaskOut
from app.services.broadcast_service import publish_event, redis_client

router = APIRouter()

DEFAULT_LISTS = ["To Do", "In Progress", "Done"]
BOARD_CACHE_TTL_SECONDS = 60


# ==========================================
# BOARDS
# ==========================================
@router.get("/", response_model=TypingList[BoardSummaryOut])
def get_boards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The boards you belong to, each with your role on it and its member count."""
    member_count = (
        select(func.count())
        .where(BoardMember.board_id == Board.id)
        .correlate(Board)
        .scalar_subquery()
    )
    rows = (
        db.query(Board, BoardMember.role, member_count)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .filter(BoardMember.user_id == current_user.id)
        .order_by(Board.id)
        .all()
    )
    return [
        BoardSummaryOut(id=board.id, name=board.name, description=board.description, role=role, member_count=count)
        for board, role, count in rows
    ]

@router.post("/", response_model=BoardOut)
def create_board(board: BoardCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # One transaction: a board never exists without its owner or default lists
    db_board = Board(**board.model_dump())
    db.add(db_board)
    db.flush()

    db.add(BoardMember(user_id=current_user.id, board_id=db_board.id, role="owner"))
    db.add_all(DBList(name=list_name, board_id=db_board.id) for list_name in DEFAULT_LISTS)

    db.commit()
    db.refresh(db_board)
    return db_board

@router.get("/{board_id}", response_model=BoardOut)
async def get_board(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # SQLAlchemy is synchronous: inside an async route it must run in the threadpool,
    # otherwise the query blocks the event loop and stalls every WebSocket on this worker
    await run_in_threadpool(authorize_board, db, board_id, current_user)

    cache_key = f"board_cache:{board_id}"
    cached_board = await redis_client.get(cache_key)
    if cached_board:
        return json.loads(cached_board)

    db_board = await run_in_threadpool(db.get, Board, board_id)
    board_data = BoardOut.model_validate(db_board).model_dump(mode="json")
    await redis_client.set(cache_key, json.dumps(board_data), ex=BOARD_CACHE_TTL_SECONDS)
    return board_data

@router.get("/{board_id}/lists", response_model=TypingList[ListOut])
def get_board_lists(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user)
    return db.query(DBList).filter(DBList.board_id == board_id).order_by(DBList.id).all()

@router.get("/{board_id}/tasks", response_model=TypingList[TaskOut])
def get_board_tasks(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user)
    # joinedload fetches creators in the same query instead of one lazy query per task (N+1)
    return (
        db.query(Task)
        .join(DBList, Task.list_id == DBList.id)
        .filter(DBList.board_id == board_id)
        .options(joinedload(Task.creator))
        .order_by(Task.id)
        .all()
    )


# ==========================================
# MEMBERS
# ==========================================
@router.get("/{board_id}/members", response_model=TypingList[BoardMemberOut])
def get_board_members(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user)
    rows = (
        db.query(BoardMember, User.username)
        .join(User, User.id == BoardMember.user_id)
        .filter(BoardMember.board_id == board_id)
        .order_by(BoardMember.id)
        .all()
    )
    return [BoardMemberOut(user_id=member.user_id, username=username, role=member.role) for member, username in rows]

@router.post("/{board_id}/members", response_model=BoardMemberOut, status_code=201)
def add_board_member(board_id: int, member_in: BoardMemberCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user, min_role="owner")

    user = db.query(User).filter(User.username == member_in.username).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if get_membership(db, board_id, user.id) is not None:
        raise HTTPException(status_code=409, detail="User is already a member of this board")

    db.add(BoardMember(user_id=user.id, board_id=board_id, role=member_in.role))
    db.commit()

    background_tasks.add_task(publish_event, board_id, {"event": "member_added", "user_id": user.id})
    return BoardMemberOut(user_id=user.id, username=user.username, role=member_in.role)

def _get_target_membership(db: Session, board_id: int, user_id: int) -> BoardMember:
    target = get_membership(db, board_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if target.role == "owner":
        # Ownership transfer is out of scope, so a board must always keep its owner
        raise HTTPException(status_code=400, detail="The board owner can't be changed or removed")
    return target

@router.patch("/{board_id}/members/{user_id}", response_model=BoardMemberOut)
def change_member_role(board_id: int, user_id: int, member_update: BoardMemberUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user, min_role="owner")
    target = _get_target_membership(db, board_id, user_id)

    target.role = member_update.role
    db.commit()

    # Permissions are checked on every request, so the new role applies immediately;
    # the event just lets open clients update their UI
    background_tasks.add_task(publish_event, board_id, {"event": "member_role_changed", "user_id": user_id})
    username = db.query(User.username).filter(User.id == user_id).scalar()
    return BoardMemberOut(user_id=user_id, username=username, role=target.role)

@router.delete("/{board_id}/members/{user_id}")
def remove_member(board_id: int, user_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The owner can remove anyone else; any other member can remove themselves (leave the board)."""
    caller = authorize_board(db, board_id, current_user)
    if user_id != current_user.id and caller.role != "owner":
        raise HTTPException(status_code=403, detail="Only the board owner can remove other members")
    target = _get_target_membership(db, board_id, user_id)

    db.delete(target)
    db.commit()

    # Every server instance closes the removed user's open sockets for this board when this arrives
    background_tasks.add_task(publish_event, board_id, {"event": "member_removed", "user_id": user_id})
    return {"message": "Member removed"}

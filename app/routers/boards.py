import json
from typing import List as TypingList

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from starlette.concurrency import run_in_threadpool

from app.core.deps import authorize_board, get_current_user, get_membership
from app.db.session import get_db
from app.models.board import Board
from app.models.board_member import BoardMember
from app.models.list_ import List as DBList
from app.models.task import Task
from app.models.user import User
from app.schemas.board import BoardCreate, BoardMemberCreate, BoardMemberOut, BoardOut
from app.schemas.list_ import ListOut
from app.schemas.task import TaskOut
from app.services.broadcast_service import redis_client

router = APIRouter()

DEFAULT_LISTS = ["To Do", "In Progress", "Done"]
BOARD_CACHE_TTL_SECONDS = 60


# ==========================================
# BOARDS
# ==========================================
@router.get("/", response_model=TypingList[BoardOut])
def get_boards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return (
        db.query(Board)
        .join(BoardMember, BoardMember.board_id == Board.id)
        .filter(BoardMember.user_id == current_user.id)
        .order_by(Board.id)
        .all()
    )

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
def add_board_member(board_id: int, member_in: BoardMemberCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, board_id, current_user, min_role="owner")

    user = db.query(User).filter(User.username == member_in.username).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if get_membership(db, board_id, user.id) is not None:
        raise HTTPException(status_code=409, detail="User is already a member of this board")

    db.add(BoardMember(user_id=user.id, board_id=board_id, role=member_in.role))
    db.commit()
    return BoardMemberOut(user_id=user.id, username=user.username, role=member_in.role)

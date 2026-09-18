from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models.board_member import BoardMember
from app.models.list_ import List as DBList
from app.models.task import Task
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Higher rank implies every permission of the lower ranks
ROLE_RANK = {"viewer": 0, "editor": 1, "owner": 2}


# ==========================================
# AUTHENTICATION
# ==========================================
def get_user_from_token(token: str, db: Session) -> Optional[User]:
    """Returns the user a JWT belongs to, or None if the token is invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
    username = payload.get("sub")
    if username is None:
        return None
    return db.query(User).filter(User.username == username).first()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    user = get_user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ==========================================
# BOARD AUTHORIZATION
# ==========================================
def get_membership(db: Session, board_id: int, user_id: int) -> Optional[BoardMember]:
    return db.query(BoardMember).filter(
        BoardMember.board_id == board_id,
        BoardMember.user_id == user_id,
    ).first()

def authorize_board(db: Session, board_id: int, user: User, min_role: str = "viewer") -> BoardMember:
    """
    Non-members get 404 rather than 403 so board IDs can't be probed for existence.
    Members without a high enough role get 403.
    """
    membership = get_membership(db, board_id, user.id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Board not found")
    if ROLE_RANK[membership.role] < ROLE_RANK[min_role]:
        raise HTTPException(status_code=403, detail=f"Requires {min_role} access to this board")
    return membership

def get_authorized_list(db: Session, list_id: int, user: User, min_role: str = "viewer") -> DBList:
    db_list = db.query(DBList).filter(DBList.id == list_id).first()
    if db_list is None:
        raise HTTPException(status_code=404, detail="List not found")
    authorize_board(db, db_list.board_id, user, min_role)
    return db_list

def get_authorized_task(db: Session, task_id: int, user: User, min_role: str = "viewer") -> tuple[Task, int]:
    """Returns the task together with the board it belongs to."""
    row = db.query(Task, DBList.board_id).join(DBList, Task.list_id == DBList.id).filter(Task.id == task_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task, board_id = row
    authorize_board(db, board_id, user, min_role)
    return task, board_id

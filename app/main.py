from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List as TypingList, Optional
from pydantic import BaseModel
import json

from app.core.rate_limit import rate_limit
from app.services.task_service import update_task_with_conflict_check
from app.db.session import get_db
from app.models.board import Board
from app.models.task import Task
from app.models.user import User
from app.models.board_member import BoardMember
from app.models.list_ import List as DBList
from app.schemas.board import BoardCreate, BoardOut
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut
from app.schemas.list_ import ListCreate, ListOut
from app.core.deps import get_current_user
from app.routers import auth
from app.routers import websocket
from app.services.broadcast_service import publish_event, redis_client

app = FastAPI(title="Real-Time Collaborative Task Board")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(websocket.router, tags=["websockets"])

class QuickTaskCreate(BaseModel):
    title: str
    description: Optional[str] = ""

# ==========================================
# 1. FRONTEND / ROOT
# ==========================================
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")

# ==========================================
# 2. BOARDS
# ==========================================
@app.get("/boards/", response_model=TypingList[BoardOut])
def get_boards(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    boards = db.query(Board).all()
    return boards

@app.get("/boards/{board_id}")
async def get_board(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cache_key = f"board_cache:{board_id}"
    cached_board = await redis_client.get(cache_key)
    if cached_board:
        return json.loads(cached_board)
        
    db_board = db.query(Board).filter(Board.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="Board not found")
        
    board_data = BoardOut.model_validate(db_board).model_dump(mode="json")
    await redis_client.setex(cache_key, 60, json.dumps(board_data))
    return board_data

@app.get("/boards/{board_id}/lists", response_model=TypingList[ListOut])
def get_board_lists(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lists = db.query(DBList).filter(DBList.board_id == board_id).all()
    return lists

@app.get("/boards/{board_id}/tasks", response_model=TypingList[TaskOut])
def get_board_tasks(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    board_lists = db.query(DBList).filter(DBList.board_id == board_id).all()
    list_ids = [lst.id for lst in board_lists]
    tasks = db.query(Task).filter(Task.list_id.in_(list_ids)).all()
    return tasks

@app.post("/boards/", response_model=BoardOut)
def create_board(board: BoardCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_board = Board(**board.model_dump())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    
    db_member = BoardMember(user_id=current_user.id, board_id=db_board.id, role="owner")
    db.add(db_member)
    
    default_lists = ["To Do", "In Progress", "Done"]
    for list_name in default_lists:
        new_list = DBList(name=list_name, board_id=db_board.id)
        db.add(new_list)
        
    db.commit()
    return db_board

# ==========================================
# 3. LISTS
# ==========================================
@app.post("/lists/", response_model=ListOut)
def create_list(list_in: ListCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_list = DBList(**list_in.model_dump())
    db.add(db_list)
    db.commit()
    db.refresh(db_list)
    
    event_data = {"event": "list_created", "list_id": db_list.id, "name": db_list.name}
    background_tasks.add_task(publish_event, db_list.board_id, event_data)
    
    return db_list

@app.delete("/lists/{list_id}")
def delete_list(list_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_list = db.query(DBList).filter(DBList.id == list_id).first()
    
    if not db_list:
        raise HTTPException(status_code=404, detail="List not found")
    
    board_id = db_list.board_id 
    
    db.delete(db_list)
    db.commit()
    
    background_tasks.add_task(publish_event, board_id, {"event": "list_deleted", "list_id": list_id})
    
    return {"message": "List deleted successfully"}

# ==========================================
# 4. TASKS
# ==========================================
@app.post("/tasks/", response_model=TaskOut, dependencies=[Depends(rate_limit)])
def create_task(task: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = Task(**task.model_dump(), creator_id=current_user.id)
    
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    db_list = db.query(DBList).filter(DBList.id == db_task.list_id).first()
    if db_list:
        event_data = {"event": "task_created", "task_id": db_task.id, "title": db_task.title}
        background_tasks.add_task(publish_event, db_list.board_id, event_data)
        
    return db_task

@app.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task_update: TaskUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = update_task_with_conflict_check(db, task_id, task_update)
    
    db_list = db.query(DBList).filter(DBList.id == db_task.list_id).first()
    if db_list:
        event_data = {"event": "task_updated", "task_id": db_task.id, "new_version": db_task.version}
        background_tasks.add_task(publish_event, db_list.board_id, event_data)
        
    return db_task

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # THE FIX: Safely grab the list to get the board_id before deleting
    db_list = db.query(DBList).filter(DBList.id == task.list_id).first()
    board_id = db_list.board_id if db_list else None
    
    db.delete(task)
    db.commit()
    
    # Safely broadcast the deletion event
    if board_id:
        background_tasks.add_task(publish_event, board_id, {"event": "task_deleted", "task_id": task_id})
        
    return {"message": "Task deleted successfully"}
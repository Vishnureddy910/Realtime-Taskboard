from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.rate_limit import rate_limit
from fastapi import Request
from app.services.task_service import update_task_with_conflict_check
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List as TypingList
import json

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
from app.services.broadcast_service import publish_event,redis_client

app = FastAPI(title="Real-Time Collaborative Task Board")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(websocket.router, tags=["websockets"])

@app.post("/boards/", response_model=BoardOut)
def create_board(board: BoardCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_board = Board(**board.model_dump())
    db.add(db_board)
    db.commit()
    db.refresh(db_board)
    
    db_member = BoardMember(user_id=current_user.id, board_id=db_board.id, role="owner")
    db.add(db_member)
    db.commit()
    return db_board

@app.post("/lists/", response_model=ListOut)
def create_list(list_in: ListCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_list = DBList(**list_in.model_dump())
    db.add(db_list)
    db.commit()
    db.refresh(db_list)
    return db_list

@app.post("/tasks/", response_model=TaskOut, dependencies=[Depends(rate_limit)])
def create_task(task: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_task = Task(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    db_list = db.query(DBList).filter(DBList.id == db_task.list_id).first()
    if db_list:
        event_data = {"event": "task_created", "task_id": db_task.id, "title": db_task.title}
        # Publish to Redis instead of local broadcast
        background_tasks.add_task(publish_event, db_list.board_id, event_data)
        
    return db_task

@app.put("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task_update: TaskUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    
    # 1. Update the task using our conflict-resolution service
    db_task = update_task_with_conflict_check(db, task_id, task_update)
    
    # 2. Publish the WebSocket event via Redis
    db_list = db.query(DBList).filter(DBList.id == db_task.list_id).first()
    if db_list:
        event_data = {"event": "task_updated", "task_id": db_task.id, "new_version": db_task.version}
        background_tasks.add_task(publish_event, db_list.board_id, event_data)
        
    return db_task

@app.get("/boards/{board_id}/tasks", response_model=TypingList[TaskOut])
def get_board_tasks(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Find all lists that belong to this board
    board_lists = db.query(DBList).filter(DBList.board_id == board_id).all()
    list_ids = [lst.id for lst in board_lists]
    
    # 2. Find all tasks that belong to those lists
    tasks = db.query(Task).filter(Task.list_id.in_(list_ids)).all()
    
    return tasks

# Mount the frontend directory so we can serve the app.js file
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Serve the main index.html page at the root URL
@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")

# --- TEMPORARY HTML CLIENT TO TEST WEBSOCKETS ---
@app.get("/test-ws/{board_id}", response_class=HTMLResponse)
async def get_test_page(board_id: int):
    html = f"""
    <!DOCTYPE html>
    <html>
        <head><title>Board {board_id} Live Updates</title></head>
        <body>
            <h2>Live WebSocket Feed for Board {board_id}</h2>
            <ul id='messages' style="font-family: monospace; background: #f4f4f4; padding: 20px;"></ul>
            <script>
                // Dynamically grab the current port (8000 or 8001) so it connects to the right server
                var ws = new WebSocket("ws://" + window.location.host + "/ws/boards/{board_id}");
                ws.onmessage = function(event) {{
                    var messages = document.getElementById('messages');
                    var message = document.createElement('li');
                    message.textContent = event.data;
                    messages.appendChild(message);
                }};
            </script>
        </body>
    </html>
    """
    return html

@app.get("/boards/{board_id}")
async def get_board(board_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cache_key = f"board_cache:{board_id}"
    
    # 1. Check Redis Cache First
    cached_board = await redis_client.get(cache_key)
    if cached_board:
        print(f"\n⚡ CACHE HIT: Returning board {board_id} from Redis (Skipped DB!)")
        return json.loads(cached_board)
        
    print(f"\n🐢 CACHE MISS: Querying PostgreSQL for board {board_id}")
    
    # 2. If not in cache, query the Database
    db_board = db.query(Board).filter(Board.id == board_id).first()
    if not db_board:
        raise HTTPException(status_code=404, detail="Board not found")
        
    # 3. Convert SQLAlchemy model to a JSON-serializable dictionary using Pydantic
    board_data = BoardOut.model_validate(db_board).model_dump(mode="json")
    
    # 4. Save to Redis with a 60-second expiration (Time-To-Live)
    await redis_client.setex(cache_key, 60, json.dumps(board_data))
    
    return board_data
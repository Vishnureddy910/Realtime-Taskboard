from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_authorized_list, get_authorized_task, get_current_user
from app.core.rate_limit import task_creation_rate_limit
from app.db.session import get_db
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskOut, TaskUpdate
from app.services.broadcast_service import publish_event
from app.services.task_service import update_task_with_conflict_check

router = APIRouter()

@router.post("/", response_model=TaskOut, dependencies=[Depends(task_creation_rate_limit)])
def create_task(task: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_list = get_authorized_list(db, task.list_id, current_user, min_role="editor")

    db_task = Task(**task.model_dump(), creator_id=current_user.id)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    event_data = {"event": "task_created", "task_id": db_task.id, "title": db_task.title}
    background_tasks.add_task(publish_event, db_list.board_id, event_data)

    return db_task

@router.put("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, task_update: TaskUpdate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _, board_id = get_authorized_task(db, task_id, current_user, min_role="editor")

    # A task may only move between lists of its own board
    if task_update.list_id is not None:
        target_list = get_authorized_list(db, task_update.list_id, current_user, min_role="editor")
        if target_list.board_id != board_id:
            raise HTTPException(status_code=400, detail="Tasks cannot be moved to a list on another board")

    db_task = update_task_with_conflict_check(db, task_id, task_update)

    event_data = {"event": "task_updated", "task_id": db_task.id, "new_version": db_task.version}
    background_tasks.add_task(publish_event, board_id, event_data)

    return db_task

@router.delete("/{task_id}")
def delete_task(task_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    task, board_id = get_authorized_task(db, task_id, current_user, min_role="editor")

    db.delete(task)
    db.commit()

    background_tasks.add_task(publish_event, board_id, {"event": "task_deleted", "task_id": task_id})

    return {"message": "Task deleted successfully"}

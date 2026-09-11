from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.task import Task
from app.schemas.task import TaskUpdate

def update_task_with_conflict_check(db: Session, task_id: int, task_update: TaskUpdate):
    db_task = db.query(Task).filter(Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # CORE LOGIC: Optimistic Concurrency Conflict Resolution
    if db_task.version != task_update.expected_version:
        raise HTTPException(
            status_code=409, 
            detail=f"Conflict: Task was modified by another user. Current database version is {db_task.version}."
        )
    
    # Apply updates, excluding the expected_version from the actual data modification
    update_data = task_update.model_dump(exclude={"expected_version"}, exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_task, key, value)
        
    # Increment the version number for the next time it gets edited
    db_task.version += 1
    
    db.commit()
    db.refresh(db_task)
    return db_task
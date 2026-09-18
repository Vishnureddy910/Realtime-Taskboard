from sqlalchemy import update
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.task import Task
from app.schemas.task import TaskUpdate

def update_task_with_conflict_check(db: Session, task_id: int, task_update: TaskUpdate) -> Task:
    """
    Optimistic concurrency control as a single atomic compare-and-swap.

    The version check lives in the UPDATE's WHERE clause rather than in Python.
    Postgres row-locks the task during the UPDATE; a concurrent writer blocks,
    then re-evaluates the WHERE clause against the committed row, finds the
    version has moved on, and matches zero rows. Exactly one writer per
    version can succeed, no matter how many arrive at once.
    """
    update_data = task_update.model_dump(exclude={"expected_version"}, exclude_unset=True)

    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.version == task_update.expected_version)
        .values(**update_data, version=Task.version + 1)
        .execution_options(synchronize_session=False)
    )

    if result.rowcount == 0:
        db.rollback()
        current_version = db.query(Task.version).filter(Task.id == task_id).scalar()
        if current_version is None:
            raise HTTPException(status_code=404, detail="Task not found")
        raise HTTPException(
            status_code=409,
            detail=f"Conflict: Task was modified by another user. Current database version is {current_version}.",
        )

    db.commit()
    return db.query(Task).filter(Task.id == task_id).one()

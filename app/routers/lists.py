from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.deps import authorize_board, get_authorized_list, get_current_user
from app.db.session import get_db
from app.models.list_ import List as DBList
from app.models.user import User
from app.schemas.list_ import ListCreate, ListOut
from app.services.broadcast_service import publish_event

router = APIRouter()

@router.post("/", response_model=ListOut)
def create_list(list_in: ListCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    authorize_board(db, list_in.board_id, current_user, min_role="editor")

    db_list = DBList(**list_in.model_dump())
    db.add(db_list)
    db.commit()
    db.refresh(db_list)

    event_data = {"event": "list_created", "list_id": db_list.id, "name": db_list.name}
    background_tasks.add_task(publish_event, db_list.board_id, event_data)

    return db_list

@router.delete("/{list_id}")
def delete_list(list_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_list = get_authorized_list(db, list_id, current_user, min_role="editor")
    board_id = db_list.board_id

    # The list's tasks are removed by the database (ON DELETE CASCADE)
    db.delete(db_list)
    db.commit()

    background_tasks.add_task(publish_event, board_id, {"event": "list_deleted", "list_id": list_id})

    return {"message": "List deleted successfully"}

from app.db.session import SessionLocal
from app.models.user import User
from app.models.board import Board
from app.models.board_member import BoardMember
from app.models.list_ import List
from app.models.task import Task

def clean_user_data(username: str):
    db = SessionLocal()
    
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"User '{username}' not found.")
            return

        # 1. Find all boards this user owns
        owned_memberships = db.query(BoardMember).filter(
            BoardMember.user_id == user.id, 
            BoardMember.role == "owner"
        ).all()
        board_ids = [m.board_id for m in owned_memberships]

        if board_ids:
            # 2. Find all lists in those boards
            lists = db.query(List).filter(List.board_id.in_(board_ids)).all()
            list_ids = [l.id for l in lists]
            
            # 3. Delete from the bottom up: Tasks -> Lists -> BoardMembers -> Boards
            if list_ids:
                deleted_tasks = db.query(Task).filter(Task.list_id.in_(list_ids)).delete(synchronize_session=False)
                print(f"Deleted {deleted_tasks} tasks.")
                
            deleted_lists = db.query(List).filter(List.board_id.in_(board_ids)).delete(synchronize_session=False)
            print(f"Deleted {deleted_lists} lists.")
            
            db.query(BoardMember).filter(BoardMember.board_id.in_(board_ids)).delete(synchronize_session=False)
            deleted_boards = db.query(Board).filter(Board.id.in_(board_ids)).delete(synchronize_session=False)
            print(f"Deleted {deleted_boards} boards.")

        # 4. Remove the user from any other boards they joined, then delete the user
        db.query(BoardMember).filter(BoardMember.user_id == user.id).delete(synchronize_session=False)
        db.delete(user)
        db.commit()
        
        print(f"Successfully wiped all data for user '{username}'. Database is clean!")
        
    except Exception as e:
        db.rollback()
        print(f"Error during cleanup: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    # Change "vishnu" to whatever username you created
    clean_user_data("vishnu")
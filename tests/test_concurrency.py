import threading

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.task import Task
from app.schemas.task import TaskUpdate
from app.services.task_service import update_task_with_conflict_check
from tests.helpers import create_board, create_task, register

WRITERS = 20


@pytest.fixture
def task(client):
    alice = register(client, "alice")
    board = create_board(client, alice)
    return alice, board, create_task(client, alice, board["lists"][0]["id"], title="Original")


def test_stale_version_is_rejected_with_409(client, task):
    alice, board, created = task
    first = client.put(f"/tasks/{created['id']}", json={"title": "First", "expected_version": 1}, headers=alice.headers)
    assert first.status_code == 200

    stale = client.put(f"/tasks/{created['id']}", json={"title": "Second", "expected_version": 1}, headers=alice.headers)
    assert stale.status_code == 409

    current = client.get(f"/boards/{board['id']}/tasks", headers=alice.headers).json()[0]
    assert current["title"] == "First"
    assert current["version"] == 2


def test_concurrent_writers_with_same_version_exactly_one_wins(task):
    """
    WRITERS threads all hold version 1 and are released at the same instant.
    A read-then-check-then-write implementation lets every one of them through
    (lost updates); the atomic compare-and-swap must accept exactly one.
    """
    _, _, created = task

    # A warm pool with a connection per writer, so connection setup time
    # doesn't accidentally serialise the writers and hide the race
    race_engine = create_engine(settings.DATABASE_URL, pool_size=WRITERS)
    connections = [race_engine.connect() for _ in range(WRITERS)]
    for connection in connections:
        connection.execute(text("SELECT 1"))
        connection.close()
    RaceSession = sessionmaker(bind=race_engine)

    barrier = threading.Barrier(WRITERS)
    winners, conflicts, errors = [], [], []

    def writer(i):
        with RaceSession() as db:
            barrier.wait()
            try:
                update_task_with_conflict_check(db, created["id"], TaskUpdate(title=f"writer-{i}", expected_version=1))
                winners.append(i)
            except HTTPException as exc:
                (conflicts if exc.status_code == 409 else errors).append(exc)
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(WRITERS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with RaceSession() as db:
        final = db.get(Task, created["id"])
        final_version, final_title = final.version, final.title
    race_engine.dispose()

    assert errors == []
    assert len(winners) == 1
    assert len(conflicts) == WRITERS - 1
    assert final_version == 2
    assert final_title == f"writer-{winners[0]}"

from contextlib import contextmanager

from sqlalchemy import event

from app.db.session import engine
from tests.helpers import add_member, create_board, create_task, register


@contextmanager
def count_queries():
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_new_board_has_owner_and_default_lists(client):
    alice = register(client, "alice")
    board = create_board(client, alice)

    assert [lst["name"] for lst in board["lists"]] == ["To Do", "In Progress", "Done"]
    members = client.get(f"/boards/{board['id']}/members", headers=alice.headers).json()
    assert members == [{"user_id": alice.id, "username": "alice", "role": "owner"}]


def test_get_board_uses_cache_after_first_read(client, redis_sync):
    alice = register(client, "alice")
    board = create_board(client, alice, "Cached")

    assert client.get(f"/boards/{board['id']}", headers=alice.headers).json()["name"] == "Cached"
    assert redis_sync.exists(f"board_cache:{board['id']}")
    assert client.get(f"/boards/{board['id']}", headers=alice.headers).json()["name"] == "Cached"


def test_deleting_a_list_deletes_its_tasks(client):
    alice = register(client, "alice")
    board = create_board(client, alice)
    todo = board["lists"][0]["id"]
    create_task(client, alice, todo, "a")
    create_task(client, alice, todo, "b")

    assert client.delete(f"/lists/{todo}", headers=alice.headers).status_code == 200
    assert client.get(f"/boards/{board['id']}/tasks", headers=alice.headers).json() == []


def test_board_tasks_query_count_does_not_grow_with_tasks(client):
    """Guards against N+1: each task's creator must not trigger its own query."""
    alice = register(client, "alice")
    board = create_board(client, alice)
    list_id = board["lists"][0]["id"]

    create_task(client, alice, list_id)
    with count_queries() as few:
        client.get(f"/boards/{board['id']}/tasks", headers=alice.headers)

    for name in ["bob", "carol", "dave", "erin"]:
        member = register(client, name)
        add_member(client, alice, board["id"], member)
        create_task(client, member, list_id)
    with count_queries() as many:
        tasks = client.get(f"/boards/{board['id']}/tasks", headers=alice.headers).json()

    assert len(tasks) == 5
    assert {t["creator"]["username"] for t in tasks} == {"alice", "bob", "carol", "dave", "erin"}
    assert len(many) == len(few)

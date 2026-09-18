import pytest
from starlette.websockets import WebSocketDisconnect

from app.websockets.connection_manager import CLOSE_NOT_A_MEMBER, CLOSE_UNAUTHENTICATED

from tests.helpers import add_member, create_board, create_task, register


@pytest.fixture
def alice_board(client):
    alice = register(client, "alice")
    board = create_board(client, alice, "Alice's board")
    task = create_task(client, alice, board["lists"][0]["id"])
    return alice, board, task


def test_users_only_see_their_own_boards(client, alice_board):
    bob = register(client, "bob")
    create_board(client, bob, "Bob's board")

    names = [b["name"] for b in client.get("/boards/", headers=bob.headers).json()]
    assert names == ["Bob's board"]


def test_non_member_gets_404_everywhere(client, alice_board):
    _, board, task = alice_board
    mallory = register(client, "mallory")
    list_id = board["lists"][0]["id"]

    # 404 rather than 403: non-members can't even learn the board exists
    assert client.get(f"/boards/{board['id']}", headers=mallory.headers).status_code == 404
    assert client.get(f"/boards/{board['id']}/tasks", headers=mallory.headers).status_code == 404
    assert client.get(f"/boards/{board['id']}/lists", headers=mallory.headers).status_code == 404
    assert client.post("/tasks/", json={"title": "x", "list_id": list_id}, headers=mallory.headers).status_code == 404
    assert client.put(f"/tasks/{task['id']}", json={"title": "pwned", "expected_version": 1}, headers=mallory.headers).status_code == 404
    assert client.delete(f"/tasks/{task['id']}", headers=mallory.headers).status_code == 404
    assert client.delete(f"/lists/{list_id}", headers=mallory.headers).status_code == 404
    assert client.post("/lists/", json={"name": "x", "board_id": board["id"]}, headers=mallory.headers).status_code == 404


def test_viewer_can_read_but_not_write(client, alice_board):
    alice, board, task = alice_board
    victor = register(client, "victor")
    add_member(client, alice, board["id"], victor, role="viewer")

    assert client.get(f"/boards/{board['id']}/tasks", headers=victor.headers).status_code == 200
    assert client.put(f"/tasks/{task['id']}", json={"title": "x", "expected_version": 1}, headers=victor.headers).status_code == 403
    assert client.delete(f"/tasks/{task['id']}", headers=victor.headers).status_code == 403


def test_invited_editor_can_collaborate(client, alice_board):
    alice, board, task = alice_board
    bob = register(client, "bob")
    add_member(client, alice, board["id"], bob, role="editor")

    response = client.put(f"/tasks/{task['id']}", json={"title": "Edited by Bob", "expected_version": 1}, headers=bob.headers)
    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_only_owner_can_add_members(client, alice_board):
    alice, board, _ = alice_board
    bob = register(client, "bob")
    register(client, "carol")
    add_member(client, alice, board["id"], bob, role="editor")

    response = client.post(f"/boards/{board['id']}/members", json={"username": "carol"}, headers=bob.headers)
    assert response.status_code == 403


def test_member_cannot_be_added_twice(client, alice_board):
    alice, board, _ = alice_board
    bob = register(client, "bob")
    add_member(client, alice, board["id"], bob)

    response = client.post(f"/boards/{board['id']}/members", json={"username": "bob"}, headers=alice.headers)
    assert response.status_code == 409


def test_task_cannot_be_moved_to_another_board(client, alice_board):
    alice, board, task = alice_board
    bob = register(client, "bob")
    add_member(client, alice, board["id"], bob)
    bobs_board = create_board(client, bob, "Bob's board")

    response = client.put(
        f"/tasks/{task['id']}",
        json={"list_id": bobs_board["lists"][0]["id"], "expected_version": 1},
        headers=bob.headers,
    )
    assert response.status_code == 400


@pytest.mark.parametrize("token", [None, "garbage"])
def test_websocket_rejects_missing_or_invalid_token(client, alice_board, token):
    _, board, _ = alice_board
    url = f"/ws/boards/{board['id']}" + (f"?token={token}" if token else "")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(url) as ws:
            ws.receive_text()
    assert closed.value.code == CLOSE_UNAUTHENTICATED


def test_websocket_rejects_non_members(client, alice_board):
    _, board, _ = alice_board
    mallory = register(client, "mallory")
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(f"/ws/boards/{board['id']}?token={mallory.token}") as ws:
            ws.receive_text()
    assert closed.value.code == CLOSE_NOT_A_MEMBER

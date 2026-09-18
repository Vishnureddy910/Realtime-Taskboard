import pytest
from starlette.websockets import WebSocketDisconnect

from app.websockets.connection_manager import CLOSE_NOT_A_MEMBER
from tests.helpers import add_member, create_board, create_task, register, wait_for_subscriber


@pytest.fixture
def team(client):
    """alice owns a board with bob as editor and victor as viewer."""
    alice, bob, victor = register(client, "alice"), register(client, "bob"), register(client, "victor")
    board = create_board(client, alice, "Team")
    add_member(client, alice, board["id"], bob, role="editor")
    add_member(client, alice, board["id"], victor, role="viewer")
    return alice, bob, victor, board


def members_url(board, user=None):
    return f"/boards/{board['id']}/members" + (f"/{user.id}" if user else "")


def test_board_list_shows_your_role_and_member_count(client, team):
    alice, bob, victor, board = team
    for user, role in [(alice, "owner"), (bob, "editor"), (victor, "viewer")]:
        [summary] = client.get("/boards/", headers=user.headers).json()
        assert (summary["name"], summary["role"], summary["member_count"]) == ("Team", role, 3)


def test_any_member_can_see_the_member_list(client, team):
    _, _, victor, board = team
    members = client.get(members_url(board), headers=victor.headers).json()
    assert [(m["username"], m["role"]) for m in members] == [("alice", "owner"), ("bob", "editor"), ("victor", "viewer")]


def test_owner_changes_role_and_it_applies_immediately(client, team):
    alice, bob, _, board = team
    task = create_task(client, alice, board["lists"][0]["id"])

    response = client.patch(members_url(board, bob), json={"role": "viewer"}, headers=alice.headers)
    assert response.status_code == 200
    assert response.json() == {"user_id": bob.id, "username": "bob", "role": "viewer"}

    denied = client.put(f"/tasks/{task['id']}", json={"title": "x", "expected_version": 1}, headers=bob.headers)
    assert denied.status_code == 403


def test_only_owner_can_change_roles(client, team):
    _, bob, victor, board = team
    response = client.patch(members_url(board, victor), json={"role": "editor"}, headers=bob.headers)
    assert response.status_code == 403


def test_owner_cannot_be_demoted_or_removed(client, team):
    alice, _, _, board = team
    assert client.patch(members_url(board, alice), json={"role": "viewer"}, headers=alice.headers).status_code == 400
    assert client.delete(members_url(board, alice), headers=alice.headers).status_code == 400


def test_owner_removes_member_and_access_is_revoked(client, team):
    alice, bob, _, board = team

    assert client.delete(members_url(board, bob), headers=alice.headers).status_code == 200

    assert client.get("/boards/", headers=bob.headers).json() == []
    assert client.get(f"/boards/{board['id']}/tasks", headers=bob.headers).status_code == 404
    assert client.get("/boards/", headers=alice.headers).json()[0]["member_count"] == 2


def test_member_can_leave_a_board(client, team):
    _, _, victor, board = team
    assert client.delete(members_url(board, victor), headers=victor.headers).status_code == 200
    assert client.get("/boards/", headers=victor.headers).json() == []


def test_non_owner_cannot_remove_others(client, team):
    _, bob, victor, board = team
    assert client.delete(members_url(board, victor), headers=bob.headers).status_code == 403


def test_removing_a_non_member_is_404(client, team):
    alice, _, _, board = team
    stranger = register(client, "stranger")
    assert client.delete(members_url(board, stranger), headers=alice.headers).status_code == 404


def test_removed_member_is_disconnected_immediately(client, redis_sync, team):
    """Revocation reaches open sockets: the removed user's live connection is closed, not just future requests."""
    alice, bob, _, board = team
    base = f"/ws/boards/{board['id']}?token="

    with client.websocket_connect(base + alice.token) as alice_ws, client.websocket_connect(base + bob.token) as bob_ws:
        wait_for_subscriber(redis_sync, f"board:{board['id']}")

        client.delete(members_url(board, bob), headers=alice.headers)

        with pytest.raises(WebSocketDisconnect) as closed:
            bob_ws.receive_json()
        assert closed.value.code == CLOSE_NOT_A_MEMBER
        assert alice_ws.receive_json() == {"event": "member_removed", "user_id": bob.id}


def test_membership_changes_are_pushed_to_the_board(client, redis_sync, team):
    alice, bob, _, board = team
    newcomer = register(client, "newcomer")

    with client.websocket_connect(f"/ws/boards/{board['id']}?token={alice.token}") as ws:
        wait_for_subscriber(redis_sync, f"board:{board['id']}")

        add_member(client, alice, board["id"], newcomer)
        assert ws.receive_json() == {"event": "member_added", "user_id": newcomer.id}

        client.patch(members_url(board, bob), json={"role": "viewer"}, headers=alice.headers)
        assert ws.receive_json() == {"event": "member_role_changed", "user_id": bob.id}

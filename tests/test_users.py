from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from tests.helpers import add_member, create_board, register


def search(client, user, q, board_id=None):
    params = {"q": q} if board_id is None else {"q": q, "board_id": board_id}
    return client.get("/users/search", params=params, headers=user.headers)


def test_search_is_case_insensitive_prefix_match(client):
    alice = register(client, "alice")
    for name in ["Bobby", "bob", "robert"]:
        register(client, name)

    response = search(client, alice, "BO")
    assert response.status_code == 200
    assert [u["username"] for u in response.json()] == ["Bobby", "bob"]


def test_search_never_exposes_email(client):
    alice = register(client, "alice")
    register(client, "bob")

    assert search(client, alice, "bo").json() == [{"id": 2, "username": "bob"}]


def test_search_excludes_yourself(client):
    alice = register(client, "alice")
    register(client, "alicia")

    assert [u["username"] for u in search(client, alice, "ali").json()] == ["alicia"]


def test_like_wildcards_are_treated_literally(client):
    alice = register(client, "alice")
    register(client, "bob")
    register(client, "b_x")

    assert search(client, alice, "%%").json() == []
    assert [u["username"] for u in search(client, alice, "b_").json()] == ["b_x"]


def test_results_are_capped(client):
    alice = register(client, "alice")
    for i in range(10):
        register(client, f"user{i}")

    assert len(search(client, alice, "us").json()) == 8


def test_query_must_be_at_least_two_characters(client):
    alice = register(client, "alice")
    assert search(client, alice, "a").status_code == 422


def test_search_requires_login(client):
    assert client.get("/users/search", params={"q": "bo"}).status_code == 401


def test_board_scoped_search_excludes_existing_members(client):
    alice = register(client, "alice")
    bob, bobby = register(client, "bob"), register(client, "bobby")
    board = create_board(client, alice)
    add_member(client, alice, board["id"], bob)

    assert [u["username"] for u in search(client, alice, "bob", board["id"]).json()] == [bobby.username]


def test_board_scoped_search_is_owner_only(client):
    alice = register(client, "alice")
    bob = register(client, "bob")
    mallory = register(client, "mallory")
    board = create_board(client, alice)
    add_member(client, alice, board["id"], bob, role="editor")

    assert search(client, bob, "ma", board["id"]).status_code == 403
    assert search(client, mallory, "bo", board["id"]).status_code == 404


def test_search_is_rate_limited(client):
    alice = register(client, "alice")
    statuses = [search(client, alice, "zz").status_code for _ in range(settings.USER_SEARCH_RATE_LIMIT + 1)]
    assert statuses[-1] == 429
    assert set(statuses[:-1]) == {200}


def test_prefix_search_can_use_the_index():
    """The planner can answer lower(username) LIKE 'ab%' from the prefix index instead of scanning users."""
    with engine.connect() as conn:
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0] for row in conn.execute(text("EXPLAIN SELECT id FROM users WHERE lower(username) LIKE 'ab%'"))
        )
    assert "ix_users_username_lower_prefix" in plan

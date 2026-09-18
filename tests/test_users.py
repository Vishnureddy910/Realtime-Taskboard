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

    assert search(client, alice, "bo").json() == [{"id": 2, "username": "bob", "shared_boards": []}]


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


def test_single_character_query_works_and_empty_is_rejected(client):
    alice = register(client, "alice")
    register(client, "bob")

    assert [u["username"] for u in search(client, alice, "b").json()] == ["bob"]
    assert search(client, alice, "").status_code == 422


def test_collaborators_rank_first_with_shared_boards(client):
    alice = register(client, "alice")
    ben, bob = register(client, "ben"), register(client, "bob")
    sprint = create_board(client, alice, "Sprint")
    batman = create_board(client, alice, "Batman")
    add_member(client, alice, sprint["id"], bob)
    add_member(client, alice, batman["id"], bob)

    results = search(client, alice, "b").json()
    # bob outranks ben despite sorting later alphabetically, because alice already works with him
    assert [(u["username"], u["shared_boards"]) for u in results] == [
        ("bob", ["Batman", "Sprint"]),
        ("ben", []),
    ]


def test_shared_boards_never_reveal_boards_the_searcher_is_not_on(client):
    alice, bob = register(client, "alice"), register(client, "bob")
    create_board(client, bob, "Bob's secret board")
    together = create_board(client, alice, "Together")
    add_member(client, alice, together["id"], bob)

    assert search(client, alice, "bob").json()[0]["shared_boards"] == ["Together"]


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

from app.core.config import settings
from tests.helpers import add_member, create_board, register


def test_task_creation_is_limited_per_user(client, redis_sync):
    alice, bob = register(client, "alice"), register(client, "bob")
    board = create_board(client, alice)
    add_member(client, alice, board["id"], bob)
    list_id = board["lists"][0]["id"]

    statuses = [
        client.post("/tasks/", json={"title": f"t{i}", "list_id": list_id}, headers=alice.headers).status_code
        for i in range(settings.TASK_RATE_LIMIT + 1)
    ]
    assert statuses == [200] * settings.TASK_RATE_LIMIT + [429]

    # Same client IP, different user: has its own budget
    response = client.post("/tasks/", json={"title": "bob's", "list_id": list_id}, headers=bob.headers)
    assert response.status_code == 200


def test_rate_limit_counter_always_has_an_expiry(client, redis_sync):
    alice = register(client, "alice")
    board = create_board(client, alice)
    client.post("/tasks/", json={"title": "t", "list_id": board["lists"][0]["id"]}, headers=alice.headers)

    ttl = redis_sync.ttl(f"rate_limit:tasks:{alice.id}")
    assert 0 < ttl <= settings.TASK_RATE_WINDOW_SECONDS

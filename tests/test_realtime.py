import asyncio
import time

from app.websockets.connection_manager import ConnectionManager
from tests.helpers import create_board, create_task, register


def _wait_for_subscriber(redis_sync, channel: str, timeout: float = 5.0):
    # The Redis listener starts asynchronously after the socket connects
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dict(redis_sync.pubsub_numsub(channel)).get(channel, 0) > 0:
            return
        time.sleep(0.05)
    raise AssertionError(f"No subscriber on {channel}")


def test_mutation_is_pushed_to_connected_member(client, redis_sync):
    alice = register(client, "alice")
    board = create_board(client, alice)

    with client.websocket_connect(f"/ws/boards/{board['id']}?token={alice.token}") as ws:
        _wait_for_subscriber(redis_sync, f"board:{board['id']}")

        task = create_task(client, alice, board["lists"][0]["id"], title="Live")

        event = ws.receive_json()
        assert event == {"event": "task_created", "task_id": task["id"], "title": "Live"}


def test_event_published_by_another_instance_is_delivered(client, redis_sync):
    """Any server instance publishing to the board channel reaches this instance's sockets."""
    alice = register(client, "alice")
    board = create_board(client, alice)
    channel = f"board:{board['id']}"

    with client.websocket_connect(f"/ws/boards/{board['id']}?token={alice.token}") as ws:
        _wait_for_subscriber(redis_sync, channel)

        redis_sync.publish(channel, '{"event": "task_deleted", "task_id": 42}')

        assert ws.receive_json() == {"event": "task_deleted", "task_id": 42}


class _FakeSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.received = []

    async def send_text(self, message: str):
        if self.fail:
            raise RuntimeError("connection closed")
        self.received.append(message)


def test_dead_socket_does_not_block_delivery_to_others():
    manager = ConnectionManager()
    healthy, dead, also_healthy = _FakeSocket(), _FakeSocket(fail=True), _FakeSocket()
    manager.active_connections[1] = [healthy, dead, also_healthy]

    asyncio.run(manager.broadcast("hello", 1))

    assert healthy.received == ["hello"]
    assert also_healthy.received == ["hello"]
    assert manager.active_connections[1] == [healthy, also_healthy]

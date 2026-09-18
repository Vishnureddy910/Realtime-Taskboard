"""
Fan-out load test: how long does one edit take to reach every connected client?

Opens CLIENTS WebSockets to one board, spread round-robin across one or more server
instances, then makes UPDATES sequential edits (alternating instances) and measures,
for every client, the time from sending the HTTP request to receiving the event.
That covers the whole path: HTTP -> Postgres commit -> Redis publish -> every
instance's subscriber -> every socket.

Usage (servers must share the same Postgres and Redis):
    python scripts/loadtest.py --targets http://localhost:8001,http://localhost:8002 --clients 200 --updates 50
"""
import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx
import websockets

WARMUP_EDITS_PER_INSTANCE = 3


def percentile(values, pct):
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[index]


def describe(label, seconds):
    ms = [s * 1000 for s in seconds]
    return (
        f"{label:<24} p50 {percentile(ms, 50):7.1f} ms   p95 {percentile(ms, 95):7.1f} ms   "
        f"p99 {percentile(ms, 99):7.1f} ms   max {max(ms):7.1f} ms   mean {statistics.mean(ms):7.1f} ms"
    )


async def setup(http, target):
    """Creates a throwaway user, a board and one task to edit."""
    username = f"load-{uuid.uuid4().hex[:8]}"
    await http.post(f"{target}/auth/signup", json={"username": username, "email": f"{username}@example.com", "password": "load-test"})
    login = await http.post(f"{target}/auth/login", data={"username": username, "password": "load-test"})
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    board = (await http.post(f"{target}/boards/", json={"name": "Load test"}, headers=headers)).json()
    todo = (await http.get(f"{target}/boards/{board['id']}/lists", headers=headers)).json()[0]
    task = (await http.post(f"{target}/tasks/", json={"title": "load", "list_id": todo["id"]}, headers=headers)).json()
    return token, headers, board["id"], task["id"]


async def listen(socket, version_received_at):
    """Records when this client receives each task version."""
    async for raw in socket:
        event = json.loads(raw)
        if event.get("event") == "task_updated":
            version_received_at.setdefault(event["new_version"], time.perf_counter())


async def main(targets, clients, updates, interval):
    async with httpx.AsyncClient(timeout=30) as http:
        token, headers, board_id, task_id = await setup(http, targets[0])

        ws_targets = [t.replace("http", "ws", 1) for t in targets]
        sockets = await asyncio.gather(*(
            websockets.connect(f"{ws_targets[i % len(ws_targets)]}/ws/boards/{board_id}?token={token}", max_queue=None)
            for i in range(clients)
        ))
        received = [dict() for _ in sockets]
        listeners = [asyncio.create_task(listen(s, r)) for s, r in zip(sockets, received)]
        await asyncio.sleep(1.0)  # let every instance finish subscribing to the board's Redis channel

        async def edit(version, target):
            response = await http.put(f"{target}/tasks/{task_id}", json={"title": f"v{version}", "expected_version": version}, headers=headers)
            response.raise_for_status()

        # Untimed warm-up: each instance's first requests open pooled DB connections and
        # prepare statements, which would otherwise show up as a one-off outlier
        version = 1
        for _ in range(WARMUP_EDITS_PER_INSTANCE):
            for target in targets:
                await edit(version, target)
                version += 1
        await asyncio.sleep(0.5)

        sent_at, write_latencies = {}, []
        for i in range(updates):
            target = targets[i % len(targets)]
            started = time.perf_counter()
            sent_at[version + 1] = started
            await edit(version, target)
            write_latencies.append(time.perf_counter() - started)
            version += 1
            await asyncio.sleep(interval)

        await asyncio.sleep(2.0)  # let the last events arrive
        for listener in listeners:
            listener.cancel()
        await asyncio.gather(*(s.close() for s in sockets), return_exceptions=True)

    deliveries = [at - sent_at[version] for per_client in received for version, at in per_client.items() if version in sent_at]
    expected = clients * updates

    print(f"instances: {len(targets)}   clients: {clients}   timed updates: {updates} (after {WARMUP_EDITS_PER_INSTANCE} warm-up edits per instance)")
    print(f"delivered {len(deliveries)} / {expected} events ({100 * len(deliveries) / expected:.1f}%)")
    print(describe("HTTP write (PUT)", write_latencies))
    print(describe("edit -> every client", deliveries))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--targets", default="http://localhost:8000", help="comma-separated server base URLs")
    parser.add_argument("--clients", type=int, default=100)
    parser.add_argument("--updates", type=int, default=50)
    parser.add_argument("--interval", type=float, default=0.1, help="seconds between edits")
    args = parser.parse_args()
    asyncio.run(main(args.targets.split(","), args.clients, args.updates, args.interval))

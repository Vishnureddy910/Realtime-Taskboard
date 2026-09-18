from app.services.broadcast_service import redis_client


def test_health_reports_ok_when_dependencies_are_up(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_health_returns_503_when_redis_is_down(client, monkeypatch):
    async def unreachable():
        raise ConnectionError("redis is down")

    monkeypatch.setattr(redis_client, "ping", unreachable)

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "ok", "redis": "unavailable"}

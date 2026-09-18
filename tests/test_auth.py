from tests.helpers import register


def test_frontend_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_signup_login_and_me(client):
    alice = register(client, "alice")
    response = client.get("/auth/me", headers=alice.headers)
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


def test_duplicate_username_is_rejected(client):
    register(client, "alice")
    response = client.post("/auth/signup", json={"username": "alice", "email": "other@example.com", "password": "pw"})
    assert response.status_code == 400


def test_wrong_password_is_rejected(client):
    register(client, "alice")
    response = client.post("/auth/login", data={"username": "alice", "password": "wrong"})
    assert response.status_code == 401


def test_protected_routes_require_a_token(client):
    assert client.get("/boards/").status_code == 401
    assert client.post("/boards/", json={"name": "No auth"}).status_code == 401


def test_invalid_token_is_rejected(client):
    response = client.get("/boards/", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401

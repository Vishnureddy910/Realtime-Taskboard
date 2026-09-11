from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_frontend_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

def test_login_success():
    response = client.post(
        "/auth/login",
        data={"username": "testuser", "password": "password"} 
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_create_board_unauthorized():
    response = client.post(
        "/boards/",
        json={"title": "Hacker Board", "description": "Should fail"}
    )
    assert response.status_code == 401
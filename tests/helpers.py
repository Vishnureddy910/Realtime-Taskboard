from dataclasses import dataclass


@dataclass
class AuthUser:
    id: int
    username: str
    token: str

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}


def register(client, username: str, password: str = "correct-horse") -> AuthUser:
    signup = client.post("/auth/signup", json={"username": username, "email": f"{username}@example.com", "password": password})
    assert signup.status_code == 200, signup.text
    login = client.post("/auth/login", data={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return AuthUser(id=signup.json()["id"], username=username, token=login.json()["access_token"])


def create_board(client, owner: AuthUser, name: str = "Board") -> dict:
    """Creates a board and returns it with its default lists under 'lists'."""
    board = client.post("/boards/", json={"name": name}, headers=owner.headers)
    assert board.status_code == 200, board.text
    lists = client.get(f"/boards/{board.json()['id']}/lists", headers=owner.headers)
    return {**board.json(), "lists": lists.json()}


def add_member(client, owner: AuthUser, board_id: int, member: AuthUser, role: str = "editor"):
    response = client.post(f"/boards/{board_id}/members", json={"username": member.username, "role": role}, headers=owner.headers)
    assert response.status_code == 201, response.text


def create_task(client, user: AuthUser, list_id: int, title: str = "Task") -> dict:
    response = client.post("/tasks/", json={"title": title, "list_id": list_id}, headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()

import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.security import COOKIE, sign_device, signature


class Browser:
    """Independent browser cookies sharing TestClient's single application event loop."""

    def __init__(self, client, secret):
        self.client = client
        self.device = uuid4()
        self.headers = {
            "Cookie": f"{COOKIE}={sign_device(secret, self.device)}",
            "X-CSRF-Token": signature(secret, "csrf:" + str(self.device)),
        }

    def get(self, path):
        return self.client.get(path, headers=self.headers)

    def post(self, path, body=None):
        return self.client.post(path, json=body or {}, headers=self.headers)


@pytest.fixture
def client():
    settings = Settings()
    if not settings.database_url.endswith("/qr_chuvsu_test"):
        pytest.fail("Tests require a dedicated qr_chuvsu_test database")
    app = create_app(settings)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        client.portal.call(
            app.state.pool.execute, "TRUNCATE attendance,sessions,ip_rate_limits RESTART IDENTITY CASCADE"
        )
        yield client


@pytest.fixture
def browser(client):
    return lambda: Browser(client, client.app.state.secret)


@pytest.fixture
def teacher(browser):
    return browser()


@pytest.fixture
def session(teacher):
    response = teacher.post(
        "/api/sessions",
        {
            "title": "Базы данных",
            "group_name": "ИВТ-21",
            "teacher_name": "Иванов И. И.",
            "campus_id": "chuvsu-g",
            "duration_minutes": 30,
            "radius": 150,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def student_data(name="Иванов Иван Иванович", seed="one", **changes):
    data = {
        "student_name": name,
        "group_name": "ИВТ-21",
        "latitude": 56.1457245,
        "longitude": 47.2243805,
        "fingerprint": {
            "user_agent": "TestBrowser/1 " + seed,
            "language": "ru-RU",
            "timezone": "Europe/Moscow",
            "screen_width": 390,
            "screen_height": 844,
        },
    }
    data.update(changes)
    return data


def csrf_from_html(text):
    return re.search(r'name="csrf-token" content="([a-f0-9]+)"', text).group(1)

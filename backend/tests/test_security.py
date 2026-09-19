from uuid import uuid4

import pytest
from conftest import csrf_from_html, student_data

from app.models import BrowserFingerprint
from app.services.security import COOKIE, fingerprint_hash, haversine, read_device, sign_device


def test_cookie_bootstrap_and_csrf(client):
    response = client.get("/")
    cookie = response.cookies[COOKIE]
    assert read_device(client.app.state.secret, cookie) is not None
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert client.post("/api/sessions/resolve", json={"code": "000000"}).status_code == 403
    token = csrf_from_html(response.text)
    assert (
        client.post(
            "/api/sessions/resolve", json={"code": "000000"}, headers={"X-CSRF-Token": token}
        ).status_code
        == 410
    )
    assert (
        client.post(
            "/api/sessions/resolve",
            json={"code": "000000"},
            headers={
                "X-CSRF-Token": token,
                "Origin": "https://attacker.invalid",
            },
        ).status_code
        == 403
    )


def test_foreign_browser_cannot_manage_session(browser, session):
    stranger = browser()
    for path in [
        session["teacher_url"],
        session["qr_path"],
        f"/api/sessions/{session['id']}/attendance",
        f"/api/sessions/{session['id']}/export",
    ]:
        assert stranger.get(path).status_code == 404
    for action in ["close", "manual"]:
        body = {"student_name": "Чужой Студент", "group_name": "ИВТ-21"} if action == "manual" else {}
        assert stranger.post(f"/api/sessions/{session['id']}/{action}", body).status_code == 404


def test_cookie_cannot_be_forged():
    secret = "example"
    signed = sign_device(secret, uuid4())
    assert read_device(secret, signed) is not None
    assert read_device(secret, signed + "x") is None
    assert read_device("other", signed) is None
    assert read_device(secret, "garbage") is None
    assert read_device(secret, signed + "é") is None


def test_haversine():
    assert haversine(56.14, 47.20, 56.14, 47.20) == 0
    assert haversine(0, 0, 0, 1) == pytest.approx(111194.927, abs=0.01)
    assert haversine(0, 179.999, 0, -179.999) == pytest.approx(222.39, abs=0.1)
    assert haversine(90, 0, -90, 0) == pytest.approx(20015086.8, abs=1)


def test_fingerprint_orientation():
    data = student_data()["fingerprint"]
    one = fingerprint_hash(BrowserFingerprint(**data))
    data["screen_width"], data["screen_height"] = data["screen_height"], data["screen_width"]
    assert fingerprint_hash(BrowserFingerprint(**data)) == one


@pytest.mark.parametrize(
    "change",
    [
        {"latitude": 91},
        {"longitude": -181},
        {"student_name": ""},
        {"group_name": ""},
        {"latitude": "NaN"},
        {"unexpected": True},
        {"student_name": "Иван\u0001ов"},
        {"student_name": "Иван\u0000ов"},
    ],
)
def test_validation(browser, session, change):
    result = browser().post(f"/api/attendance/{session['session_code']}", student_data(**change))
    assert result.status_code == 422
    assert "errors" in result.json()


def test_html_escapes_student_input(teacher, session):
    malicious = "<script>alert(1)</script>"
    teacher.post(
        f"/api/sessions/{session['id']}/manual",
        {
            "student_name": malicious,
            "group_name": "ИВТ-21",
        },
    )
    page = teacher.get(session["teacher_url"])
    assert malicious not in page.text
    assert "&lt;script&gt;" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]


def test_sql_injection_is_data(teacher, session):
    name = "Robert'); DROP TABLE sessions;--"
    result = teacher.post(
        f"/api/sessions/{session['id']}/manual",
        {
            "student_name": name,
            "group_name": "ИВТ-21",
        },
    )
    assert result.status_code == 200
    assert teacher.get(session["teacher_url"]).status_code == 200

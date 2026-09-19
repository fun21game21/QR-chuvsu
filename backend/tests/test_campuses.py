from uuid import UUID

import pytest
from conftest import student_data

from app.services.campuses import CAMPUSES, CATALOGUE


def session_data(**changes):
    data = {
        "title": "Проверка корпуса",
        "group_name": "ИВТ-21",
        "teacher_name": "Тестовый преподаватель",
        "campus_id": "chuvsu-g",
        "duration_minutes": 30,
        "radius": 150,
    }
    data.update(changes)
    return data


@pytest.mark.parametrize("campus", CATALOGUE, ids=lambda c: c.id)
def test_campus_coordinates_are_saved_and_used(client, teacher, browser, campus):
    response = teacher.post("/api/sessions", session_data(campus_id=campus.id))
    assert response.status_code == 201, response.text
    session = response.json()
    stored = client.portal.call(
        client.app.state.pool.fetchrow,
        "SELECT campus_id,latitude,longitude,location_name FROM sessions WHERE id=$1",
        UUID(session["id"]),
    )
    assert dict(stored) == {
        "campus_id": campus.id,
        "latitude": campus.latitude,
        "longitude": campus.longitude,
        "location_name": campus.label,
    }
    assert campus.label in teacher.get(session["teacher_url"]).text
    result = browser().post(
        f"/api/attendance/{session['session_code']}",
        student_data(latitude=campus.latitude, longitude=campus.longitude),
    )
    assert result.status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"campus_id": "unknown"},
        {"campus_id": ""},
        {"campus_id": None},
        {"latitude": 0, "longitude": 0},
        {"location_name": "Произвольное место"},
    ],
)
def test_client_cannot_override_campus_location(teacher, changes):
    result = teacher.post("/api/sessions", session_data(**changes))
    assert result.status_code == 422


def test_different_campus_is_outside_zone(teacher, browser, session):
    other = CAMPUSES["chuvsu-e"]
    student = browser()
    result = student.post(
        f"/api/attendance/{session['session_code']}",
        student_data(latitude=other.latitude, longitude=other.longitude),
    )
    assert result.status_code == 422
    assert result.json()["reason"] == "outside_zone"
    rows = teacher.get(f"/api/sessions/{session['id']}/attendance").json()
    assert rows[0]["status"] == "rejected"
    assert rows[0]["distance_m"] > 150
    assert student.post(f"/api/attendance/{session['session_code']}", student_data()).status_code == 200


def test_form_offers_catalogue_without_manual_coordinates(teacher):
    page = teacher.get("/teacher/new")
    assert page.status_code == 200
    assert 'name="campus_id" required' in page.text
    for campus in CATALOGUE:
        assert f'value="{campus.id}"' in page.text
    assert 'name="latitude"' not in page.text
    assert 'name="longitude"' not in page.text
    assert "Центр зоны присутствия" not in page.text
    assert "Посещаемость без переклички" not in page.text
    assert "Доработан Максимкой" in page.text


def test_existing_session_uses_saved_coordinates(client, teacher, browser, session):
    # A legacy session has no campus_id; it must keep its original geozone.
    client.portal.call(
        client.app.state.pool.execute,
        "UPDATE sessions SET campus_id=NULL,latitude=56.14,longitude=47.20 WHERE id=$1",
        UUID(session["id"]),
    )
    result = browser().post(
        f"/api/attendance/{session['session_code']}",
        student_data(latitude=56.14, longitude=47.20),
    )
    assert result.status_code == 200
    assert teacher.get(session["teacher_url"]).status_code == 200

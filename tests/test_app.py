"""Flask アプリ(Web UI / REST API)の統合テスト。"""

import pytest

from timecard import create_app


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "test.db"
    app = create_app(db_path=str(db_path))
    app.config.update(TESTING=True)
    with app.test_client() as client:
        yield client


def _create_employee(client, code="E001", name="山田太郎"):
    resp = client.post("/api/employees", json={"code": code, "name": name})
    assert resp.status_code == 201
    return resp.get_json()["id"]


def test_index_empty(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "社員が登録されていません".encode() in resp.data


def test_create_employee_api(client):
    emp_id = _create_employee(client)
    assert isinstance(emp_id, int)

    resp = client.get("/api/employees")
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["code"] == "E001"
    assert data[0]["status"] == "off"


def test_duplicate_employee_code_rejected(client):
    _create_employee(client, code="E001")
    resp = client.post("/api/employees", json={"code": "E001", "name": "別人"})
    assert resp.status_code == 409


def test_create_employee_requires_fields(client):
    resp = client.post("/api/employees", json={"code": "", "name": ""})
    assert resp.status_code == 400


def test_punch_flow(client):
    emp_id = _create_employee(client)

    # 出勤
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "in"})
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "working"

    # 休憩開始 → 休憩中
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "break_in"})
    assert resp.get_json()["status"] == "on_break"

    # 休憩終了 → 勤務中
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "break_out"})
    assert resp.get_json()["status"] == "working"

    # 退勤 → 未出勤
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "out"})
    assert resp.get_json()["status"] == "off"


def test_invalid_transition_rejected(client):
    emp_id = _create_employee(client)
    # 出勤前に退勤はできない
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "out"})
    assert resp.status_code == 400


def test_double_clock_in_rejected(client):
    emp_id = _create_employee(client)
    client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "in"})
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "in"})
    assert resp.status_code == 400


def test_punch_unknown_employee(client):
    resp = client.post("/api/employees/999/punch", json={"punch_type": "in"})
    assert resp.status_code == 404


def test_invalid_punch_type(client):
    emp_id = _create_employee(client)
    resp = client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "lunch"})
    assert resp.status_code == 400


def test_summary_api(client):
    emp_id = _create_employee(client)
    client.post(f"/api/employees/{emp_id}/punch", json={"punch_type": "in"})
    resp = client.get(f"/api/employees/{emp_id}/summary")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "working"
    assert data["clock_in"] is not None
    assert data["incomplete"] is True  # まだ退勤していない


def test_summary_unknown_employee(client):
    resp = client.get("/api/employees/999/summary")
    assert resp.status_code == 404


def test_web_forms(client):
    # フォーム経由での社員登録
    resp = client.post("/employees", data={"code": "E010", "name": "佐藤花子"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "佐藤花子".encode() in resp.data

    # 詳細ページが表示できる
    emp_id = client.get("/api/employees").get_json()[0]["id"]
    resp = client.get(f"/employee/{emp_id}")
    assert resp.status_code == 200
    assert "佐藤花子".encode() in resp.data


def test_employee_detail_not_found(client):
    resp = client.get("/employee/999")
    assert resp.status_code == 404

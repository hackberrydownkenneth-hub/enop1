"""カラー剤計算機の利用登録まわりのテスト。"""

import pytest

from colormix_server import create_app, db
from colormix_server.validation import (
    ValidationError,
    normalize_instagram,
    validate_registration,
)


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "colormix.db")


@pytest.fixture()
def app(db_path, monkeypatch):
    monkeypatch.delenv("COLORMIX_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("COLORMIX_ALLOWED_ORIGIN", raising=False)
    return create_app(db_path)


@pytest.fixture()
def client(app):
    return app.test_client()


def post(client, **payload):
    return client.post("/api/register", json=payload)


# ---------- 入力チェック ----------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("your_id", "your_id"),
        ("@your_id", "your_id"),
        ("  @Your_ID  ", "your_id"),
        ("https://www.instagram.com/foo.bar/", "foo.bar"),
        ("https://instagram.com/foo.bar?hl=ja", "foo.bar"),
        ("instagram.com/Foo_Bar/", "foo_bar"),
        ("foo/bar", "foo"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_instagram(raw, expected):
    assert normalize_instagram(raw) == expected


def test_validate_keeps_salon_only_for_salon_stylists():
    salon = validate_registration(
        {"affiliation": "salon", "salon": " SALON TOKYO ", "instagram": "@Stylist_Me", "lang": "ja"}
    )
    assert salon == {
        "affiliation": "salon",
        "salon": "SALON TOKYO",
        "instagram": "stylist_me",
        "lang": "ja",
    }

    freelance = validate_registration(
        {"affiliation": "freelance", "salon": "消える", "instagram": "stylist_me", "lang": "yue"}
    )
    assert freelance["salon"] == ""


@pytest.mark.parametrize(
    "payload,code",
    [
        ({}, "affiliation"),
        ({"affiliation": "owner", "instagram": "me"}, "affiliation"),
        # サロン所属は店名が必須
        ({"affiliation": "salon", "instagram": "me"}, "salon"),
        ({"affiliation": "salon", "salon": "   ", "instagram": "me"}, "salon"),
        ({"affiliation": "salon", "salon": "S"}, "instagram"),
        ({"affiliation": "salon", "salon": "S", "instagram": "  "}, "instagram"),
        ({"affiliation": "salon", "salon": "S", "instagram": "だめな名前"}, "instagram_format"),
        ({"affiliation": "salon", "salon": "S", "instagram": "a" * 31}, "instagram_format"),
        ({"affiliation": "salon", "salon": "S", "instagram": "has space"}, "instagram_format"),
        # フリーランスは店名なしでよい
        ({"affiliation": "freelance"}, "instagram"),
    ],
)
def test_validate_rejects_bad_input(payload, code):
    with pytest.raises(ValidationError) as excinfo:
        validate_registration(payload)
    assert excinfo.value.code == code


def test_unknown_language_is_dropped():
    record = validate_registration(
        {"affiliation": "freelance", "instagram": "stylist_me", "lang": "klingon"}
    )
    assert record["lang"] == ""


def test_salon_name_is_truncated():
    record = validate_registration(
        {"affiliation": "salon", "salon": "あ" * 200, "instagram": "stylist_me"}
    )
    assert len(record["salon"]) == 80


# ---------- 登録 API ----------


def test_register_saves_new_stylist(client, db_path):
    response = post(client, affiliation="salon", salon="SALON TOKYO", instagram="@Stylist.01", lang="ja")
    assert response.status_code == 201
    assert response.get_json() == {"ok": True, "created": True, "instagram": "stylist.01"}

    rows = db.list_registrations(db_path)
    assert len(rows) == 1
    assert rows[0]["instagram"] == "stylist.01"
    assert rows[0]["affiliation"] == "salon"
    assert rows[0]["salon"] == "SALON TOKYO"


def test_same_instagram_updates_instead_of_duplicating(client, db_path):
    post(client, affiliation="salon", salon="前の店", instagram="stylist_me", lang="ja")
    response = post(client, affiliation="freelance", instagram="@STYLIST_ME", lang="yue")

    assert response.status_code == 200
    assert response.get_json()["created"] is False

    rows = db.list_registrations(db_path)
    assert len(rows) == 1
    assert rows[0]["affiliation"] == "freelance"
    assert rows[0]["salon"] == ""


@pytest.mark.parametrize(
    "handle", ["123", "111", "1234", "0000", "aaa", "ab", "test", "abc", ".foo", "foo."]
)
def test_validate_rejects_fake_instagram(handle):
    with pytest.raises(ValidationError) as excinfo:
        validate_registration(
            {"affiliation": "freelance", "instagram": handle, "lang": "ja"}
        )
    assert excinfo.value.code == "instagram_fake"


@pytest.mark.parametrize(
    "handle",
    ["kenneth_hk", "drive.blue", "a1b2c3", "hair_by_ken", "salon.tokyo.hk", "ken1"],
)
def test_validate_accepts_real_looking_instagram(handle):
    record = validate_registration(
        {"affiliation": "freelance", "instagram": handle, "lang": "ja"}
    )
    assert record["instagram"] == handle


def test_register_rejects_fake_instagram(client, db_path):
    response = post(client, affiliation="freelance", instagram="123")
    assert response.status_code == 400
    assert response.get_json()["error"] == "instagram_fake"
    assert db.list_registrations(db_path) == []


def test_register_rejects_bad_input(client, db_path):
    response = post(client, affiliation="salon", salon="SALON TOKYO", instagram="ダメ")
    assert response.status_code == 400
    assert response.get_json()["error"] == "instagram_format"

    response = post(client, affiliation="salon", instagram="stylist_me")
    assert response.status_code == 400
    assert response.get_json()["error"] == "salon"
    assert db.list_registrations(db_path) == []


def test_register_rejects_non_json(client):
    assert client.post("/api/register", data="hello").status_code == 400


def test_rate_limit_blocks_flooding(db_path, monkeypatch):
    monkeypatch.setenv("COLORMIX_RATE_LIMIT", "3")
    client = create_app(db_path).test_client()

    for i in range(3):
        assert post(client, affiliation="freelance", instagram="user%d" % i).status_code == 201

    blocked = post(client, affiliation="freelance", instagram="user_over")
    assert blocked.status_code == 429
    assert blocked.get_json()["error"] == "rate_limited"
    assert len(db.list_registrations(db_path)) == 3


def test_cors_header_only_when_configured(db_path, monkeypatch):
    monkeypatch.setenv("COLORMIX_ALLOWED_ORIGIN", "https://salon.example")
    client = create_app(db_path).test_client()

    response = post(client, affiliation="freelance", instagram="stylist_me")
    assert response.headers["Access-Control-Allow-Origin"] == "https://salon.example"
    assert client.open("/api/register", method="OPTIONS").status_code == 204


# ---------- 管理画面 ----------


def test_admin_is_closed_until_a_token_is_set(client):
    assert client.get("/admin").status_code == 503
    assert client.get("/admin/registrations.csv").status_code == 503


def test_admin_needs_the_right_token(db_path, monkeypatch):
    monkeypatch.setenv("COLORMIX_ADMIN_TOKEN", "secret-token")
    client = create_app(db_path).test_client()
    post(client, affiliation="salon", salon="SALON TOKYO", instagram="stylist", lang="ja")

    assert client.get("/admin").status_code == 404
    assert client.get("/admin?token=wrong").status_code == 404

    page = client.get("/admin?token=secret-token")
    assert page.status_code == 200
    body = page.data.decode()
    assert "stylist" in body
    assert "SALON TOKYO" in body


def test_admin_csv_export(db_path, monkeypatch):
    monkeypatch.setenv("COLORMIX_ADMIN_TOKEN", "secret-token")
    client = create_app(db_path).test_client()
    post(client, affiliation="freelance", instagram="freelancer", lang="yue")

    response = client.get("/admin/registrations.csv?token=secret-token")
    assert response.status_code == 200
    text = response.data.decode("utf-8")
    assert text.startswith("﻿")
    assert "instagram,affiliation,salon,lang" in text
    assert "freelancer,freelance,,yue" in text


# ---------- 画面の配信 ----------


def test_serves_the_calculator_with_api_mode(client):
    assert b"<title>" in client.get("/").data

    config = client.get("/config.js").data.decode()
    assert '"mode": "api"' in config
    assert '"apiUrl": "/api/register"' in config


def test_build_artifacts_are_not_served(client):
    assert client.get("/standalone.html").status_code == 404
    assert client.get("/calc.test.js").status_code == 404
    assert client.get("/calc.js").status_code == 200

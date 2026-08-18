from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.server.host_app import create_app


_ADMIN_PASSWORD = "correct horse battery staple"
_SESSION_SECRET = "test-session-signing-secret-with-32-bytes"
_AUTH_SESSION_PATH = "/api/v1/query/auth/session"
_AUTH_LOGIN_PATH = "/api/v1/command/auth/login"
_AUTH_LOGOUT_PATH = "/api/v1/command/auth/logout"


@asynccontextmanager
async def _lifespan(_app):
    yield


def _enable_admin_auth(monkeypatch) -> None:
    monkeypatch.setenv("CWS_ADMIN_PASSWORD", _ADMIN_PASSWORD)
    monkeypatch.setenv("CWS_ADMIN_SESSION_SECRET", _SESSION_SECRET)
    monkeypatch.setenv("CWS_ADMIN_COOKIE_SECURE", "1")


def _assert_public_error(response, code: str) -> None:
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["details"] == {}


def test_auth_session_reports_disabled_when_admin_password_is_not_configured(monkeypatch):
    monkeypatch.delenv("CWS_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("CWS_ADMIN_SESSION_SECRET", raising=False)

    client = TestClient(create_app(lifespan=_lifespan))

    response = client.get(_AUTH_SESSION_PATH)

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "enabled": False,
            "authenticated": False,
            "csrf_token": None,
        },
    }


def test_visitor_cannot_call_command_when_admin_auth_is_enabled(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)

    @app.post("/api/v1/command/example")
    def example_command():
        return {"called": True}

    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/v1/command/example")

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_AUTH_REQUIRED")


def test_command_cors_preflight_does_not_require_admin_session(monkeypatch):
    _enable_admin_auth(monkeypatch)
    monkeypatch.delenv("CWS_ALLOWED_ORIGINS", raising=False)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    response = client.options(
        "/api/v1/command/example",
        headers={
            "Origin": "http://localhost:53147",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:53147"


def test_visitor_cannot_list_saves_when_admin_auth_is_enabled(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)

    @app.get("/api/v1/query/saves")
    def list_saves():
        return {"ok": True, "data": {"saves": ["private-save.json"]}}

    client = TestClient(app, base_url="https://testserver")

    response = client.get("/api/v1/query/saves")

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_AUTH_REQUIRED")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/query/world/state",
        "/api/settings",
    ],
)
def test_visitor_can_read_public_surfaces_when_admin_auth_is_enabled(monkeypatch, path):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    app.add_api_route(path, lambda: {"public": True}, methods=["GET"])
    client = TestClient(app, base_url="https://testserver")

    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {"public": True}


def test_visitor_cannot_change_settings_when_admin_auth_is_enabled(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)

    @app.patch("/api/settings")
    def change_settings():
        return {"changed": True}

    client = TestClient(app, base_url="https://testserver")

    response = client.patch("/api/settings", json={"ui": {"locale": "en-US"}})

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_AUTH_REQUIRED")


def test_visitor_cannot_reset_settings_when_admin_auth_is_enabled(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)

    @app.post("/api/settings/reset")
    def reset_settings():
        return {"reset": True}

    client = TestClient(app, base_url="https://testserver")

    response = client.post("/api/settings/reset")

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_AUTH_REQUIRED")


@pytest.mark.parametrize(
    "path",
    [
        "/api/settings/llm",
        "/api/settings/llm/status",
    ],
)
def test_visitor_cannot_read_llm_configuration_when_admin_auth_is_enabled(monkeypatch, path):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    app.add_api_route(path, lambda: {"sensitive": True}, methods=["GET"])
    client = TestClient(app, base_url="https://testserver")

    response = client.get(path)

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_AUTH_REQUIRED")


@pytest.mark.parametrize("session_secret", [None, "too-short"])
def test_admin_auth_fails_closed_when_session_secret_is_not_strong(monkeypatch, session_secret):
    monkeypatch.setenv("CWS_ADMIN_PASSWORD", _ADMIN_PASSWORD)
    if session_secret is None:
        monkeypatch.delenv("CWS_ADMIN_SESSION_SECRET", raising=False)
    else:
        monkeypatch.setenv("CWS_ADMIN_SESSION_SECRET", session_secret)

    with pytest.raises(RuntimeError, match="CWS_ADMIN_SESSION_SECRET"):
        create_app(lifespan=_lifespan)


def test_admin_auth_fails_closed_when_admin_password_is_too_short(monkeypatch):
    monkeypatch.setenv("CWS_ADMIN_PASSWORD", "too-short")
    monkeypatch.setenv("CWS_ADMIN_SESSION_SECRET", _SESSION_SECRET)

    with pytest.raises(RuntimeError, match="CWS_ADMIN_PASSWORD"):
        create_app(lifespan=_lifespan)


def test_admin_auth_fails_closed_when_only_session_secret_is_configured(monkeypatch):
    monkeypatch.delenv("CWS_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("CWS_ADMIN_SESSION_SECRET", _SESSION_SECRET)

    with pytest.raises(RuntimeError, match="CWS_ADMIN_PASSWORD"):
        create_app(lifespan=_lifespan)


@pytest.mark.parametrize(
    ("password", "session_secret", "expected_variable"),
    [
        (
            "replace-with-a-long-random-password",
            _SESSION_SECRET,
            "CWS_ADMIN_PASSWORD",
        ),
        (
            _ADMIN_PASSWORD,
            "replace-with-at-least-32-random-characters",
            "CWS_ADMIN_SESSION_SECRET",
        ),
    ],
)
def test_admin_auth_rejects_documented_placeholder_secrets(
    monkeypatch,
    password,
    session_secret,
    expected_variable,
):
    monkeypatch.setenv("CWS_ADMIN_PASSWORD", password)
    monkeypatch.setenv("CWS_ADMIN_SESSION_SECRET", session_secret)

    with pytest.raises(RuntimeError, match=expected_variable):
        create_app(lifespan=_lifespan)


def test_wrong_admin_password_does_not_create_session(monkeypatch):
    _enable_admin_auth(monkeypatch)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    response = client.post(_AUTH_LOGIN_PATH, json={"password": "definitely-wrong"})

    assert response.status_code == 401
    _assert_public_error(response, "ADMIN_LOGIN_INVALID")
    assert "set-cookie" not in response.headers
    assert client.get(_AUTH_SESSION_PATH).json()["data"]["authenticated"] is False


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"{}", "application/json"),
        (b"{", "application/json"),
    ],
)
def test_invalid_admin_login_request_uses_public_error_contract(
    monkeypatch,
    body,
    content_type,
):
    _enable_admin_auth(monkeypatch)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    response = client.post(
        _AUTH_LOGIN_PATH,
        content=body,
        headers={"Content-Type": content_type},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "ADMIN_LOGIN_REQUEST_INVALID"
    assert payload["error"]["message"] == "Administrator login request is invalid"
    assert isinstance(payload["error"]["details"]["errors"], list)
    assert all(
        "input" not in error and "ctx" not in error
        for error in payload["error"]["details"]["errors"]
    )


def test_correct_admin_password_creates_secure_http_only_session(monkeypatch):
    _enable_admin_auth(monkeypatch)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})

    assert response.status_code == 200
    response_payload = response.json()
    assert response_payload["ok"] is True
    payload = response_payload["data"]
    assert payload["enabled"] is True
    assert payload["authenticated"] is True
    assert isinstance(payload["csrf_token"], str)
    assert len(payload["csrf_token"]) >= 32
    cookie = response.headers["set-cookie"].lower()
    assert "cws_admin_session=" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    assert "max-age=" in cookie
    assert response.headers["cache-control"] == "no-store"

    session_response = client.get(_AUTH_SESSION_PATH)
    assert session_response.status_code == 200
    assert session_response.json() == {"ok": True, "data": payload}
    assert session_response.headers["cache-control"] == "no-store"


def test_tampered_session_cookie_is_rejected(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    client = TestClient(app, base_url="https://testserver")
    client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    cookie = client.cookies.get("cws_admin_session")
    assert cookie
    replacement = "A" if cookie[-1] != "A" else "B"
    tampered_cookie = f"{cookie[:-1]}{replacement}"
    client.cookies.clear()

    response = client.get(
        _AUTH_SESSION_PATH,
        headers={"Cookie": f"cws_admin_session={tampered_cookie}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["authenticated"] is False


def test_cookie_secure_flag_can_be_disabled_for_local_http_testing(monkeypatch):
    _enable_admin_auth(monkeypatch)
    monkeypatch.setenv("CWS_ADMIN_COOKIE_SECURE", "0")
    client = TestClient(create_app(lifespan=_lifespan))

    response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})

    cookie = response.headers["set-cookie"].lower()
    assert "; secure" not in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert client.get(_AUTH_SESSION_PATH).json()["data"]["authenticated"] is True


def test_authenticated_admin_can_read_save_list_without_csrf(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)

    @app.get("/api/v1/query/saves")
    def list_saves():
        return {"ok": True, "data": {"saves": ["admin-save.json"]}}

    client = TestClient(app, base_url="https://testserver")
    login_response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    assert login_response.status_code == 200

    response = client.get("/api/v1/query/saves")

    assert response.status_code == 200
    assert response.json()["data"]["saves"] == ["admin-save.json"]


def test_authenticated_write_without_csrf_is_rejected_before_handler(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    calls = []

    @app.post("/api/v1/command/example")
    def example_command():
        calls.append("called")
        return {"ok": True}

    client = TestClient(app, base_url="https://testserver")
    login_response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    assert login_response.status_code == 200

    response = client.post("/api/v1/command/example")

    assert response.status_code == 403
    _assert_public_error(response, "ADMIN_CSRF_INVALID")
    assert calls == []


def test_authenticated_write_with_wrong_csrf_is_rejected_before_handler(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    calls = []

    @app.post("/api/v1/command/example")
    def example_command():
        calls.append("called")
        return {"ok": True}

    client = TestClient(app, base_url="https://testserver")
    login_response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    assert login_response.status_code == 200

    response = client.post(
        "/api/v1/command/example",
        headers={"X-CSRF-Token": "wrong-token"},
    )

    assert response.status_code == 403
    _assert_public_error(response, "ADMIN_CSRF_INVALID")
    assert calls == []


def test_authenticated_write_with_csrf_reaches_existing_handler(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    calls = []

    @app.post("/api/v1/command/example")
    def example_command():
        calls.append("called")
        return {"ok": True}

    client = TestClient(app, base_url="https://testserver")
    login_response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    csrf_token = login_response.json()["data"]["csrf_token"]

    response = client.post(
        "/api/v1/command/example",
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == ["called"]


def test_logout_invalidates_server_session_and_clears_cookie(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    client = TestClient(app, base_url="https://testserver")
    login_response = client.post(_AUTH_LOGIN_PATH, json={"password": _ADMIN_PASSWORD})
    csrf_token = login_response.json()["data"]["csrf_token"]
    issued_cookie = client.cookies.get("cws_admin_session")
    assert issued_cookie

    response = client.post(
        _AUTH_LOGOUT_PATH,
        json={},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "data": {
            "enabled": True,
            "authenticated": False,
            "csrf_token": None,
        },
    }
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.get(_AUTH_SESSION_PATH).json()["data"]["authenticated"] is False

    replay_client = TestClient(app, base_url="https://testserver")
    replay_response = replay_client.get(
        _AUTH_SESSION_PATH,
        headers={"Cookie": f"cws_admin_session={issued_cookie}"},
    )
    assert replay_response.json()["data"]["authenticated"] is False


def test_server_session_registry_evicts_oldest_session_at_limit(monkeypatch):
    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    client = TestClient(app, base_url="https://testserver")
    first_login = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": _ADMIN_PASSWORD},
    )
    first_cookie = client.cookies.get("cws_admin_session")
    assert first_login.status_code == 200
    assert first_cookie

    for _ in range(64):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": _ADMIN_PASSWORD},
        )
        assert response.status_code == 200

    replay_client = TestClient(app, base_url="https://testserver")
    replay_response = replay_client.get(
        _AUTH_SESSION_PATH,
        headers={"Cookie": f"cws_admin_session={first_cookie}"},
    )

    assert replay_response.json()["data"]["authenticated"] is False


def test_repeated_failed_logins_are_rate_limited(monkeypatch):
    _enable_admin_auth(monkeypatch)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for _ in range(5):
        response = client.post(_AUTH_LOGIN_PATH, json={"password": "wrong-password"})
        assert response.status_code == 401

    blocked_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "still-wrong"},
    )

    assert blocked_response.status_code == 429
    _assert_public_error(blocked_response, "ADMIN_LOGIN_RATE_LIMITED")
    assert int(blocked_response.headers["retry-after"]) > 0
    assert "set-cookie" not in blocked_response.headers


def test_parallel_failed_logins_cannot_overrun_limit(monkeypatch):
    from src.server import admin_auth as admin_auth_module

    _enable_admin_auth(monkeypatch)
    app = create_app(lifespan=_lifespan)
    start_barrier = threading.Barrier(6)
    compare_calls = 0
    compare_calls_lock = threading.Lock()
    five_compares_started = threading.Event()
    six_compares_started = threading.Event()
    release_compares = threading.Event()
    original_password_matches = admin_auth_module._AdminAuth.password_matches

    def slow_password_matches(auth, supplied_password):
        nonlocal compare_calls
        with compare_calls_lock:
            compare_calls += 1
            if compare_calls >= 5:
                five_compares_started.set()
            if compare_calls >= 6:
                six_compares_started.set()
        assert release_compares.wait(timeout=5)
        return original_password_matches(auth, supplied_password)

    def attempt_login():
        client = TestClient(app, base_url="https://testserver")
        start_barrier.wait(timeout=5)
        return client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
        ).status_code

    with patch.object(
        admin_auth_module._AdminAuth,
        "password_matches",
        slow_password_matches,
    ):
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(attempt_login) for _ in range(6)]
            assert five_compares_started.wait(timeout=5)
            six_compares_started.wait(timeout=0.5)
            release_compares.set()
            statuses = [future.result(timeout=5) for future in futures]

    assert statuses.count(401) == 5
    assert statuses.count(429) == 1


def test_cloudflare_client_ip_header_is_not_trusted_by_default(monkeypatch):
    _enable_admin_auth(monkeypatch)
    monkeypatch.delenv("CWS_TRUST_CLOUDFLARE_IP", raising=False)
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for index in range(5):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": f"203.0.113.{index + 1}"},
        )
        assert response.status_code == 401

    blocked_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "wrong-password"},
        headers={"CF-Connecting-IP": "203.0.113.250"},
    )

    assert blocked_response.status_code == 429


def test_cloudflare_client_ip_can_be_trusted_explicitly(monkeypatch):
    _enable_admin_auth(monkeypatch)
    monkeypatch.setenv("CWS_TRUST_CLOUDFLARE_IP", "1")
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for _ in range(5):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": "203.0.113.10"},
        )
        assert response.status_code == 401

    other_source_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "wrong-password"},
        headers={"CF-Connecting-IP": "203.0.113.11"},
    )

    assert other_source_response.status_code == 401


def test_invalid_cloudflare_client_ip_falls_back_to_peer(monkeypatch):
    _enable_admin_auth(monkeypatch)
    monkeypatch.setenv("CWS_TRUST_CLOUDFLARE_IP", "1")
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for index in range(5):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": f"not-an-ip-{index}"},
        )
        assert response.status_code == 401

    blocked_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "wrong-password"},
        headers={"CF-Connecting-IP": "still-not-an-ip"},
    )

    assert blocked_response.status_code == 429


def test_login_failure_sources_share_a_bounded_overflow_bucket(monkeypatch):
    from src.server import admin_auth as admin_auth_module

    _enable_admin_auth(monkeypatch)
    monkeypatch.setenv("CWS_TRUST_CLOUDFLARE_IP", "1")
    monkeypatch.setattr(
        admin_auth_module,
        "_LOGIN_FAILURE_SOURCE_LIMIT",
        3,
        raising=False,
    )
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for source_suffix in range(1, 8):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": f"203.0.113.{source_suffix}"},
        )
        assert response.status_code == 401

    blocked_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "wrong-password"},
        headers={"CF-Connecting-IP": "203.0.113.8"},
    )

    assert blocked_response.status_code == 429


def test_expired_login_failure_sources_are_removed_globally(monkeypatch):
    from src.server import admin_auth as admin_auth_module

    _enable_admin_auth(monkeypatch)
    monkeypatch.setenv("CWS_TRUST_CLOUDFLARE_IP", "1")
    monkeypatch.setattr(admin_auth_module, "_LOGIN_FAILURE_SOURCE_LIMIT", 3)
    monotonic_time = [0.0]
    monkeypatch.setattr(
        admin_auth_module.time,
        "monotonic",
        lambda: monotonic_time[0],
    )
    client = TestClient(
        create_app(lifespan=_lifespan),
        base_url="https://testserver",
    )

    for source_suffix in (1, 2):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": f"203.0.113.{source_suffix}"},
        )
        assert response.status_code == 401

    monotonic_time[0] = 301.0
    for _ in range(5):
        response = client.post(
            _AUTH_LOGIN_PATH,
            json={"password": "wrong-password"},
            headers={"CF-Connecting-IP": "203.0.113.3"},
        )
        assert response.status_code == 401

    fresh_source_response = client.post(
        _AUTH_LOGIN_PATH,
        json={"password": "wrong-password"},
        headers={"CF-Connecting-IP": "203.0.113.4"},
    )

    assert fresh_source_response.status_code == 401


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:53147",
        "http://127.0.0.1:49211",
        "https://localhost:9443",
    ],
)
def test_cors_allows_dynamic_localhost_port_by_default(monkeypatch, origin):
    monkeypatch.delenv("CWS_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("CWS_ADMIN_SESSION_SECRET", raising=False)
    monkeypatch.delenv("CWS_ALLOWED_ORIGINS", raising=False)
    client = TestClient(create_app(lifespan=_lifespan))

    response = client.options(
        "/api/v1/command/example",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_allows_configured_origin_and_rejects_unlisted_origin(monkeypatch):
    monkeypatch.delenv("CWS_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("CWS_ADMIN_SESSION_SECRET", raising=False)
    monkeypatch.setenv(
        "CWS_ALLOWED_ORIGINS",
        " https://world.ym0v0.com,https://admin.example.com,https://world.ym0v0.com ",
    )
    app = create_app(lifespan=_lifespan)
    client = TestClient(app, base_url="https://testserver")
    preflight_headers = {
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-CSRF-Token,Content-Type",
    }

    allowed_response = client.options(
        "/api/v1/command/example",
        headers={"Origin": "https://world.ym0v0.com", **preflight_headers},
    )
    denied_response = client.options(
        "/api/v1/command/example",
        headers={"Origin": "https://evil.example.com", **preflight_headers},
    )
    local_response = client.options(
        "/api/v1/command/example",
        headers={"Origin": "http://localhost:53147", **preflight_headers},
    )

    assert allowed_response.status_code == 200
    assert allowed_response.headers["access-control-allow-origin"] == "https://world.ym0v0.com"
    assert allowed_response.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in denied_response.headers
    assert "access-control-allow-origin" not in local_response.headers

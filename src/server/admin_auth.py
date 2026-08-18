from __future__ import annotations

import os
import time
from base64 import urlsafe_b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as new_hmac
from ipaddress import ip_address
from math import ceil
from secrets import token_urlsafe
from threading import Lock

from fastapi import APIRouter, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from src.server.services.public_api_contract import ok_response


_SESSION_COOKIE_NAME = "cws_admin_session"
_SESSION_TTL_SECONDS = 8 * 60 * 60
_SESSION_LIMIT = 64
_LOGIN_FAILURE_LIMIT = 5
_LOGIN_FAILURE_WINDOW_SECONDS = 5 * 60
_LOGIN_FAILURE_SOURCE_LIMIT = 256
_LOGIN_FAILURE_OVERFLOW_KEY = "overflow"
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}
_PLACEHOLDER_SECRET_PREFIXES = ("replace-with-", "change-me", "changeme")
_AUTH_SESSION_PATH = "/api/v1/query/auth/session"
_AUTH_LOGIN_PATH = "/api/v1/command/auth/login"
_AUTH_LOGOUT_PATH = "/api/v1/command/auth/logout"


def _env_flag(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in _FALSE_ENV_VALUES


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().casefold()
    return normalized.startswith(_PLACEHOLDER_SECRET_PREFIXES)


@dataclass(frozen=True, slots=True)
class _AdminAuthConfig:
    password: str
    session_secret: str
    cookie_secure: bool
    trust_cloudflare_ip: bool

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> "_AdminAuthConfig":
        password = environ.get("CWS_ADMIN_PASSWORD", "")
        session_secret = environ.get("CWS_ADMIN_SESSION_SECRET", "")
        if session_secret and not password:
            raise RuntimeError(
                "CWS_ADMIN_PASSWORD is required when "
                "CWS_ADMIN_SESSION_SECRET is configured"
            )
        if password and _is_placeholder_secret(password):
            raise RuntimeError(
                "CWS_ADMIN_PASSWORD must not use a documented placeholder value"
            )
        if session_secret and _is_placeholder_secret(session_secret):
            raise RuntimeError(
                "CWS_ADMIN_SESSION_SECRET must not use a documented placeholder value"
            )
        if password and len(password) < 12:
            raise RuntimeError(
                "CWS_ADMIN_PASSWORD must contain at least 12 characters when "
                "administrator authentication is enabled"
            )
        if password and len(session_secret) < 32:
            raise RuntimeError(
                "CWS_ADMIN_SESSION_SECRET must contain at least 32 characters "
                "when CWS_ADMIN_PASSWORD enables administrator authentication"
            )
        return cls(
            password=password,
            session_secret=session_secret,
            cookie_secure=_env_flag(
                environ.get("CWS_ADMIN_COOKIE_SECURE"),
                default=True,
            ),
            trust_cloudflare_ip=_env_flag(
                environ.get("CWS_TRUST_CLOUDFLARE_IP"),
                default=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class _AdminSession:
    session_id: str
    csrf_token: str
    expires_at: int


@dataclass(frozen=True, slots=True)
class _LoginAttemptResult:
    authenticated: bool
    retry_after: int = 0


class _AdminAuth:
    def __init__(self, config: _AdminAuthConfig):
        self._config = config
        self._sessions: dict[str, _AdminSession] = {}
        self._sessions_lock = Lock()
        self._login_failures: dict[str, list[float]] = {}
        self._login_failures_lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def anonymous_payload(self) -> dict[str, bool | str | None]:
        return {
            "enabled": self.enabled,
            "authenticated": False,
            "csrf_token": None,
        }

    def session_payload(self, session: _AdminSession) -> dict[str, bool | str | None]:
        return {
            "enabled": True,
            "authenticated": True,
            "csrf_token": session.csrf_token,
        }

    def create_session(self) -> _AdminSession:
        now = int(time.time())
        session = _AdminSession(
            session_id=token_urlsafe(32),
            csrf_token=token_urlsafe(32),
            expires_at=now + _SESSION_TTL_SECONDS,
        )
        with self._sessions_lock:
            self._remove_expired_sessions_locked(now)
            while len(self._sessions) >= _SESSION_LIMIT:
                earliest_expiring_session_id = min(
                    self._sessions.items(),
                    key=lambda item: item[1].expires_at,
                )[0]
                self._sessions.pop(earliest_expiring_session_id, None)
            self._sessions[session.session_id] = session
        return session

    def find_session(self, request: Request) -> _AdminSession | None:
        cookie_value = request.cookies.get(_SESSION_COOKIE_NAME)
        if not cookie_value:
            return None
        try:
            payload, supplied_signature = cookie_value.rsplit(".", 1)
            session_id, expires_text = payload.rsplit(".", 1)
            expires_at = int(expires_text)
        except (TypeError, ValueError):
            return None

        expected_signature = self._sign(payload)
        if not compare_digest(supplied_signature, expected_signature):
            return None

        now = int(time.time())
        with self._sessions_lock:
            if expires_at <= now:
                self._sessions.pop(session_id, None)
                return None
            session = self._sessions.get(session_id)
            if session is None or session.expires_at != expires_at:
                return None
            return session

    def login_response(self) -> JSONResponse:
        session = self.create_session()
        response = JSONResponse(
            ok_response(self.session_payload(session)),
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            key=_SESSION_COOKIE_NAME,
            value=self._cookie_value(session),
            max_age=_SESSION_TTL_SECONDS,
            httponly=True,
            secure=self._config.cookie_secure,
            samesite="strict",
            path="/",
        )
        return response

    def logout_response(self, request: Request) -> JSONResponse:
        session = self.find_session(request)
        if session is not None:
            with self._sessions_lock:
                self._sessions.pop(session.session_id, None)
        response = JSONResponse(
            ok_response(self.anonymous_payload()),
            headers={"Cache-Control": "no-store"},
        )
        response.delete_cookie(
            key=_SESSION_COOKIE_NAME,
            httponly=True,
            secure=self._config.cookie_secure,
            samesite="strict",
            path="/",
        )
        return response

    def password_matches(self, supplied_password: str) -> bool:
        return compare_digest(
            supplied_password.encode("utf-8"),
            self._config.password.encode("utf-8"),
        )

    def attempt_login(
        self,
        request: Request,
        supplied_password: str,
    ) -> _LoginAttemptResult:
        key = self._login_source_key(request)
        with self._login_failures_lock:
            now = time.monotonic()
            self._remove_expired_login_failures_locked(now)
            key = self._bounded_login_source_key_locked(key)
            recent = self._login_failures.get(key, [])
            if len(recent) >= _LOGIN_FAILURE_LIMIT:
                return _LoginAttemptResult(
                    authenticated=False,
                    retry_after=max(
                        1,
                        ceil(_LOGIN_FAILURE_WINDOW_SECONDS - (now - recent[0])),
                    ),
                )
            recent.append(now)
            self._login_failures[key] = recent

        authenticated = self.password_matches(supplied_password)
        if authenticated:
            with self._login_failures_lock:
                self._login_failures.pop(key, None)
        return _LoginAttemptResult(authenticated=authenticated)

    def _cookie_value(self, session: _AdminSession) -> str:
        payload = f"{session.session_id}.{session.expires_at}"
        return f"{payload}.{self._sign(payload)}"

    def _sign(self, payload: str) -> str:
        digest = new_hmac(
            self._config.session_secret.encode("utf-8"),
            payload.encode("utf-8"),
            sha256,
        ).digest()
        return urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _remove_expired_sessions_locked(self, now: int) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)

    def _login_source_key(self, request: Request) -> str:
        cloudflare_address = request.headers.get("CF-Connecting-IP", "").strip()
        if self._config.trust_cloudflare_ip and cloudflare_address:
            try:
                return f"cloudflare:{ip_address(cloudflare_address).compressed}"
            except ValueError:
                pass
        peer_address = request.client.host if request.client is not None else "unknown"
        return f"peer:{peer_address}"

    def _remove_expired_login_failures_locked(self, now: float) -> None:
        cutoff = now - _LOGIN_FAILURE_WINDOW_SECONDS
        for key, failures in list(self._login_failures.items()):
            recent = [failed_at for failed_at in failures if failed_at > cutoff]
            if recent:
                self._login_failures[key] = recent
            else:
                self._login_failures.pop(key, None)

    def _bounded_login_source_key_locked(self, key: str) -> str:
        if key in self._login_failures:
            return key
        regular_source_count = len(self._login_failures) - int(
            _LOGIN_FAILURE_OVERFLOW_KEY in self._login_failures
        )
        if regular_source_count >= max(0, _LOGIN_FAILURE_SOURCE_LIMIT - 1):
            return _LOGIN_FAILURE_OVERFLOW_KEY
        return key


class _LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


def _public_validation_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    return [
        {
            key: error[key]
            for key in ("type", "loc", "msg")
            if key in error
        }
        for error in exc.errors()
    ]


def _auth_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    response_headers = {"Cache-Control": "no-store"}
    if headers:
        response_headers.update(headers)
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        },
        headers=response_headers,
    )


class _AdminAuthMiddleware:
    def __init__(self, app, *, auth: _AdminAuth):
        self._app = app
        self._auth = auth

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        method = scope.get("method", "")
        normalized_path = path.rstrip("/")
        if (
            self._auth.enabled
            and scope["type"] == "http"
            and method != "OPTIONS"
            and (
                (
                    path.startswith("/api/v1/command/")
                    and normalized_path != _AUTH_LOGIN_PATH
                )
                or normalized_path == "/api/v1/query/saves"
                or normalized_path.startswith("/api/settings/llm")
                or (
                    (
                        normalized_path == "/api/settings"
                        or path.startswith("/api/settings/")
                    )
                    and method not in {"GET", "HEAD"}
                )
            )
        ):
            request = Request(scope)
            session = self._auth.find_session(request)
            if session is None:
                response = _auth_error(
                    status_code=401,
                    code="ADMIN_AUTH_REQUIRED",
                    message="Administrator authentication required",
                )
                await response(scope, receive, send)
                return
            if method not in {"GET", "HEAD"}:
                supplied_csrf = request.headers.get("X-CSRF-Token", "")
                if not supplied_csrf or not compare_digest(
                    supplied_csrf.encode("utf-8"),
                    session.csrf_token.encode("utf-8"),
                ):
                    response = _auth_error(
                        status_code=403,
                        code="ADMIN_CSRF_INVALID",
                        message="Valid CSRF token required",
                    )
                    await response(scope, receive, send)
                    return
        await self._app(scope, receive, send)


def install_admin_auth(
    app: FastAPI,
    *,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Install the administrator-authentication interface on a FastAPI app."""
    source = os.environ if environ is None else environ
    config = _AdminAuthConfig.from_environ(source)
    auth = _AdminAuth(config)
    router = APIRouter()

    app.add_middleware(_AdminAuthMiddleware, auth=auth)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ):
        if request.url.path.rstrip("/") == _AUTH_LOGIN_PATH:
            return _auth_error(
                status_code=422,
                code="ADMIN_LOGIN_REQUEST_INVALID",
                message="Administrator login request is invalid",
                details={"errors": _public_validation_errors(exc)},
                headers={"Cache-Control": "no-store"},
            )
        return await request_validation_exception_handler(request, exc)

    @router.get(_AUTH_SESSION_PATH)
    def get_auth_session(request: Request):
        session = auth.find_session(request)
        return JSONResponse(
            ok_response(
                auth.session_payload(session)
                if session is not None
                else auth.anonymous_payload()
            ),
            headers={"Cache-Control": "no-store"},
        )

    @router.post(_AUTH_LOGIN_PATH)
    def login(request: Request, req: _LoginRequest):
        if not auth.enabled:
            return JSONResponse(
                ok_response(auth.anonymous_payload()),
                headers={"Cache-Control": "no-store"},
            )
        attempt = auth.attempt_login(request, req.password)
        if attempt.retry_after:
            return _auth_error(
                status_code=429,
                code="ADMIN_LOGIN_RATE_LIMITED",
                message="Too many failed administrator login attempts",
                headers={"Retry-After": str(attempt.retry_after)},
            )
        if not attempt.authenticated:
            return _auth_error(
                status_code=401,
                code="ADMIN_LOGIN_INVALID",
                message="Invalid administrator credentials",
            )
        return auth.login_response()

    @router.post(_AUTH_LOGOUT_PATH)
    def logout(request: Request):
        return auth.logout_response(request)

    app.include_router(router)

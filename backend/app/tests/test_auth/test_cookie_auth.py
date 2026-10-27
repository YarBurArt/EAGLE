"""
Module for cookie (HttpOnly + SameSite) auth flows on top of the same JWT:
login sets both cookies, bearer-less access works, logout revokes + clears,
registration is closed by default
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession as SqlAsyncSession

from app.api.deps import ACCESS_COOKIE, REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.core import database_session
from app.core.config import get_settings
from app.core.database_session import new_async_engine
from app.core.security.password import get_password_hash
from app.main import app
from app.models import RefreshToken, User
from app.tests.conftest import default_user_email, default_user_password


def _login(client: AsyncClient, user: User):
    return client.post(
        app.url_path_for("login_access_token"),
        data={"username": user.email, "password": default_user_password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def _refresh(client: AsyncClient, token: str | None = None):
    """empty body -> backend takes the refresh cookie"""
    body = {"refresh_token": token} if token else None
    return client.post(app.url_path_for("refresh_token"), json=body)


@pytest.mark.asyncio(loop_scope="session")
async def test_login_sets_httponly_session_cookies(
    client: AsyncClient,
    default_user: User,
) -> None:
    response = await _login(client, default_user)

    assert response.status_code == status.HTTP_200_OK
    assert response.cookies.get(ACCESS_COOKIE)
    refresh_cookie = response.cookies.get(REFRESH_COOKIE)
    assert refresh_cookie
    # refresh cookie must not ride ordinary api calls
    assert any(c.path == REFRESH_COOKIE_PATH for c in response.cookies.jar)


@pytest.mark.asyncio(loop_scope="session")
async def test_cookie_only_access_works_without_bearer_header(
    client: AsyncClient,
    default_user: User,
) -> None:
    await _login(client, default_user)

    response = await client.get(app.url_path_for("read_current_user"))
    # no Authorization header was set anywhere, HttpOnly cookie did it
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["email"] == default_user_email


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_via_cookie_without_body(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    login = await _login(client, default_user)
    cookie_token = login.cookies.get(REFRESH_COOKIE)

    response = await _refresh(client)
    assert response.status_code == status.HTTP_200_OK
    # old token is rotated away (used), fresh one went back into the jar
    row = await session.scalar(
        select(RefreshToken).where(RefreshToken.refresh_token == cookie_token)
    )
    assert row is not None and row.used is True


@pytest.mark.asyncio(loop_scope="session")
async def test_reused_refresh_token_revokes_whole_family(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    login = await _login(client, default_user)
    stolen = login.cookies.get(REFRESH_COOKIE)
    await _refresh(client, stolen)  # legit rotation, stolen is dead now
    # a new login gives the user a second session with its own family row
    await _login(client, default_user)

    replay = await _refresh(client, stolen)
    # replayed rotated token -> 401 + every refresh token of the user dies
    assert replay.status_code == status.HTTP_401_UNAUTHORIZED
    count = await session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == default_user.user_id)
    )
    assert count == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_refreshes_with_same_token_allow_exactly_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """real parallel run: the conftest session is shared between requests and
    would serialize them with IllegalStateChangeError, and its rollback
    transaction hides uncommitted rows from any other connection, so this
    test builds its own engine, own user and per-request sessions"""

    engine = new_async_engine(get_settings().sqlalchemy_database_uri)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    email = "concurrent@test.local"

    async with maker() as s:
        s.add(
            User(
                email=email,
                username="concurrent",
                role="user",
                hashed_password=get_password_hash("geralt"),
            )
        )
        await s.commit()

    @asynccontextmanager
    async def own_session() -> AsyncGenerator[SqlAsyncSession]:
        session = maker()
        yield session
        await session.close()

    monkeypatch.setattr(database_session, "get_async_session", own_session)
    codes: list[int] = []
    try:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        async with client as own_client:
            login = await _login(
                own_client,
                User(email=email, hashed_password="", user_id="0"),
            )
            if login.status_code != status.HTTP_200_OK:
                codes = [login.status_code, login.status_code]
            else:
                token = login.cookies.get(REFRESH_COOKIE)
                first, second = await asyncio.gather(
                    _refresh(own_client, token),
                    _refresh(own_client, token),
                )
                codes = [first.status_code, second.status_code]
    finally:
        await engine.dispose()

    # FOR UPDATE SKIP LOCKED: one rotates, the other must not double-rotate
    codes = sorted(codes)
    assert codes.count(status.HTTP_200_OK) == 1
    assert codes[0] in (
        status.HTTP_200_OK,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_logout_revokes_refresh_and_clears_cookies(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    await _login(client, default_user)

    response = await client.post(app.url_path_for("logout"))
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.cookies.get(ACCESS_COOKIE) in (None, "")
    count = await session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == default_user.user_id)
    )
    assert count == 0
    # session is really gone
    after = await client.get(app.url_path_for("read_current_user"))
    assert after.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio(loop_scope="session")
async def test_registration_is_closed_by_default(
    client: AsyncClient,
    default_user: User,
    default_user_headers: dict[str, str],
) -> None:
    response = await client.post(
        app.url_path_for("register_new_user"),
        json={
            "email": "nobody@example.com",
            "password": "123",
            "role": "user",
            "username": "nobody",
        },
        headers=default_user_headers,
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

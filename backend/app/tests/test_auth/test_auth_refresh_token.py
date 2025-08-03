"""
Module for test jwt refresh token scenarios, their correct http response
in the context of a user one-time authentication
"""
import time

import pytest
from fastapi import status
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import api_messages
from app.core.config import get_settings
from app.main import app
from app.models import RefreshToken, User

from app.tests.test_auth.token_tests_helper import (
    check_refresh_token, check_token_expire_time,
    validate_token_response
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_fails_with_message_when_token_does_not_exist(
    client: AsyncClient,
) -> None:
    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": api_messages.REFRESH_TOKEN_NOT_FOUND}


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_fails_with_message_when_token_is_expired(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) - 1,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": api_messages.REFRESH_TOKEN_EXPIRED}


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_fails_with_message_when_token_is_used(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=True,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {
        "detail": api_messages.REFRESH_TOKEN_ALREADY_USED}


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_success_response_status_code(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_success_old_token_is_used(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    used_test_refresh_token = await session.scalar(
        select(RefreshToken).where(RefreshToken.refresh_token == "blaxx")
    )
    assert used_test_refresh_token is not None
    assert used_test_refresh_token.used


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_success_jwt_has_valid_token_type(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    token = response.json()
    assert token["token_type"] == "Bearer"


@pytest.mark.asyncio(loop_scope="session")
@freeze_time("2023-01-01")
async def test_refresh_token_success_jwt_has_valid_expire_time(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert check_token_expire_time(
        response.json(),
        get_settings().security.jwt_access_token_expire_secs, "expires_at")


@pytest.mark.asyncio(loop_scope="session")
@freeze_time("2023-01-01")
async def test_refresh_token_success_jwt_has_valid_access_token(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert validate_token_response(response.json(), default_user.user_id)


@pytest.mark.asyncio(loop_scope="session")
@freeze_time("2023-01-01")
async def test_refresh_token_success_refresh_token_has_valid_expire_time(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    assert check_token_expire_time(
        response.json(),
        get_settings().security.refresh_token_expire_secs,
        "refresh_token_expires_at")


@pytest.mark.asyncio(loop_scope="session")
async def test_refresh_token_success_new_refresh_token_is_in_db(
    client: AsyncClient,
    default_user: User,
    session: AsyncSession,
) -> None:
    test_refresh_token = RefreshToken(
        user_id=default_user.user_id,
        refresh_token="blaxx",
        exp=int(time.time()) + 1000,
        used=False,
    )
    session.add(test_refresh_token)
    await session.commit()

    response = await client.post(
        app.url_path_for("refresh_token"),
        json={
            "refresh_token": "blaxx",
        },
    )

    tdc = await check_refresh_token(response.json(), session)
    assert tdc

"""
Module for test registration scenarios
against the closed-registration state (bootstrap admin/roles later)
"""

import pytest
from fastapi import status
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio(loop_scope="session")
async def test_register_new_user_is_forbidden_by_default(
    client: AsyncClient,
    default_user_headers: dict[str, str],
) -> None:
    """registration is disabled: open self-registration plus a bash tool
    on the same box would be anyone-signs-up-owns-the-machine"""
    response = await client.post(
        app.url_path_for("register_new_user"),
        json={
            "email": "geralt@example.com",
            "password": "somepassword1",
            "role": "user",
            "username": "someuser",
        },
        headers=default_user_headers,
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio(loop_scope="session")
async def test_register_new_user_without_auth_token(
    client: AsyncClient,
) -> None:
    """even worse for anonymous, auth is checked before the gate"""
    response = await client.post(
        app.url_path_for("register_new_user"),
        json={
            "email": "nobody@example.com",
            "password": "1231",
            "role": "user",
            "username": "nobody",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

"""
module for general dependencies
like all authenticated endpoints need user session & id
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import api_messages
from app.core import database_session
from app.core.security.jwt import verify_jwt_token
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/access-token")


class ChainController:
    def __init__(self):
        self.active_chains: dict[int, asyncio.Event] = {}

    def cancel_chain(self, chain_id: int):
        if chain_id in self.active_chains:
            self.active_chains[chain_id].set()


async def get_session() -> AsyncGenerator[AsyncSession]:
    """get new database session by generator"""
    async with database_session.get_async_session() as session:
        yield session


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: AsyncSession = Depends(get_session),
) -> User:
    """get user from DB by jwt token"""
    token_payload = verify_jwt_token(token)

    query = select(User).where(User.user_id == token_payload.sub)
    user = await session.scalar(query)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=api_messages.JWT_ERROR_USER_REMOVED,
        )
    return user


def get_mythic_client(request: Request):
    """inject MythicClient from app.state"""
    from app.cmd.c2_tool import MythicClient  # noqa: PLC0415

    client = request.app.state.mythic_client
    assert isinstance(client, MythicClient)
    return client


def get_chain_controller(request: Request) -> ChainController:
    """inject ChainController from app.state"""
    controller = request.app.state.chain_controller
    assert isinstance(controller, ChainController)
    return controller

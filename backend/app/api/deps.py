"""
module for general dependencies
like all authenticated endpoints need user session & id
"""

import asyncio
import logging
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

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/access-token", auto_error=False)

# cookies hold the same JWT as the header
ACCESS_COOKIE = "eagle_at"
REFRESH_COOKIE = "eagle_rt"
# route-scoped, never rides an ordinary api call
REFRESH_COOKIE_PATH = "/api/auth/refresh-token"


class ChainController:
    def __init__(self):
        self.active_chains: dict[int, asyncio.Event] = {}

    def cancel_chain(self, chain_id: int):
        if chain_id in self.active_chains:
            self.active_chains[chain_id].set()
        # direct bash steps of this chain are running right now, kill them
        from app.cmd.local_bash import kill_chain  # noqa: PLC0415

        killed = kill_chain(chain_id)
        if killed:
            logging.getLogger(__name__).info(
                "chain %s cancel: killed %s bash process(es)", chain_id, killed
            )


async def get_session() -> AsyncGenerator[AsyncSession]:
    """get new database session by generator"""
    async with database_session.get_async_session() as session:
        yield session


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    """cookie first, header second, header stays for Swagger/scripts"""
    token = token or request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=api_messages.JWT_ERROR_USER_REMOVED,
        )
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
    if not isinstance(client, MythicClient):
        raise ValueError("cannot get Mythic client")
    return client


def get_events_service(request: Request):
    """inject MythicEventsService from app.state"""
    from app.cmd.mythic_events import MythicEventsService  # noqa: PLC0415

    service = request.app.state.events_service
    if not isinstance(service, MythicEventsService):
        raise ValueError("cannot get MythicEvents service")
    return service


def get_chain_controller(request: Request) -> ChainController:
    """inject ChainController from app.state"""
    controller = request.app.state.chain_controller
    if not isinstance(controller, ChainController):
        raise ValueError("cannot get ChainController")
    return controller

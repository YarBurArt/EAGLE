"""
Module for the general logic of token tests
"""
import time
from sqlalchemy import func, select

from app.models import RefreshToken
from app.core.security.jwt import verify_jwt_token


async def check_refresh_token(token, session) -> bool:
    """ token and from db is the same """
    token_db_count = await session.scalar(
        select(
            func.count()).where(
            RefreshToken.refresh_token == token["refresh_token"])
    )
    return token_db_count == 1


def check_token_expire_time(token, sec, place) -> bool:
    """ check for time parameters of tokens """
    current_timestamp = int(time.time())
    return token[place] == current_timestamp + sec


def validate_token_response(token, user_id) -> bool:
    """ check token verify response parameters """
    now = int(time.time())
    token_payload = verify_jwt_token(token["access_token"])

    return (
        token_payload.sub == user_id
        and token_payload.iat == now
        and token_payload.exp == token["expires_at"]
    )

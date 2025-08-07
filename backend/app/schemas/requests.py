"""
Module to defining requests types and format
"""
from pydantic import BaseModel, EmailStr


class BaseRequest(BaseModel):
    # may define additional fields or config shared across requests
    pass


class RefreshTokenRequest(BaseRequest):
    refresh_token: str


class UserUpdatePasswordRequest(BaseRequest):
    password: str


class UserCreateRequest(BaseRequest):
    email: EmailStr
    password: str
    role: str
    username: str


class NewChainRequest(BaseRequest):
    chain_name: str


class LocalCommandRequest(BaseRequest):
    chain_name: str
    phase: str
    callback_display_id: int
    command: str

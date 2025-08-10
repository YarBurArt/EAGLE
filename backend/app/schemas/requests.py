"""
Module to defining requests types and format
"""
from pydantic import BaseModel, EmailStr
from typing import Optional


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
    callback_display_id: int
    command: str


class ActionApprovalRequest(BaseModel):
    """Модель запроса для одобрения действий"""
    command: str
    agent_id: int
    chain_id: int
    phase: str
    approved_by: str
    reason: Optional[str] = ""


class ActionExecutionRequest(BaseModel):
    """Модель запроса для выполнения одобренных действий"""
    command: str
    agent_display_id: int
    chain_id: int
    phase: str
    approved_by: str
    context: Optional[str] = ""


class QueryRequest(BaseModel):
    prompt: str
    provider: Optional[str] = None


class CodeAnalysisRequest(BaseModel):
    code: str


class PayloadRequest(BaseModel):
    description: str
    language: Optional[str] = "python"

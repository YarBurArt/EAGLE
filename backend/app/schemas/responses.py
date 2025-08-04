"""
Module to defining responses types and format
"""
from pydantic import BaseModel, ConfigDict, EmailStr


class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccessTokenResponse(BaseResponse):
    token_type: str = "Bearer"
    access_token: str
    expires_at: int
    refresh_token: str
    refresh_token_expires_at: int


class UserResponse(BaseResponse):
    user_id: str
    email: EmailStr


class NewChainResponse(BaseResponse):
    chain_name: str
    current_phase_name: str


class GetChainPhaseResponse(BaseResponse):
    chain_id: int
    user_id: str
    chain_name: str
    username: str
    user_email: str
    final_status: str
    current_phase_name: str


class LocalCommandResponse(BaseResponse):
    user_id: str
    chain_name: str
    callback_display_id: int
    mythic_task_id: int
    tool_name: str
    command: str
    status: str
    raw_output: str

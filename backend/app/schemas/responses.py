"""
Module to defining responses types and format
"""

from typing import ClassVar

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr


class BaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AccessTokenResponse(BaseResponse):
    token_type: str = "Bearer"
    access_token: str
    expires_at: int
    refresh_token: str
    refresh_token_expires_at: int


class UserResponse(BaseResponse):
    user_id: UUID4
    email: EmailStr
    role: str | None = "user"
    username: str | None = "g3r4lt-w13dzm1n-pl"


class NewChainResponse(BaseResponse):
    chain_id: int
    chain_name: str
    current_phase_name: str


class NewPhaseResponse(BaseResponse):
    chain_id: int
    current_phase_name: str


class LocalCommandResponse(BaseResponse):
    user_id: UUID4
    chain_name: str
    callback_display_id: int
    mythic_task_id: int
    tool_name: str
    command: str
    status: str
    raw_output: str
    llm_analysis: str


class AttackStepResponse(BaseResponse):
    id: int | None
    chain_id: int | None
    phase: str
    tool_name: str
    command: str
    mythic_payload_uuid: str | UUID4
    status: str
    raw_log: str

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)


class GetChainPhaseResponse(BaseResponse):
    chain_id: int
    user_id: UUID4
    chain_name: str
    username: str | None = "g3r4lt-w13dzm1n-pl"
    user_email: str
    final_status: str
    current_phase_name: str
    last_attack_step: AttackStepResponse | None


class NewAgentResponse(BaseResponse):
    callback_display_id: int
    status: str
    os_type: str
    rhost: str


class NewPayloadResponse(BaseResponse):
    chain_id: int
    status: str
    phase: str
    payload_type: str | None  # based on os
    payload_uuid: str | UUID4
    payload_id: int | None
    download_url: str
    raw_log: str | None
    llm_analysis: str


# almost full from LLM
class SuggestActionResponse(BaseResponse):
    chain_id: int | None = 0
    agent_id: int | None = 0
    command: str | None = "whoami"
    phase: str | None = "Reconnaissance"
    target_os_type: str | None = None
    type_cmd: str | None = None
    type_tool: str | None = "whoami"

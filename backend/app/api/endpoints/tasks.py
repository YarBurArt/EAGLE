"""
Module for tasks endpoints, also might repeat tasks
based on chain id or commands and payloads from exported chain
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, StreamingResponse

from app.api import deps
from app.api.deps import ChainController, get_chain_controller
from app.models import User
from app.schemas.requests import (
    ActionApprovalRequest,
    ActionExecutionRequest,
    AgentCommandRequest,
    LocalCommandRequest,
    NewAgentRequest,
    NewChainRequest,
)
from app.schemas.responses import (
    AttackStepResponse,
    GetChainPhaseResponse,
    LocalCommandResponse,
    NewAgentResponse,
    NewChainResponse,
    NewPayloadResponse,
    NewPhaseResponse,
)
from app.services.c2_service import CommandsC2ExecService
from app.services.chain_exec_service import ChainExecutionService
from app.services.chain_service import ChainService
from app.services.payload_service import AgentPayloadService
from app.services.s_deps import (
    get_agent_payload_service,
    get_chain_execution_service,
    get_chain_service,
    get_command_service,
)

router = APIRouter()


@router.post(
    "/new-chain", description="Create new chain", response_model=NewChainResponse
)
async def create_new_chain(
    data: NewChainRequest,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
) -> NewChainResponse:
    chain_id, chain_name, phase = await chain_service.create_chain(
        data.chain_name, current_user
    )
    return NewChainResponse(
        chain_id=chain_id, chain_name=chain_name, current_phase_name=phase
    )


@router.post(
    "/run-command",
    description="Run shell command on zero agent",
    response_model=LocalCommandResponse,
)
async def run_local_command(
    data: LocalCommandRequest,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
    command_service: CommandsC2ExecService = Depends(get_command_service),
) -> LocalCommandResponse:
    chain_name, chain_id, phase_name = await chain_service.get_chain_n_phase(
        data.chain_name, current_user
    )
    result = await command_service.run_local_command(
        data.command, data.callback_display_id, chain_id, phase_name, current_user
    )
    return LocalCommandResponse(
        chain_name=chain_name,
        **result,
    )


@router.post(
    "/run-agent-command",
    description="Run agent command on remote agent like libinject",
    response_model=LocalCommandResponse,
)
async def run_agent_command(
    data: AgentCommandRequest,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
    command_service: CommandsC2ExecService = Depends(get_command_service),
) -> LocalCommandResponse:
    chain_name, chain_id, phase_name = await chain_service.get_chain_n_phase(
        data.chain_name, current_user
    )
    result = await command_service.run_agent_command(
        data.command_params or "",
        data.callback_display_id,
        data.tool or "shell",
        chain_id,
        phase_name,
        current_user,
    )
    return LocalCommandResponse(
        chain_name=chain_name,
        **result,
    )


@router.post(
    "/new-agent",
    description="Create new mythic agent payload, return download url",
    response_model=NewPayloadResponse,
)
async def new_agent(
    data: NewAgentRequest,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
    payload_service: AgentPayloadService = Depends(get_agent_payload_service),
) -> NewPayloadResponse:
    chain_name, chain_id, phase_name = await chain_service.get_chain_n_phase(
        data.chain_name, current_user
    )
    result = await payload_service.create_payload(
        chain_id, phase_name, data.payload_type, data.os_type
    )
    return NewPayloadResponse(**result)


@router.post(
    "/update-agents",
    description="Add agent to chain with save as AttackStep, Agent",
    response_model=NewAgentResponse,
)
async def update_agent(
    rhost: str,
    chain_name: str,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
    payload_service: AgentPayloadService = Depends(get_agent_payload_service),
) -> NewAgentResponse:
    _, chain_id, phase_name = await chain_service.get_chain_n_phase(
        chain_name, current_user
    )
    result = await payload_service.register_agent(rhost, chain_id, phase_name)
    return NewAgentResponse(**result)


@router.get(
    "/status/{display_id}", description="Get status of agent by callback_display_id"
)
async def read_agent_status(
    display_id: int,
    command_service: CommandsC2ExecService = Depends(get_command_service),
) -> str:
    return await command_service.get_agent_status(display_id)


@router.get(
    "/chain-phase/{chain_id}",
    description="Get chain info and UCKC phase, last attack step",
)
async def read_chain_info(
    chain_id: int,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
) -> GetChainPhaseResponse:
    info = await chain_service.read_chain_info(chain_id, current_user)
    last_step = info.pop("last_attack_step")
    return GetChainPhaseResponse(
        **info,
        last_attack_step=AttackStepResponse.from_orm(last_step) if last_step else None,
    )


@router.post(
    "/next-phase/{chain_id}",
    description="Switch to the next chain phase",
    response_model=NewPhaseResponse,
)
async def next_phase(
    chain_id: int,
    chain_service: ChainService = Depends(get_chain_service),
) -> NewPhaseResponse:
    c_id, phase = await chain_service.next_phase(chain_id)
    return NewPhaseResponse(chain_id=c_id, current_phase_name=phase)


@router.post(
    "/set-phase/{chain_id}",
    description="Switch to the specific chain phase",
    response_model=NewPhaseResponse,
)
async def set_phase(
    chain_id: int,
    phase_name: str,
    chain_service: ChainService = Depends(get_chain_service),
) -> NewPhaseResponse:
    c_id, phase = await chain_service.set_phase(chain_id, phase_name)
    return NewPhaseResponse(chain_id=c_id, current_phase_name=phase)


@router.post(
    "/reject-s/{chain_name}",
    description="Reject the last suggested step in the current chain",
    response_model=AttackStepResponse,
)
async def reject_last_step_or_cmd(
    chain_name: str,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
) -> AttackStepResponse:
    step = await chain_service.reject_last_step(chain_name, current_user)
    return AttackStepResponse.from_orm(step)


@router.post(
    "/run-chain/{chain_id}",
    description="Run attack chain from db by id",
)
async def run_chain(  # noqa: PLR0913, PLR0917
    chain_id: int,
    zero_display_id: int,
    current_user: User = Depends(deps.get_current_user),
    chain_service: ChainService = Depends(get_chain_service),
    chain_execution_service: ChainExecutionService = Depends(
        get_chain_execution_service
    ),
    chain_controller: ChainController = Depends(get_chain_controller),
) -> StreamingResponse:
    steps = await chain_service.get_chain_steps(chain_id)
    sorted_steps = chain_execution_service.get_sorted_steps(steps)
    cancel_event = asyncio.Event()
    chain_controller.active_chains[chain_id] = cancel_event
    return StreamingResponse(
        chain_execution_service.perform_chain_step(
            sorted_steps, zero_display_id, cancel_event
        ),
        media_type="application/json",
    )


@router.websocket("/ws/cancel-chain/{chain_id}")
async def cancel_chain_ws(
    websocket: WebSocket,
    chain_id: int,
    chain_service: ChainService = Depends(get_chain_service),
    chain_controller: ChainController = Depends(get_chain_controller),
) -> None:
    await websocket.accept()
    try:
        chain_name = await websocket.receive_text()
        verified = await chain_service.verify_chain_name(chain_id, chain_name)
        if verified:
            chain_controller.cancel_chain(chain_id)
    except WebSocketDisconnect:
        pass


@router.post("/cancel-chain/{chain_id}")
async def cancel_chain_a_http(
    chain_id: int,
    chain_name: str,
    chain_service: ChainService = Depends(get_chain_service),
    chain_controller: ChainController = Depends(get_chain_controller),
) -> JSONResponse:
    verified = await chain_service.verify_chain_name(chain_id, chain_name)
    if verified:
        chain_controller.cancel_chain(chain_id)
    return JSONResponse(content={"status": "canceled", "chain_name": chain_name})


@router.post("/approve-action")
async def approve_action_from_llm(
    action_request: ActionApprovalRequest,
    command_service: CommandsC2ExecService = Depends(get_command_service),
) -> dict[str, Any]:
    try:
        result = await command_service.approve_action(
            command=action_request.command,
            chain_id=action_request.chain_id,
            phase=action_request.phase,
            agent_id=action_request.agent_id,
            type_cmd=action_request.type_cmd,
            type_tool=action_request.type_tool,
            target_os_type=action_request.target_os_type,
        )
        return {
            "success": True,
            "attack_step": result["attack_step"],
            "llm_analysis": result["llm_analysis"],
            "message": "Action executed and saved successfully",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error executing approved action: {str(e)}"
        ) from e


@router.post("/api/llm/action/execute")
async def execute_approved_action(
    action_request: ActionExecutionRequest,
    command_service: CommandsC2ExecService = Depends(get_command_service),
) -> dict[str, Any]:
    try:
        if not action_request.command:
            raise HTTPException(status_code=400, detail="Command is required")
        result = await command_service.execute_approved_action(
            command=action_request.command,
            agent_display_id=action_request.agent_display_id,
            chain_id=action_request.chain_id,
            phase=action_request.phase,
        )
        return {
            "success": True,
            "attack_step": result["attack_step"],
            "message": "Action executed and saved to AttackStep successfully",
            "llm analysis": str(result["llm_analysis"]),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to execute approved action: {str(e)}"
        ) from e

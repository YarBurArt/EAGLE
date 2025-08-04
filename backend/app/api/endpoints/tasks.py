"""
Module for tasks endpoints, also might repeat tasks
based on chain id or commands and payloads from exported chain
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models import (
    User, AttackChain, AttackStep, CurrentAttackPhase
)
from app.schemas.requests import (
    NewChainRequest, LocalCommandRequest
)
from app.schemas.responses import (
    LocalCommandResponse, NewChainResponse, GetChainPhaseResponse
)
from app.cmd.proc import check_and_process_local_cmd, get_agent_status

router = APIRouter()


@router.post(
    "/new-chain",
    description="Create new chain",
    response_model=NewChainResponse
)
async def create_new_chain(
    data: NewChainRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> NewChainResponse:
    """ post endpoint for create chain just by name """
    chain = AttackChain(
        user_id=current_user.user_id,
        chain_name=data.chain_name,
        final_status="execution"
    )
    session.add(chain)
    # keep track of the current in DB for stability
    c_phase = CurrentAttackPhase(
        chain_id=chain.id,
        phase="Reconnaissance"
    )
    session.add(c_phase)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return NewChainResponse(
        chain_id=chain.id,
        chain_name=chain.chain_name,
        current_phase_name=c_phase.phase
    )


@router.post(
    "/run-command",
    description="Run command on zero agent",
    response_model=LocalCommandResponse
)
async def run_local_command(
    data: LocalCommandRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> LocalCommandResponse:
    """ post endpoint that get chain -> run command ->
        save as AttackStep with chain id, combine and return with log """
    # get chain by user_id from get_current_user and chain_name
    chain_ca: AttackChain = await session.execute(
        select(AttackChain).where(
            AttackChain.user_id == current_user.user_id,
            AttackChain.chain_name == data.chain_name
        )
    )
    chain_c = chain_ca.scalars().first()  # get first object of select
    # zero agent must be already deployed, thats why we need display id
    step: AttackStep = await check_and_process_local_cmd(
        data.command, data.callback_display_id, chain_c.id)
    # add attack step with phase
    session.add(step)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()

    return LocalCommandResponse(
        user_id=current_user.user_id,
        chain_name=chain_c.chain_name,
        callback_display_id=data.callback_display_id,
        mythic_task_id=step.mythic_task_id,
        tool_name=step.tool_name,
        command=step.command,
        status=step.status,
        raw_output=step.raw_log
    )


@router.get(
    "/status/{display_id}",
    description="Get status of agent by callback_display_id"
)
async def read_agent_status(
    display_id: int,
    current_user: User = Depends(deps.get_current_user),
) -> str:
    """ just get status of agent callback """
    status = await get_agent_status(display_id)
    return status


@router.get(
    "/chain-phase/{chain_id}",
    description="Get chain info and UCKC phase"
)
async def read_chain_info(
    chain_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> GetChainPhaseResponse:
    """ just get status of agent callback """
    chain_ca: AttackChain = await session.execute(
        select(AttackChain).where(
            AttackChain.id == chain_id,
            AttackChain.user_id == current_user.user_id
        )  # can see only own chain
    )
    chain_username = current_user.username or f"user#{chain_id}"
    chain_c_phase: CurrentAttackPhase = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_ca.id
        )
    )
    return GetChainPhaseResponse(
        chain_id=chain_ca.id,
        user_id=chain_ca.user_id,
        chain_name=chain_ca.chain_name,
        username=chain_username,
        user_email=current_user.email,
        final_status=chain_ca.final_status,
        current_phase_name=chain_c_phase.phase
    )

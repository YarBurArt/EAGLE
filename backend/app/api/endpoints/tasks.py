from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security.password import get_password_hash
from app.models import User, AttackChain, AttackStep, Agent
from app.schemas.requests import (
    NewChainRequest, LocalCommandRequest
)
from app.schemas.responses import LocalCommandResponse

from app.cmd.proc import check_and_process_local_cmd

router = APIRouter()


@router.post(
    "/new-chain",
    description="Create new chain",
)
async def create_new_chain(
    data: NewChainRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> str:
    chain = AttackChain(
        user_id=current_user.user_id,
        chain_name=data.chain_name,
        final_status="execution"
    )
    session.add(chain)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return data.chain_name


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

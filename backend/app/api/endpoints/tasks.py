"""
Module for tasks endpoints, also might repeat tasks
based on chain id or commands and payloads from exported chain
"""
from typing import List, Dict, Any

import g4f  # temp
from fastapi import (
    APIRouter, Depends, HTTPException, status, Request
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.cmd.llm_analysis import (
    llm_service, PayloadRequest, QueryRequest, CodeAnalysisRequest
)
from app.api import deps
from app.models import (
    User, AttackChain, AttackStep, CurrentAttackPhase
)
from app.schemas.requests import (
    NewChainRequest, LocalCommandRequest
)
from app.schemas.responses import (
    LocalCommandResponse, NewChainResponse, GetChainPhaseResponse,
    NewPhaseResponse
)
from app.cmd.proc import check_and_process_local_cmd, get_agent_status, phases


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
    await session.commit()  # otherwise there will be no id
    # keep track of the current in DB for stability
    c_phase = CurrentAttackPhase(
        chain_id=chain.id,
        phase=phases[0]  # start with recon
    )
    session.add(c_phase)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

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
    chain_ca: List[AttackChain] = await session.execute(
        select(AttackChain).where(
            AttackChain.user_id == current_user.user_id,
            AttackChain.chain_name == data.chain_name
        )
    )
    # get first object of select
    chain_c: AttackChain = chain_ca.scalars().first()
    phase_name: str = chain_c.current_phase.phase or "Reconnaissance"
    # zero agent must be already deployed, thats why we need display id
    step: AttackStep = await check_and_process_local_cmd(
        data.command, data.callback_display_id, chain_c.id, phase_name)
    # add attack step with phase
    session.add(step)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

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
    status_agent = await get_agent_status(display_id)
    return status_agent


@router.get(
    "/chain-phase/{chain_id}",
    description="Get chain info and UCKC phase"
)
async def read_chain_info(
    chain_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> GetChainPhaseResponse:
    """ get full info about chain phase """
    chain_ca_list: List[AttackChain] = await session.execute(
        select(AttackChain).where(
            AttackChain.id == chain_id,
        )
    )
    chain_ca: AttackChain = chain_ca_list.scalars().first()
    await session.commit()
    chain_username = current_user.username or f"user#{chain_id}"
    chain_c_phase_list: List[CurrentAttackPhase] = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_ca.id
        )
    )
    chain_c_phase = chain_c_phase_list.scalars().first()
    current_phase_n = chain_c_phase.phase or "Reconnaissance"
    return GetChainPhaseResponse(
        chain_id=chain_ca.id,
        user_id=chain_ca.user_id,
        chain_name=chain_ca.chain_name,
        username=chain_username,
        user_email=current_user.email,
        final_status=chain_ca.final_status,
        current_phase_name=current_phase_n
    )


@router.post(
    "/next-phase/{chain_id}",
    description="Switch to the next chain phase",
    response_model=NewPhaseResponse
)
async def next_phase(
    chain_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> NewPhaseResponse:
    """ switch to next by UCKC phases list """
    res_phase: List[CurrentAttackPhase] = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_id
        )
    )
    # users should only know the numbers of their chains
    c_phase: CurrentAttackPhase = res_phase.scalars().first()
    try:
        idx = phases.index(c_phase.phase)  # from proc or config
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Unknown phase, check UCKC phases"
        ) from exc
    if idx + 1 >= len(phases):
        raise HTTPException(
            status_code=400,
            detail="Already last phase, try to find a way to save the chain."
        )
    c_phase.phase = phases[idx + 1]  # temp: by tuple plus 1
    # already check exceptions
    await session.commit()
    return NewPhaseResponse(
        chain_id=c_phase.chain_id,
        current_phase_name=c_phase.phase
    )


@router.post(
    "/set-phase/{chain_id}",
    description="Switch to the specific chain phase",
    response_model=NewPhaseResponse
)
async def set_phase(
    chain_id: int,
    phase_name: str,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> NewPhaseResponse:
    """ switch to the specific phase in UCKC phases list """
    if phase_name not in phases:
        raise HTTPException(
            status_code=400,
            detail="Unknown phase, check UCKC phases"
        )
    # check by id for phase in chain
    res_phase: List[CurrentAttackPhase] = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_id
        )
    )
    c_phase: CurrentAttackPhase = res_phase.scalars().first()
    if not c_phase:
        # add if no current phase
        c_phase = CurrentAttackPhase(chain_id=chain_id, phase=phase_name)
        session.add(c_phase)
    else:
        # or just switch the phase
        c_phase.phase = phase_name
    await session.commit()
    return NewPhaseResponse(
        chain_id=c_phase.chain_id,
        current_phase_name=c_phase.phase
    )


@router.post("/api/llm/query")
async def llm_query(request: QueryRequest):
    """
    Основной эндпоинт для запросов к LLM
    """
    try:
        result = await llm_service.query_llm(request.prompt, request.provider)
        return {
            "success": True,
            "response": result,
            "prompt": request.prompt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/llm/analyze/code")
async def analyze_code(request: CodeAnalysisRequest):
    """
    Анализирует код с помощью LLM
    """
    try:
        prompt = f"analyze this code and explain it to me\n\n{request.code}"
        result = await llm_service.query_llm(prompt)
        return {
            "success": True,
            "analysis": result,
            "code": request.code
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error code analysis {str(e)}")


@router.post("/api/llm/generate/payload")
async def generate_payload(request: PayloadRequest):
    """
    Генерирует пейлоады для penetration testing
    """
    try:
        prompt = f"Create {request.language} script for learning purposes:\n{request.description}"
        result = await llm_service.query_llm(prompt)
        return {
            "success": True,
            "payload": result,
            "language": request.language,
            "description": request.description
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"generation error: {str(e)}"
        ) from e


@router.get("/api/llm/providers")
async def get_providers():
    """
    Возвращает список доступных провайдеров
    """
    try:
        providers_list = []
        for name, provider in llm_service.providers.items():
            providers_list.append({
                "name": name,
                "class": provider.__name__
            })
        return {
            "success": True,
            "providers": providers_list
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"error retrieving provider: {str(e)}"
        ) from e


@router.post("/api/llm/chat")
async def chat_conversation(messages: Dict[str, Any]):
    """
    Эндпоинт для ведения диалога
    """
    try:
        chat_messages = messages.get("messages", [])
        if not chat_messages:
            raise HTTPException(status_code=400, detail="message massive needed")

        for name, provider in llm_service.providers.items():
            try:
                response = await g4f.ChatCompletion.create_async(
                    model=g4f.models.default,
                    messages=chat_messages,
                    provider=provider
                )
                if response and len(response) > 0:
                    return {
                        "success": True,
                        "response": response,
                        "provider": name
                    }
            except Exception as e:
                print(f"Provider {name} failed: {e}")
                continue

        raise HTTPException(status_code=500, detail="no response from providers")

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"dialog error: {str(e)}"
        ) from e  # to track traceback


# @router.add_middleware("http") FIXME: middleware to main
async def log_requests_body(request: Request, call_next):
    print(f"query: {request.method} {request.url}")
    try:
        body = await request.body()
        if body:
            print(f"request body: {body.decode()}")
    except Exception:
        pass

    response = await call_next(request)
    return response

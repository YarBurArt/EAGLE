"""
Module for tasks endpoints, also might repeat tasks
based on chain id or commands and payloads from exported chain
"""
import os
import json
import asyncio
from typing import List, Tuple, Dict
from dotenv import load_dotenv

from fastapi import (
    APIRouter, Depends, HTTPException, status, Request,
    WebSocket, WebSocketDisconnect
)
from fastapi.responses import StreamingResponse, JSONResponse
from app.core.llm_templ import LLMTemplates
from sqlalchemy import select, desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmd.c2_tool import execute_local_command
from app.cmd.llm_analysis import llm_service
from app.api import deps
from app.core.config import phases
from app.models import (
    User, AttackChain, AttackStep, CurrentAttackPhase, Agent
)
from app.schemas.requests import (
    NewChainRequest, LocalCommandRequest,
    ActionApprovalRequest, ActionExecutionRequest,
    PayloadRequest, AgentCommandRequest, NewAgentRequest
)
from app.schemas.responses import (
    LocalCommandResponse, NewChainResponse, GetChainPhaseResponse,
    NewPhaseResponse, NewAgentResponse, AttackStepResponse,
    NewPayloadResponse
)
from app.cmd.proc import (
    check_and_process_local_cmd, get_agent_status,
    analyze_command_output_with_llm, process_approved_cmd,
    check_and_process_agent_cmd, process_new_callback,
    check_and_create_mpayload
)


load_dotenv()
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


async def get_chain_n_phase(
    session: AsyncSession, chain_name: str, current_user: User
) -> Tuple[str, int, str]:
    """ get chain name and current phase name from db by id """
    # get chain by user_id from get_current_user and chain_name
    chain_ca: List[AttackChain] = await session.execute(
        select(AttackChain).where(
            AttackChain.user_id == current_user.user_id,
            AttackChain.chain_name == chain_name
        )
    )
    # get first object of select
    chain_c: AttackChain = chain_ca.scalars().first()
    c_phase = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_c.id
        )
    )
    phase_name_ob: CurrentAttackPhase = c_phase.scalars().first()
    phase_name: str = str(phase_name_ob.phase) or "Reconnaissance"
    return chain_c.chain_name, chain_c.id, phase_name


@router.post(
    "/run-command",
    description="Run shell command on zero agent",
    response_model=LocalCommandResponse
)
async def run_local_command(
    data: LocalCommandRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> LocalCommandResponse:
    """ post endpoint that get chain -> run command ->
        save as AttackStep with chain id, combine and return with log """
    chain_name, chain_id, phase_name = await get_chain_n_phase(
        session, data.chain_name, current_user
    )
    # zero agent must be already deployed, thats why we need display id
    step, llm_a = await check_and_process_local_cmd(
        data.command, data.callback_display_id, chain_id, phase_name)
    # add attack step with phase
    session.add(step)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    # FIXME: for long time response
    return LocalCommandResponse(
        user_id=current_user.user_id,
        chain_name=chain_name,
        callback_display_id=data.callback_display_id,
        mythic_task_id=step.mythic_task_id,
        tool_name=step.tool_name,
        command=step.command,
        status=step.status,
        raw_output=step.raw_log,
        llm_analysis=llm_a
    )


@router.post(
    "/run-agent-command",
    description="Run agent command on remote agent like libinject",
    response_model=LocalCommandResponse
)
async def run_agent_command(
    data: AgentCommandRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> LocalCommandResponse:
    """ post endpoint that get chain/phase -> run command on agent ->
        save as AttackStep with chain id, combine and return with log """
    chain_name, chain_id, phase_name = await get_chain_n_phase(
        session, data.chain_name, current_user
    )
    # FIXME: display_id from rhost Agent
    step, llm_a, c_agent = await check_and_process_agent_cmd(
        data.callback_display_id, chain_id, data.command,
        'agent_' + data.tool, data.tool, phase_name)
    # add attack step with phase
    session.add(step)
    try:
        await session.commit()
        c_agent.step_id = step.id  # test me
        session.add(c_agent)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    return LocalCommandResponse(  # temp
        user_id=current_user.user_id,
        chain_name=chain_name,
        callback_display_id=data.callback_display_id,
        mythic_task_id=step.mythic_task_id,
        tool_name=step.tool_name,   # already agent_ cuz from AttackStep
        command=step.command,
        status=step.status,
        raw_output=step.raw_log,
        llm_analysis=llm_a
    )


@router.post(
    "/new-agent",
    description="Create new mythic agent payload, return download url",
    response_model=NewPayloadResponse
)
async def new_agent(
    data: NewAgentRequest,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> NewPayloadResponse:
    """ create new payload C2, save to mythic, return download url """
    chain_name, chain_id, phase_name = await get_chain_n_phase(
        session, data.chain_name, current_user
    )
    # None as string for step reproducibility via process_approved_cmd
    p_type = "None" if data.payload_type is None else str(data.payload_type)
    tool_name = "payload_" + p_type
    payload_step, llm_a = await check_and_create_mpayload(
        chain_id=chain_id, tool_name=tool_name, tool_n=p_type,
        p_lport=-1,  # set as default from .env
        p_os_type=data.os_type
    )
    session.add(payload_step)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    # like https://10.2:7443/direct/download
    #             /95917999-2eff-478c-b71a-6a81e2a83383
    ip = os.getenv('MYTHIC__SERVER_IP')
    port = os.getenv('MYTHIC__SERVER_PORT')
    uuid = payload_step.mythic_payload_uuid
    p_download_url = f"https://{ip}:{port}/direct/download/{uuid}"

    return NewPayloadResponse(
        chain_id=chain_id, status=payload_step.status,
        phase=payload_step.phase, download_url=p_download_url,
        payload_uuid=uuid, payload_id=payload_step.mythic_payload_id,
        raw_log=payload_step.raw_log, llm_analysis=llm_a,
        payload_type=payload_step.tool_name,  # TODO: fix to default types
    )


@router.post(
    "/update-agents",
    description="Add agent to chain with save as AttackStep, Agent",
    response_model=NewAgentResponse
)
async def update_agent(
    rhost: str,
    chain_name: str,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> NewAgentResponse:
    """ you run new agent with RCE, by this save to DB """
    chain_name, chain_id, phase_name = await get_chain_n_phase(
        session, chain_name, current_user
    )
    chain_steps_list = await session.execute(
        select(AttackStep).where(
            AttackStep.chain_id == chain_id,
        ))
    # we suppose that the previous step was run payload
    chain_steps_l_ca: List[AttackStep] = chain_steps_list.scalars().all()
    last_step = max(
        chain_steps_l_ca,
        key=lambda step: step.update_time
    )
    res: Tuple[AttackStep, Agent] = await process_new_callback(
        chain_id=chain_id, tool_name="getcallback_get_agent_callback_after",
        cmd=rhost, phase_name=phase_name, parent_step_id=last_step.id
    )
    get_callback_step, new_agent = res
    session.add(get_callback_step)
    session.add(new_agent)  # TODO: connect by p step id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    return NewAgentResponse(
        os_type=new_agent.os_type,
        rhost=rhost,
        status=new_agent.status,
        callback_display_id=new_agent.callback_display_id
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
    description="Get chain info and UCKC phase, last attack step"
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
    chain_username = (
        current_user.username or current_user.email.split("@", 1)[0]
    )
    chain_c_phase_list: List[CurrentAttackPhase] = await session.execute(
        select(CurrentAttackPhase).where(
            CurrentAttackPhase.chain_id == chain_ca.id
        )
    )
    chain_c_phase = chain_c_phase_list.scalars().first()
    current_phase_n = chain_c_phase.phase or "Reconnaissance"
    res_l_step = await session.execute(
        select(AttackStep).where(
            AttackStep.chain_id == chain_id
        ).order_by(
            desc(AttackStep.update_time)
        ).limit(1)
    )
    # first because order by
    last_attack_step_r: AttackStep = res_l_step.scalars().first()
    last_attack_step = AttackStepResponse.from_orm(last_attack_step_r)
    return GetChainPhaseResponse(
        chain_id=chain_ca.id,
        user_id=chain_ca.user_id,
        chain_name=chain_ca.chain_name,
        username=chain_username,
        user_email=current_user.email,
        final_status=chain_ca.final_status,
        current_phase_name=current_phase_n,
        last_attack_step=last_attack_step
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


class ChainController:
    def __init__(self):
        self.active_chains = {}

    def cancel_chain(self, chain_id: int):
        if chain_id in self.active_chains:
            # stop by asyncio.Event()
            self.active_chains[chain_id].set()


chain_controller = ChainController()


async def perform_chain_step(
    steps: List[AttackStep], zero_display_id: int,
    session: AsyncSession, cancel_event: asyncio.Event
) -> Dict:
    """ generator to yield result of each step """
    for step in steps:
        if cancel_event.is_set():  # check asyncio.Event status
            print("\nINFO [-] chain is cancel\n")
            break
        res_agent = await session.execute(
            select(Agent).where(
                Agent.step_id == step.id
            )
        )
        c_agent: Agent = res_agent.scalars().first()
        if c_agent:
            display_id = c_agent.callback_display_id
            p_os_type = c_agent.os_type
        else:
            display_id = zero_display_id
            p_os_type = "Windows"  # cuz most popular target
        # _ is new agent what we dont need
        result, llm_a, _ = await process_approved_cmd(
            cmd=step.command, chain_id=step.chain_id,
            tool_name=step.tool_name, phase_name=step.phase,
            display_id=display_id,
            p_os_type=p_os_type
        )  # temp
        resp_step = {
            "step_id": result.id,
            "chain_id": result.chain_id,
            "phase": result.phase,
            "tool_name": result.tool_name,
            "mythic_payload_uuid": result.mythic_payload_uuid,
            "status": result.status,
            "raw_log": result.raw_log,
            "command": result.command
        }
        out_d = {
            # result.model_dump() -> pydantic issue #6554
            "AttackStep": resp_step,
            "LLM_analysis": llm_a
        }
        # back to StreamingResponse
        yield json.dumps(out_d, default=str) + "\n"


@router.post(
    "/run-chain/{chain_id}",
    description="Run attack chain from db by id",
)
async def run_chain(
    chain_id: int,
    zero_display_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
) -> StreamingResponse:
    """ executes commands via proc in order of time """
    global chain_controller  # FIXME
    chain_steps_list = await session.execute(
        select(AttackStep).where(
            AttackStep.chain_id == chain_id,
        )
    )
    chain_steps_l_ca: List[AttackStep] = chain_steps_list.scalars().all()
    # generate list of successed steps and filter by last update_time
    f_sorted_steps = sorted(  # TODO: that's slower that via SQLalchemy
        (i for i in chain_steps_l_ca if i.status == "success"),
        key=lambda step: step.update_time
    )
    # to interrupt globally specific chain
    cancel_event = asyncio.Event()
    chain_controller.active_chains[chain_id] = cancel_event
    return StreamingResponse(
        perform_chain_step(
            f_sorted_steps, zero_display_id, session, cancel_event
        ),
        media_type="application/json"
    )


@router.websocket("/ws/cancel-chain/{chain_id}")
async def cancel_chain_ws(
    websocket: WebSocket, chain_id: int,
    session: AsyncSession = Depends(deps.get_session),
    current_user: User = Depends(deps.get_current_user),
):
    global chain_controller  # FIXME
    await websocket.accept()
    try:
        chain_name = await websocket.receive_text()
        chain_ca_list: List[AttackChain] = await session.execute(
            select(AttackChain).where(
                AttackChain.id == chain_id,
            )
        )
        chain_ca: AttackChain = chain_ca_list.scalars().first()
        print(chain_name)
        if chain_name == chain_ca.chain_name:
            # cancel chain via global chain controller
            chain_controller.cancel_chain(chain_id)
    except WebSocketDisconnect:
        pass


@router.post("/cancel-chain/{chain_id}")
async def cancel_chain_a_http(
    chain_id: int, chain_name,
    session: AsyncSession = Depends(deps.get_session)
):
    global chain_controller  # FIXME
    chain_ca_list: List[AttackChain] = await session.execute(
        select(AttackChain).where(
            AttackChain.id == chain_id,
        )
    )
    chain_ca: AttackChain = chain_ca_list.scalars().first()
    print(chain_name)
    if chain_name == chain_ca.chain_name:
        # cancel chain via global chain controller
        chain_controller.cancel_chain(chain_id)

    return JSONResponse(content={
        "status": "canceled",
        "chain_name": chain_name
    })


@router.post("/api/llm/generate/payload")
async def generate_payload(request: PayloadRequest):
    """
    Генерирует пейлоады для penetration testing
    """
    try:
        # Используем шаблон из конфигурации
        prompt = LLMTemplates.PAYLOAD_GENERATION.format(
            language=request.language,
            description=request.description
        )
        result = await llm_service.query_llm(prompt)

        # Используем шаблон для генерации команд
        commands_prompt = LLMTemplates.COMMANDS_GENERATION.format(
            language=request.language,
            script=result
        )

        commands_result = await llm_service.query_llm(commands_prompt)

        # Пытаемся распарсить команды
        try:
            import json
            commands_data = json.loads(commands_result)
        except json.JSONDecodeError:
            commands_data = {
                "setup_commands": [],
                "execution_commands": [],
                "verification_commands": [],
                "cleanup_commands": []
            }

        return {
            "success": True,
            "payload": result,
            "commands": commands_data,
            "language": request.language,
            "description": request.description
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"generation error: {str(e)}"
        ) from e


@router.post("/api/llm/action/approve")
async def approve_action(
    action_request: ActionApprovalRequest,
    session: AsyncSession = Depends(deps.get_session)
):
    """
    Endpoint for approved actions and execution with saving to AttackStep
    """
    try:
        # Execute the approved action
        result = await process_approved_cmd(
            cmd=action_request.command,
            chain_id=action_request.chain_id,
            tool_name=f"local_{action_request.command.split()[0]}",
            display_id=action_request.agent_id,
            phase_name=action_request.phase
        )

        if hasattr(result, '__await__'):
            attack_step, llm_analysis = await result
        else:
            attack_step, llm_analysis = result

        # Update the existing attack_step with LLM analysis
        attack_step.llm_analysis = llm_analysis
        attack_step.status = "success"

        # Add to session and commit
        session.add(attack_step)
        try:
            # Обновляем объект после сохранения
            await session.commit()
            await session.refresh(attack_step)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=400,
                detail="Database integrity error"
            ) from exc

        return {
            "success": True,
            "attack_step": attack_step,
            "llm_analysis": llm_analysis,
            "message": "Action executed and saved successfully"
        }

    except Exception as e:
        # no need to save to AttackStep, only crit errors for 500
        raise HTTPException(
            status_code=500,
            detail=f"Error executing approved action: {str(e)}"
        ) from e


@router.post("/api/llm/action/execute")
async def execute_approved_action(action_request: ActionExecutionRequest):
    """
    Endpoint for executing approved actions with results saving
    """
    try:
        # Validate request
        if not action_request.command:
            raise HTTPException(
                status_code=400,
                detail="Command is required"
            )
        # Execute command on agent
        res: Tuple = await execute_local_command(
            action_request.command,
            action_request.agent_display_id
        )
        output, mythic_task_id, mythic_payload_id, mythic_payload_uuid = res
        # Analyze output with LLM
        llm_analysis_result: str = await analyze_command_output_with_llm(
            action_request.command,
            output
        )

        # Create AttackStep object
        attack_step = AttackStep(
            chain_id=action_request.chain_id,
            phase=action_request.phase,
            tool_name=action_request.command.split()[0],
            command=action_request.command,
            mythic_task_id="",
            mythic_payload_uuid="",
            mythic_payload_id="",
            raw_log=output,
            status="success"
        )
        return {
            "success": True,
            "attack_step": attack_step,
            "message": "Action executed and saved to AttackStep successfully",
            "llm analysis": str(llm_analysis_result)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute approved action: {str(e)}"
        ) from e


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

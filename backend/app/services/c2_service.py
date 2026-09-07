from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmd.c2_tool import MythicClient
from app.cmd.proc import (
    CallbackInfo,
    ChainContext,
    PayloadParams,
    analyze_command_output_with_llm,
    check_and_process_agent_cmd,
    check_and_process_local_cmd,
    get_agent_status,
    process_approved_cmd,
)
from app.models import AttackStep, User


class CommandsC2ExecService:
    def __init__(self, session: AsyncSession, mythic_client: MythicClient) -> None:
        self.session = session
        self.mythic_client = mythic_client

    async def run_local_command(  # noqa: PLR0913, PLR0917
        self,
        command: str,
        display_id: int,
        chain_id: int,
        phase_name: str,
        current_user: User,
        no_llm_analysis: bool = False,
    ) -> dict[str, Any]:
        """execute bash/C2 command via local agent"""
        ctx = ChainContext(chain_id=chain_id, phase_name=phase_name)
        step, llm_a = await check_and_process_local_cmd(
            command, display_id, ctx, self.mythic_client, no_llm_analysis
        )
        self.session.add(step)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=400) from exc
        return {
            "user_id": current_user.user_id,
            "callback_display_id": display_id,
            "mythic_task_id": step.mythic_task_id,
            "tool_name": step.tool_name,
            "command": step.command,
            "status": step.status,
            "raw_output": step.raw_log,
            "llm_analysis": llm_a,
        }

    async def run_agent_command(  # noqa: PLR0913, PLR0917
        self,
        command_params: str,
        display_id: int,
        tool: str,
        chain_id: int,
        phase_name: str,
        current_user: User,
        no_llm_analysis: bool = False,
    ) -> dict[str, Any]:
        ctx = ChainContext(chain_id=chain_id, phase_name=phase_name)
        cb = CallbackInfo(display_id=display_id, tool_name="agent_" + tool)
        step, llm_a, c_agent = await check_and_process_agent_cmd(
            cb, ctx, command_params, self.mythic_client, no_llm_analysis
        )
        self.session.add(step)
        try:
            await self.session.commit()
            c_agent.step_id = step.id
            self.session.add(c_agent)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(status_code=400) from exc
        return {
            "user_id": current_user.user_id,
            "callback_display_id": display_id,
            "mythic_task_id": step.mythic_task_id,
            "tool_name": step.tool_name,
            "command": step.command,
            "status": step.status,
            "raw_output": step.raw_log,
            "llm_analysis": llm_a,
        }

    async def approve_action(  # noqa: PLR0913, PLR0917
        self,
        command: str,
        chain_id: int,
        phase: str,
        agent_id: int,
        type_cmd: str,
        type_tool: str,
        target_os_type: str,
    ) -> dict[str, Any]:
        ctx = ChainContext(chain_id=chain_id, phase_name=phase)
        cb = CallbackInfo(
            display_id=agent_id,
            tool_name=f"{type_cmd}_{type_tool}",
        )
        result = await process_approved_cmd(
            cmd=command,
            ctx=ctx,
            cb=cb,
            payload_params=PayloadParams(os_type=target_os_type),
            mythic_client=self.mythic_client,
        )
        if hasattr(result, "__await__"):
            attack_step, llm_analysis, agent = await result
        else:
            attack_step, llm_analysis, agent = result
        attack_step.llm_analysis = llm_analysis
        attack_step.status = "success"
        self.session.add(attack_step)
        try:
            await self.session.commit()
            await self.session.refresh(attack_step)
            if agent != "":
                agent.step_id = attack_step.id
                self.session.add(agent)
                await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise HTTPException(
                status_code=400, detail="Database integrity error"
            ) from exc
        return {
            "attack_step": attack_step,
            "llm_analysis": llm_analysis,
        }

    async def execute_approved_action(
        self,
        command: str,
        agent_display_id: int,
        chain_id: int,
        phase: str,
    ) -> dict[str, Any]:
        result = await self.mythic_client.execute_local_command(
            command, agent_display_id
        )
        llm_analysis_result = await analyze_command_output_with_llm(
            command, result.output
        )
        attack_step = AttackStep(
            chain_id=chain_id,
            phase=phase,
            tool_name=command.split(maxsplit=1)[0],
            command=command,
            mythic_task_id="",
            mythic_payload_uuid="",
            mythic_payload_id="",
            raw_log=result.output,
            status="success",
        )
        return {
            "attack_step": attack_step,
            "llm_analysis": llm_analysis_result,
        }

    async def get_agent_status(self, display_id: int) -> str:
        return await get_agent_status(display_id, self.mythic_client)

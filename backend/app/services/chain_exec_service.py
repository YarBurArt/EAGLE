import asyncio
import json
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmd.c2_tool import MythicClient
from app.cmd.proc import (
    CallbackInfo,
    ChainContext,
    PayloadParams,
    process_approved_cmd,
)
from app.core import database_session
from app.models import Agent, AttackStep


class ChainExecutionService:
    def __init__(self, session: AsyncSession, mythic_client: MythicClient) -> None:
        self.session = session
        self.mythic_client = mythic_client

    async def perform_chain_step(
        self,
        steps: list[AttackStep],
        zero_display_id: int,
        cancel_event: asyncio.Event,
    ) -> AsyncGenerator[str]:
        async with database_session.get_async_session() as session:
            for step in steps:
                if cancel_event.is_set():
                    break
                res_agent = await session.execute(
                    select(Agent).where(Agent.step_id == step.id)
                )
                c_agent = res_agent.scalars().first()
                if c_agent:
                    display_id = c_agent.callback_display_id
                    p_os_type = c_agent.os_type
                else:
                    display_id = zero_display_id
                    p_os_type = "Windows"
                ctx = ChainContext(chain_id=step.chain_id, phase_name=step.phase)
                cb = CallbackInfo(display_id=display_id, tool_name=step.tool_name)
                result, llm_a, _ = await process_approved_cmd(
                    cmd=step.command,
                    ctx=ctx,
                    cb=cb,
                    payload_params=PayloadParams(os_type=p_os_type),
                    mythic_client=self.mythic_client,
                )
                resp_step = {
                    "step_id": result.id,
                    "chain_id": result.chain_id,
                    "phase": result.phase,
                    "tool_name": result.tool_name,
                    "mythic_payload_uuid": result.mythic_payload_uuid,
                    "status": result.status,
                    "raw_log": result.raw_log,
                    "command": result.command,
                }
                out_d = {
                    "AttackStep": resp_step,
                    "llm_analysis": llm_a,
                }
                yield json.dumps(out_d, default=str) + "\n"

    @staticmethod
    def get_sorted_steps(steps: list[AttackStep]) -> list[AttackStep]:
        return sorted(
            (s for s in steps if s.status == "success"),
            key=lambda step: step.update_time,
        )

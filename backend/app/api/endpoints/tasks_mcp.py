"""
MCP server exposing EAGLE main tasks for LLM agents
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy import select

from app.cmd.c2_tool import MythicClient
from app.core import database_session
from app.core.security.jwt import create_jwt_token, verify_jwt_token
from app.core.security.password import verify_password
from app.models import User
from app.services.c2_service import CommandsC2ExecService
from app.services.chain_exec_service import ChainExecutionService
from app.services.chain_service import ChainService
from app.services.payload_service import AgentPayloadService

mcp = MCPServer(
    "EAGLE MCP",
    description="Attack emulation management tools for the EAGLE platform (Emulated Attack Generator w/ Layered Engine), to build and reproduce Unified Kill Chains for blueteam.",
)


@dataclass
class AuthState:
    """JWT creds for the MCP agent"""

    token: str = ""
    exp: float = 0.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def is_valid(self) -> bool:
        return bool(self.token) and time.time() < self.exp - 60


@dataclass
class ToolContext:
    mythic: MythicClient
    user: User


_auth = AuthState()
_ctx: ToolContext | None = None
_ctx_lock = asyncio.Lock()


def _env(name: str) -> str:
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(
            f"{name} is not set. Set it in your environment or .env file."
        )
    return value


async def _ensure_auth() -> None:
    if _auth.is_valid:
        return
    async with _auth._lock:
        if _auth.is_valid:
            return
        email = _env("EAGLE_LLM_AGENT_EMAIL")
        password = _env("EAGLE_LLM_AGENT_PASSWORD")
        async with database_session.get_async_session() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                raise RuntimeError(f"No user found for email {email}")
            if not verify_password(password, user.hashed_password):
                raise RuntimeError("EAGLE_LLM_AGENT_PASSWORD is incorrect")
            jwt_token = create_jwt_token(user_id=user.user_id)
            _auth.token = jwt_token.access_token
            _auth.exp = jwt_token.payload.exp


async def _get_ctx() -> ToolContext:
    global _ctx  # noqa: PLW0603
    await _ensure_auth()
    if _ctx is not None:
        return _ctx
    async with _ctx_lock:
        if _ctx is not None:
            return _ctx
        mythic = MythicClient()
        await mythic.connect()
        payload = verify_jwt_token(_auth.token)
        async with database_session.get_async_session() as session:
            user = await session.scalar(select(User).where(User.user_id == payload.sub))
        if user is None:
            raise RuntimeError(f"User {payload.sub} not found after auth")
        _ctx = ToolContext(mythic=mythic, user=user)
    return _ctx


@mcp.tool()
async def create_attack_chain(chain_name: str) -> dict[str, Any]:
    """Create a new attack chain with the given name. Returns chain_id, chain_name, and the starting phase (Reconnaissance)."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        chain_id, name, phase = await svc.create_chain(chain_name, ctx.user)
    return {"chain_id": chain_id, "chain_name": name, "current_phase_name": phase}


@mcp.tool()
async def run_local_command(
    chain_name: str,
    callback_display_id: int,
    command: str,
) -> dict[str, Any]:
    """Execute a shell command on the zero agent via Mythic C2, like just bash, but for reproducible chain. Requires chain_name, the callback_display_id of the agent, and the command string."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        chain_svc = ChainService(session)
        cmd_svc = CommandsC2ExecService(session, ctx.mythic)
        chain_name_r, chain_id, phase_name = await chain_svc.get_chain_n_phase(
            chain_name, ctx.user
        )
        result = await cmd_svc.run_local_command(
            command,
            callback_display_id,
            chain_id,
            phase_name,
            ctx.user,
            no_llm_analysis=True,
        )
    return {"chain_name": chain_name_r, **result}


@mcp.tool()
async def run_agent_command(
    chain_name: str,
    callback_display_id: int,
    command_params: str = "",
    tool: str = "shell",
) -> dict[str, Any]:
    """Execute a command on a remote agent via a specific Mythic tool (like shell, libinject). Requires chain_name, callback_display_id, command_params, and tool name."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        chain_svc = ChainService(session)
        cmd_svc = CommandsC2ExecService(session, ctx.mythic)
        chain_name_r, chain_id, phase_name = await chain_svc.get_chain_n_phase(
            chain_name, ctx.user
        )
        result = await cmd_svc.run_agent_command(
            command_params,
            callback_display_id,
            tool,
            chain_id,
            phase_name,
            ctx.user,
            no_llm_analysis=True,
        )
    return {"chain_name": chain_name_r, **result}


@mcp.tool()
async def create_agent_payload(
    chain_name: str,
    os_type: str,
    payload_type: str | None = None,
) -> dict[str, Any]:
    """Build a new Mythic C2 payload for the given OS. Returns download_url, payload_uuid, and payload_id. Use this to create agent binaries for deployment."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        chain_svc = ChainService(session)
        payload_svc = AgentPayloadService(session, ctx.mythic)
        _, chain_id, phase_name = await chain_svc.get_chain_n_phase(
            chain_name, ctx.user
        )
        result = await payload_svc.create_payload(
            chain_id, phase_name, payload_type, os_type
        )
    return result


@mcp.tool()
async def register_agent(rhost: str, chain_name: str) -> dict[str, Any]:
    """Register a new agent callback from a remote host into the attack chain. Call this after a payload has been executed on the target. Returns callback_display_id, os_type, and status."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        chain_svc = ChainService(session)
        payload_svc = AgentPayloadService(session, ctx.mythic)
        _, chain_id, phase_name = await chain_svc.get_chain_n_phase(
            chain_name, ctx.user
        )
        result = await payload_svc.register_agent(rhost, chain_id, phase_name)
    return result


@mcp.tool()
async def get_agent_status(display_id: int) -> str:
    """Check whether an agent callback is active. Returns 'success' if the agent is alive, 'fail' otherwise."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        cmd_svc = CommandsC2ExecService(session, ctx.mythic)
        return await cmd_svc.get_agent_status(display_id)


@mcp.tool()
async def get_chain_info(chain_id: int) -> dict[str, Any]:
    """Get detailed information about an attack chain: current UCKC phase, last attack step, final_status, and user info."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        info = await svc.read_chain_info(chain_id, ctx.user)
    last_step = info.pop("last_attack_step", None)
    if last_step is not None:
        info["last_attack_step"] = {
            "id": last_step.id,
            "chain_id": last_step.chain_id,
            "phase": last_step.phase,
            "tool_name": last_step.tool_name,
            "command": last_step.command,
            "status": last_step.status,
            "raw_log": last_step.raw_log,
        }
    return info


@mcp.tool()
async def advance_chain_phase(chain_id: int) -> dict[str, Any]:
    """Advance the attack chain to the next kill-chain phase (e.g. Reconnaissance -> Resource Development). Returns the new phase name."""
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        cid, phase = await svc.next_phase(chain_id)
    return {"chain_id": cid, "current_phase_name": phase}


@mcp.tool()
async def set_chain_phase(chain_id: int, phase_name: str) -> dict[str, Any]:
    """Set the attack chain to a specific kill-chain phase. Valid phases: Reconnaissance, Resource Development, Delivery, Social Engineering, Exploitation, Persistence, Defense Evasion, Command & Control, Pivoting, Discovery, Privilege Escalation, Execution, Credential Access, Lateral Movement, Collection, Exfiltration, Impact, Objectives."""
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        cid, phase = await svc.set_phase(chain_id, phase_name)
    return {"chain_id": cid, "current_phase_name": phase}


@mcp.tool()
async def reject_last_step(chain_name: str) -> dict[str, Any]:
    """Delete the last saved attack step from the chain. Use this to undo a mistake. Returns the deleted step details."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        step = await svc.reject_last_step(chain_name, ctx.user)
    return {
        "id": step.id,
        "chain_id": step.chain_id,
        "phase": step.phase,
        "tool_name": step.tool_name,
        "command": step.command,
        "status": step.status,
    }


@mcp.tool()
async def run_chain(
    chain_id: int,
    zero_display_id: int,
) -> list[dict[str, Any]]:
    """Re-execute all successful steps in an existing attack chain sequentially. Returns a list of step results, each with AttackStep data and llm_analysis."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        chain_svc = ChainService(session)
        exec_svc = ChainExecutionService(session, ctx.mythic)
        steps = await chain_svc.get_chain_steps(chain_id)
        sorted_steps = exec_svc.get_sorted_steps(steps)
        cancel_event = asyncio.Event()
        results: list[dict[str, Any]] = []
        async for chunk in exec_svc.perform_chain_step(
            sorted_steps, zero_display_id, cancel_event
        ):
            line = chunk.strip()
            if line:
                results.append(json.loads(line))
    return results


@mcp.tool()
async def cancel_chain(chain_id: int, chain_name: str) -> dict[str, str]:
    """Cancel a running attack chain execution. Requires the chain_id and chain_name for verification."""
    async with database_session.get_async_session() as session:
        svc = ChainService(session)
        verified = await svc.verify_chain_name(chain_id, chain_name)
    if not verified:
        return {"status": "error", "detail": "chain_name does not match chain_id"}
    return {"status": "canceled", "chain_name": chain_name}


@mcp.tool()
async def approve_action(  # noqa: PLR0913, PLR0917
    command: str,
    agent_id: int,
    chain_id: int,
    phase: str,
    type_cmd: str,
    type_tool: str,
    target_os_type: str,
    approved_by: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Approve and execute an LLM-suggested action. Routes the command based on type_cmd (local, agent, payload, getcallback, custom). Returns the saved AttackStep and LLM analysis."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        cmd_svc = CommandsC2ExecService(session, ctx.mythic)
        result = await cmd_svc.approve_action(
            command=command,
            chain_id=chain_id,
            phase=phase,
            agent_id=agent_id,
            type_cmd=type_cmd,
            type_tool=type_tool,
            target_os_type=target_os_type,
        )
    return {
        "attack_step": {
            "id": result["attack_step"].id,
            "chain_id": result["attack_step"].chain_id,
            "phase": result["attack_step"].phase,
            "tool_name": result["attack_step"].tool_name,
            "command": result["attack_step"].command,
            "status": result["attack_step"].status,
        },
        "llm_analysis": result["llm_analysis"],
    }


@mcp.tool()
async def execute_action(
    command: str,
    agent_display_id: int,
    chain_id: int,
    phase: str,
) -> dict[str, Any]:
    """Execute an approved action directly on the specified agent. Simpler than approve_action when you already know the command and target."""
    ctx = await _get_ctx()
    async with database_session.get_async_session() as session:
        cmd_svc = CommandsC2ExecService(session, ctx.mythic)
        result = await cmd_svc.execute_approved_action(
            command=command,
            agent_display_id=agent_display_id,
            chain_id=chain_id,
            phase=phase,
        )
    return {
        "attack_step": {
            "id": result["attack_step"].id,
            "chain_id": result["attack_step"].chain_id,
            "phase": result["attack_step"].phase,
            "tool_name": result["attack_step"].tool_name,
            "command": result["attack_step"].command,
            "status": result["attack_step"].status,
        },
        "llm_analysis": str(result["llm_analysis"]),
    }

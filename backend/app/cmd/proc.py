"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""

import hashlib
import json
import time
from dataclasses import dataclass

from fastapi import HTTPException, status
from pydantic import BaseModel

from app.cmd.c2_tool import AgentCommandOutput, MythicClient
from app.cmd.llm_analysis import llm_service
from app.core.config import PHASE_COMMANDS, UNSAFE_CMD, phase_prompts
from app.core.llm_templ import LLMTemplates
from app.models import Agent, AttackStep


class ActionSuggestionsResponse(BaseModel):
    """Pydantic model for LLM action suggestions response"""

    phase: str
    priorities: list[str] | None = []
    tools: list[str] | None = []
    attack_vectors: list[str] | None = []
    what_to_look_for: list[str] | None = []
    next_steps: list[str] | None = []
    commands: list[str] | None = []
    error: str | None = None
    format: str | None = "json"


@dataclass
class PayloadParams:
    lport: int = -1
    os_type: str = "Windows"


@dataclass
class ChainContext:
    chain_id: int
    phase_name: str


@dataclass
class CallbackInfo:
    display_id: int
    tool_name: str


async def init_agent():
    """generate payload ->
    download by mythic_payload_uuid ->
    run via subprocess.run, save mythic agent info to db
    save Resource Development info to AttackStep"""
    pass


async def process_approved_cmd(
    cmd: str,
    ctx: ChainContext,
    cb: CallbackInfo,
    payload_params: PayloadParams | None = None,
    mythic_client: MythicClient | None = None,
):
    """based on PHASE_COMMANDS and c2_tool defs it route cmd and execute
    no db changes to AttackStep by default cuz it depends on tasks"""
    # tool_name like agent_libinject or local_impacket-wmiexec
    type_n, tool_n = cb.tool_name.split("_", 1)
    assert type_n in ["local", "agent", "custom", "payload", "getcallback"]

    if payload_params is None:
        payload_params = PayloadParams()

    if type_n == "local":
        result, llm_a = await check_and_process_local_cmd(
            cmd=cmd,
            display_id=cb.display_id,
            ctx=ctx,
            mythic_client=mythic_client,
        )
        return result, llm_a, ""
    if type_n == "payload":
        result, llm_a = await check_and_create_mpayload(
            ctx,
            cb.tool_name,
            tool_n,
            payload_params,
            mythic_client,
        )
        return result, llm_a, ""
    if type_n == "getcallback":
        result, agent = await process_new_callback(
            ctx,
            cb.tool_name,
            cmd,
            1,
            mythic_client,
        )
        return result, "", agent
    if type_n == "agent":
        result, llm_a, agent = await check_and_process_agent_cmd(
            cb,
            ctx,
            cmd,
            mythic_client,
        )
        return result, llm_a, agent
    if type_n == "custom":
        # any other scenarios based on custom C2 functions in c2_tool
        if not hasattr(mythic_client, tool_n):
            return  # maybe some exception
        def_func = getattr(mythic_client, tool_n)
        args_e = cmd.split(":")  # enforce LLM to return params as b:c
        result = await def_func(cb.display_id, *args_e)
        # check object from tuple for class, ret like 'status raw_log'
        strings_out = " ".join(i for i in result if isinstance(i, str))
        llm_analysis = await analyze_command_output_with_llm(strings_out, cmd)
        return result, llm_analysis, ""


async def process_new_callback(
    ctx: ChainContext,
    tool_name: str,
    cmd: str,
    parent_step_id: int,
    mythic_client: MythicClient,
) -> tuple[AttackStep, Agent]:
    """for save to Agent table by callback"""
    res = await mythic_client.get_callback_after(cmd)  # cmd is rhost
    os_type, status, display_id = res
    p_id, p_uuid = await mythic_client.get_payload_ids(display_id)
    return AttackStep(
        phase=ctx.phase_name,
        chain_id=ctx.chain_id,
        status=status,
        tool_name=tool_name,
        command=cmd,
        mythic_task_id=0,  # just created
        mythic_payload_id=p_id,
        mythic_payload_uuid=p_uuid,
        raw_log=str(res),
    ), Agent(
        step_id=parent_step_id,  # not connected to reproduce as step
        agent_name=f"{os_type}#{str(display_id)}",
        os_type=os_type,
        status=status,
        callback_display_id=display_id,
    )


async def check_and_process_agent_cmd(
    cb: CallbackInfo,
    ctx: ChainContext,
    cmd: str,
    mythic_client: MythicClient,
) -> tuple[AttackStep, str, Agent]:
    """run commands on agent and return output based on tool"""
    _, tool_n = cb.tool_name.split("_", 1)
    assert cmd not in UNSAFE_CMD
    try:
        result = await mythic_client.execute_agent_command(
            cmd=tool_n,
            params=cmd,  # basically in local_cmd is also params
            callback_display_id=cb.display_id,
        )  # by llm cmd based on get_cmd_list...
    except Exception as e:  # general exception cuz mythic lib
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="The command was aborted by C2, the step/agent not saved,"
            " but you can bypass this issue using agent commands"
            " and shell scripts for long time tasks.",
        ) from e
    llm_analysis = await analyze_command_output_with_llm(result.output, cmd)
    # for reproducibility
    rhost, agent_os, agent_status = await mythic_client.get_os_by_display_id(
        cb.display_id
    )
    return (
        AttackStep(
            phase=ctx.phase_name,
            chain_id=ctx.chain_id,
            status="success",
            tool_name=cb.tool_name,
            command=cmd,
            mythic_task_id=result.mythic_task_id,
            mythic_payload_id=result.mythic_payload_id,
            mythic_payload_uuid=result.mythic_payload_uuid,
            raw_log=result.output,
        ),
        llm_analysis,
        Agent(
            step_id=1,  # need update in tasks
            os_type=agent_os,
            status=agent_status,
            agent_name=str(cb.display_id) + "#" + rhost,
            callback_display_id=cb.display_id,
        ),
    )


async def check_and_create_mpayload(
    ctx: ChainContext,
    tool_name: str,
    tool_n: str,
    payload_params: PayloadParams,
    mythic_client: MythicClient,
) -> tuple[AttackStep, str]:
    """check payload parameters and create payload, save in mythic,
    return uuid/id to get information or send to rhost"""
    assert payload_params.os_type in ["Windows", "macOS", "Linux"]  # from mythic api
    # TODO: set port/os by C2, get information about agents profile
    file_name = tool_n + hashlib.md5(str(time.time()).encode("utf-8"))
    cmd = "create_payload"
    result = await mythic_client.create_payload(
        payload_type=tool_n,
        file_name=file_name,
        lport=payload_params.lport,
        os_type=payload_params.os_type,  # host from default
    )
    llm_analysis = await analyze_command_output_with_llm(result.raw_log, cmd)
    return AttackStep(
        chain_id=ctx.chain_id,
        tool_name=tool_name,
        phase="Resource Development",
        mythic_task_id=0,
        command=cmd,
        mythic_payload_id=result.payload_id,
        mythic_payload_uuid=result.payload_uuid,
        status=result.status,
        raw_log=result.raw_log,
    ), llm_analysis


async def get_agent_status(
    callback_display_id: int, mythic_client: MythicClient
) -> str:
    """maybe process status, like if fail -> restart agent in chain"""
    agent_status = await mythic_client.check_status(callback_display_id)
    return agent_status


async def check_and_process_local_cmd(
    cmd: str,
    display_id: int,
    ctx: ChainContext,
    mythic_client: MythicClient,
) -> tuple[AttackStep, str]:
    """async function for check is safe command ->
    execute on zero agent, formatting to AttackStep"""
    assert cmd not in UNSAFE_CMD
    try:
        # send command to C2
        ex_result: AgentCommandOutput = await mythic_client.execute_local_command(
            cmd, display_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="The command was aborted by C2, the step was not saved,"
            " but you can bypass this issue using bash scripts"
            " for long time tasks.",
        ) from e
    llm_analysis = await analyze_command_output_with_llm(ex_result.output, cmd)

    attack_step = AttackStep(
        chain_id=ctx.chain_id,
        phase=ctx.phase_name,
        tool_name="local_" + cmd.split(maxsplit=1)[0],
        command=cmd,
        mythic_task_id=ex_result.mythic_task_id,
        mythic_payload_uuid=ex_result.mythic_payload_uuid,
        mythic_payload_id=ex_result.mythic_payload_id,
        raw_log=ex_result.output,
        status="success",
    )
    return attack_step, llm_analysis


async def analyze_command_output_with_llm(output: str, command: str) -> str:
    """
    sending command output to LLM for analysis
    """
    try:
        prompt = f"""
        command: {command}
        output: {output}

        analyze results and find most important things.
        """

        llm_response = await llm_service.query_llm(prompt)

        return llm_response

    except Exception as e:
        return f"error while analysis LLM: {str(e)}"


async def is_command_allowed_in_phase(
    cmd: str,
    phase_name: str,
    payload_type: str,
    os_type: str,
    mythic_client: MythicClient,
) -> bool:
    """check command for allowed, we don't want to ransomware"""
    allowed_commands = get_commands_for_phase(phase_name)

    # Get additional allowed commands based on payload type and OS
    payload_commands = await mythic_client.get_commands_for_payload(
        payload_type, os_type
    )
    allowed_commands.extend(payload_commands)

    # Normalize command for comparison
    cmd_normalized = cmd.strip().lower()

    # Check for exact matches and partial matches
    for allowed in allowed_commands:
        allowed_normalized = allowed.strip().lower()

        # Exact match
        if cmd_normalized == allowed_normalized:
            return True

        # Partial match - command starts with allowed command
        if cmd_normalized.startswith(allowed_normalized.split()[0]):
            return True

        # Check if allowed command is a substring of the input command
        if allowed_normalized in cmd_normalized:
            return True

    # Additional security checks
    # Block dangerous commands
    dangerous_patterns = [
        "rm -rf",
        "format",
        "del /f",
        "rmdir /s",
        "shutdown",
        "reboot",
        "poweroff",
        "dd if=/dev/zero",
        "chmod 777",
        "chown root",
        "sudo rm",
    ]

    for pattern in dangerous_patterns:
        if pattern in cmd_normalized:
            return False

    return False


def get_commands_for_phase(phase_name: str):
    """get specific commands for phase, format"""
    return PHASE_COMMANDS.get(phase_name, [])


async def suggest_actions_for_phase(
    phase_name: str,
    payload_type: str,
    os_type: str,
    mythic_client: MythicClient,
) -> list[str]:
    """Return list of suggested commands for given phase"""
    by_agent = await mythic_client.get_commands_for_payload(payload_type, os_type)
    return get_commands_for_phase(phase_name) + by_agent


async def generate_action_suggestions_with_llm(
    phase_name: str, context_summary: str = ""
) -> dict:
    """Use LLM to refine suggestions based on summary or logs"""
    try:
        base_prompt = phase_prompts.get(phase_name, phase_prompts["recon"])
        prompt = base_prompt.format(
            # cuz a = None or 1 will return 1
            context=context_summary or "No context provided"
        )

        # Combine system prompt with user prompt
        full_prompt = f"{LLMTemplates.SYSTEM_PROMT}\n\n{prompt}"
        llm_response = await llm_service.query_llm(full_prompt)

        try:
            suggestions = json.loads(llm_response)
            return suggestions
        except json.JSONDecodeError:
            response = ActionSuggestionsResponse(
                phase=phase_name, suggestions=llm_response, format="text"
            )
            return response.dict()

    except Exception as e:
        response = ActionSuggestionsResponse(
            phase=phase_name,
            error=f"Error generating suggestions: {str(e)}",
            suggestions=[],
        )
        return response.dict()

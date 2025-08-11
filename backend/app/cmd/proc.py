"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""
import time
import json
import hashlib
from typing import Tuple

from app.cmd.c2_tool import (
    execute_local_command, check_status, AgentCommandOutput,
    get_cmd_list_for_payload, execute_agent_command_o, create_payload_d
)
import app.cmd.c2_tool as c2_tool_c_cmd
from app.models import AttackStep
from app.cmd.llm_analysis import llm_service
from app.core.config import (
    phase_prompts, PHASE_COMMANDS, UNSAFE_CMD
)


async def init_agent():
    """ generate payload ->
        download by mythic_payload_uuid ->
        run via subprocess.run, save mythic agent info to db
        save Resource Development info to AttackStep"""
    pass


async def process_approved_cmd(
    cmd: str, chain_id: int, tool_name: str, display_id: int,
    phase_name: str, p_lport: int = 4329, p_os_type: str = "Windows",
) -> Tuple[AttackStep, str]:
    """ based on PHASE_COMMANDS and c2_tool defs it route cmd and execute
        no db changes to AttackStep by default cuz it depends on tasks """
    # tool_name like agent_libinject or local_impacket-wmiexec
    type_n, tool_n = tool_name.split("_", 1)
    assert type_n in ['local', 'agent', 'custom', 'payload']

    if type_n == "local":
        result, llm_a = await check_and_process_local_cmd(
            cmd=cmd,  # params for shell agent command
            c_display_id=display_id,
            chain_id=chain_id, phase_name=phase_name
        )
        return result, llm_a
    if type_n == "payload":
        result, llm_a = await check_and_create_mpayload(
            chain_id, tool_name, tool_n, p_os_type, p_lport
        )  # next process by payload uuid
        return result, llm_a
    if type_n == "agent":
        result, llm_a = await check_and_process_agent_cmd(
            display_id, chain_id, cmd,  # cmd is just parameters
            tool_name, tool_n,  # actual command like libinject
            phase_name
        )
        return result, llm_a
    if type_n == "custom":
        # any other scenarios based on custom C2 functions in c2_tool
        if not hasattr(c2_tool_c_cmd, tool_n):
            return  # maybe some exception
        def_func = getattr(c2_tool_c_cmd, tool_n)
        args_e = cmd.split(":")  # enforce LLM to return params as b:c
        result = await def_func(display_id, *args_e)
        # check object from tuple for class, ret like 'status raw_log'
        strings_out = ' '.join(i for i in result if isinstance(i, str))
        llm_analysis = await analyze_command_output_with_llm(
            strings_out, cmd
        )
        return result, llm_analysis


async def check_and_process_agent_cmd(
    display_id: int, chain_id: int, cmd: str, tool_name: str,
    tool_n: str, phase: str
) -> Tuple[AttackStep, str]:
    """ run commands on agent and return output based on tool """
    assert cmd not in UNSAFE_CMD
    result = await execute_agent_command_o(
        cmd=tool_n, params=cmd,  # basicly in local_cmd is also params
        callback_display_id=display_id
    )  # by llm cmd based on get_cmd_list...
    llm_analysis = await analyze_command_output_with_llm(
        result.output, cmd
    )
    return AttackStep(
        phase=phase,
        chain_id=chain_id, status="success",
        tool_name=tool_name, command=cmd,
        mythic_task_id=result.mythic_task_id,
        mythic_payload_id=result.mythic_payload_id,
        mythic_payload_uuid=result.mythic_payload_uuid,
        raw_log=result.output,
    ), llm_analysis


async def check_and_create_mpayload(
    chain_id: int, tool_name: str, tool_n: str, p_os_type: str, p_lport: str
) -> Tuple[AttackStep, str]:
    """ check payload parameters and create payload, save in mythic,
        return uuid/id to get information or send to rhost """
    assert p_os_type in ['Windows', 'macOS', 'Linux']  # from mythic api
    # TODO: set port/os by C2, get information about agents profile
    file_name = tool_n + hashlib.md5(str(time.time()).encode('utf-8'))
    cmd = create_payload_d.__name__  # temp
    result = await create_payload_d(
        payload_type=tool_n, file_name=file_name,
        lport=p_lport, os_type=p_os_type  # host from default
    )
    llm_analysis = await analyze_command_output_with_llm(
        result.raw_log, cmd
    )
    return AttackStep(
        chain_id=chain_id, tool_name=tool_name,
        phase="Resource Development",
        mythic_task_id=0, command=cmd,
        mythic_payload_id=result.payload_id,
        mythic_payload_uuid=result.payload_uuid,
        status=result.status, raw_log=result.raw_log
    ), llm_analysis


async def get_agent_status(callback_display_id):
    """ maybe process status, like if fail -> restart agent in chain """
    status = await check_status(callback_display_id)
    return status


async def check_and_process_local_cmd(
        cmd: str, c_display_id: int, chain_id: int, phase_name: str
) -> Tuple[AttackStep, str]:
    """ async function for check is safe command ->
        execute on zero agent, formatting to AttackStep """
    assert cmd not in UNSAFE_CMD
    # phase even for local command depends on current or recon
    is_allowed_cmd = await is_command_allowed_in_phase(
        cmd, phase_name, "poseidon", "Linux"  # for agents get from d_id
    )
    # FIXME: phase names for commands
    # assert is_allowed_cmd, f"Command not allowed in phase {phase_name}"
    # send command to C2
    ex_result: AgentCommandOutput = await execute_local_command(
        cmd, c_display_id
    )
    # Отправляем вывод команды в LLM для анализа
    llm_analysis = await analyze_command_output_with_llm(
        ex_result.output, cmd
    )

    attack_step = AttackStep(
        chain_id=chain_id,
        phase=phase_name,
        tool_name="local_"+cmd.split()[0],
        command=cmd,
        mythic_task_id=ex_result.mythic_task_id,
        mythic_payload_uuid=ex_result.mythic_payload_uuid,
        mythic_payload_id=ex_result.mythic_payload_id,
        raw_log=ex_result.output,
        status="success"
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
    cmd: str, phase_name: str, payload_type: str, os_type: str
) -> bool:
    """ check command for allowed, we dont want to ransomware """
    allowed_commands = get_commands_for_phase(phase_name)
    # FIXME: for payload type format
    # allowed_commands += await get_cmd_list_for_payload(payload_type, os_type)
    # Можно сделать частичное совпадение или регулярки
    return any(
        cmd.strip().startswith(
            allowed.split()[0]
        ) for allowed in allowed_commands
    )


def get_commands_for_phase(phase_name: str):
    """ get specific commands for phase, format """
    return PHASE_COMMANDS.get(phase_name, [])


async def suggest_actions_for_phase(
    phase_name: str, payload_type: str, os_type: str
) -> list[str]:
    """Return list of suggested commands for given phase"""
    by_agent = get_cmd_list_for_payload(payload_type, os_type)
    return get_commands_for_phase(phase_name) + by_agent


async def generate_action_suggestions_with_llm(
    phase_name: str, context_summary: str = ""
) -> dict:
    """Use LLM to refine suggestions based on summary or logs"""
    try:
        # TODO: system prompt, generate also command agent for Agent
        base_prompt = phase_prompts.get(phase_name, phase_prompts["recon"])
        prompt = base_prompt.format(
            # cuz a = None or 1 will return 1
            context=context_summary or "No context provided"
        )
        llm_response = await llm_service.query_llm(prompt)

        try:
            suggestions = json.loads(llm_response)
            return suggestions
        except json.JSONDecodeError:
            # TODO: pydantic model for return
            return {
                "phase": phase_name,
                "suggestions": llm_response,
                "format": "text"
            }

    except Exception as e:
        return {
            "phase": phase_name,
            "error": f"Error generating suggestions: {str(e)}",
            "suggestions": []
        }

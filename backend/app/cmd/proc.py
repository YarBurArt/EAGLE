"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""
from app.cmd.c2_tool import execute_local_command, check_status
from app.models import AttackStep
from app.cmd.llm_analysis import (
    llm_service, PayloadRequest, QueryRequest, CodeAnalysisRequest
)
from app.core.config import (
    phases, phase_prompts, PHASE_COMMANDS, UNSAFE_CMD
)


async def init_zero_agent():
    """ generate payload ->
        download by mythic_payload_uuid ->
        run via subprocess.run, save mythic agent info to db
        save Resource Development info to AttackStep"""
    pass


async def get_agent_status(callback_display_id):
    """ maybe process status, like if fail -> restart agent in chain """
    status = await check_status(callback_display_id)
    return status


async def check_and_process_local_cmd(
        cmd: str, c_display_id: int, chain_id: int, phase_name: str
) -> AttackStep:
    """ async function for check is safe command ->
        execute on zero agent, formatting to AttackStep """
    assert cmd not in UNSAFE_CMD
    # phase even for local command depends on current or recon
    assert is_command_allowed_in_phase(
        cmd, phase_name
    ), f"Command not allowed in phase {phase_name}"
    # send command to C2
    output, myth_t_id, myth_p_id, myth_p_uuid = await execute_local_command(
        cmd, c_display_id
    )

    # Отправляем вывод команды в LLM для анализа
    llm_analysis = await analyze_command_output_with_llm(output, cmd)

    attack_step = AttackStep(
        chain_id=chain_id,
        phase=phase_name,
        tool_name=cmd.split()[0],
        command=cmd,
        mythic_task_id=myth_t_id,
        mythic_payload_uuid=myth_p_uuid,
        mythic_payload_id=myth_p_id,
        raw_log=output,
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


def is_command_allowed_in_phase(cmd: str, phase_name: str) -> bool:
    """ check command for allowed, we dont want to ransomware """
    allowed_commands = get_commands_for_phase(phase_name)
    # Можно сделать частичное совпадение или регулярки
    # TODO: check also for agent commands list
    return any(
        cmd.strip().startswith(
            allowed.split()[0]
        ) for allowed in allowed_commands
    )


def get_commands_for_phase(phase_name: str):
    """ get specific command for phase, format """
    # TODO: add commands get from agent
    return PHASE_COMMANDS.get(phase_name, [])


async def suggest_actions_for_phase(phase_name: str) -> list[str]:
    """Return list of suggested commands for given phase"""
    # TODO: add llm suggestions
    return get_commands_for_phase(phase_name)


async def generate_action_suggestions_with_llm(
    phase_name: str, context_summary: str = ""
):
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
            import json
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

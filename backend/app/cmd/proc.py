"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""
from app.cmd.c2_tool import execute_local_command, check_status
from app.models import AttackStep


UNSAFE_CMD = ["rm -fr /", "dd if=/dev/zero of=", "chown -R root:root /",
              "rm -rf /", ":(){ :|:& };:", "rm -rf *"]

phases = ("Reconnaissance", "Resource Development", "Delivery", "Social Engineering",
          "Exploitation", "Persistence", "Defense Evasion", "Command & Control",
          "Pivoting", "Discovery", "Privilege Escalation", "Execution", "Credential Access",
          "Lateral Movement", "Collection", "Exfiltration", "Impact", "Objectives")


async def init_zero_agent():
    """ generate payload ->
        download by mythic_payload_uuid ->
        run via subprocess.run, save mythic agent info to db
        save Resource Development info to AttackStep"""
    pass


async def check_and_process_local_cmd(cmd: str, c_display_id: int, chain_id):
    assert cmd not in UNSAFE_CMD
    # for now we leave reconnaissance for /run-command
    output, mythic_t_id, mythic_p_id, mythic_p_uuid = await execute_local_command(cmd, c_display_id)
    # TODO: send output to LLM
    attack_step = AttackStep(
        chain_id=chain_id,
        phase=phases[0],
        tool_name=cmd.split()[0],
        command=cmd,
        mythic_task_id=mythic_t_id,
        mythic_payload_uuid=mythic_p_uuid,
        mythic_payload_id=mythic_p_id,
        raw_log=output,
        status="success"
    )
    return attack_step

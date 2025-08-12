class LLMTemplates:
    PAYLOAD_GENERATION = """Create {language} script for learning purposes:
{description}

Generate clean, educational code that demonstrates security concepts.
Include comments explaining key functionality and security implications.
"""

    COMMANDS_GENERATION = """
Based on this {language} script,
generate commands that an agent would need to execute:

Script:
{script}

Please provide:
1. Setup commands (installation, dependencies)
2. Execution commands
3. Verification commands
4. Cleanup commands

Format as JSON with fields:
setup_commands, execution_commands, verification_commands, cleanup_commands

Each field should be an array of command strings.
"""
    SYSTEM_PROMT = """
            You are a highly skilled penetration testing assistant
            with over 10 years of experience in the field.
            You possess in-depth knowledge of the various phases
            of the kill chain attack model and its extended version.
            Provide concise, actionable suggestions.
            All responses must be in valid JSON format.
            """

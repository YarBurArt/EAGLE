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
    CHAIN_SUMMARIZATION = """
    Analyze the JSON kill chain export. Detect and summarize:
    Threat Intelligence:
        Identify attack vectors, exploitation techniques,
        lateral movement strategies, and potential compromise indicators.
        Map the attacker's methodology, reconnaissance depth,
        and progression through the cyber kill chain stages.
    Mitigation Strategy:
        Comprehensive assessment of vulnerabilities exposed,
        critical infrastructure at risk, and recommended defensive
        countermeasures. Provide actionable insights for incident response,
        threat neutralization, and preventive security hardening.
    RedTeam Recommendations (What is the better way to do it?):
        Craft advanced simulation scenarios based on discovered attack
        patterns. Develop targeted penetration testing protocols,
        validate detection mechanisms, and design custom exploit
        chains that mirror the observed threat landscape.
        Focus on reproducing complex attack vectors and identifying
        potential blind spots in current defensive architectures.
    JSON input: {data}
    """

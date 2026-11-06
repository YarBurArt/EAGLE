"""Shared agent-test payloads; finding ids stage against each caller's fakes."""

FINDINGS = {
    "findings": [
        {
            "title": "C2 beacon",
            "description": "host beaconed out",
            "stage": "Command & Control",
            "confidence": 0.8,
            "uncertainty": "",
            "evidence": [{"quote": "C2 beacon to 26.26"}],
        }
    ]
}


def make_draft(finding_ids: list[int]) -> dict:
    return {
        "steps": [
            {
                "phase": "Command & Control",
                "step_type": "bash",
                "tool_name": "shell",
                "command": "echo beacon",
                "finding_ids": finding_ids,
                "confidence": 0.6,
            }
        ]
    }

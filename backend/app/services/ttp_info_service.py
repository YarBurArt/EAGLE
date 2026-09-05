"""
Provides MITRE ATT&CK technique lookups and UKC phase mapping
for the EAGLE attack chain system.
Check UKC from https://www.unifiedkillchain.com/assets/The-Unified-Kill-Chain.pdf
"""

from __future__ import annotations

from app.mitre_loader import TTP, AttackGraph

UKC_PHASE_DESCRIPTIONS: dict[str, str] = {
    "Reconnaissance": (
        "Researching, identifying and selecting targets using active or "
        "passive reconnaissance."
    ),
    "Resource Development": (
        "Preparatory activities aimed at setting up the infrastructure "
        "required for the attack."
    ),
    "Delivery": (
        "Techniques resulting in the transmission of a weaponized object "
        "to the targeted environment."
    ),
    "Social Engineering": (
        "Techniques aimed at the manipulation of people to perform unsafe actions."
    ),
    "Exploitation": (
        "Techniques to exploit vulnerabilities in systems that may, amongst "
        "others, result in code execution."
    ),
    "Persistence": (
        "Any access, action or change to a system that gives an attacker "
        "persistent presence on the system."
    ),
    "Defense Evasion": (
        "Techniques an attacker may specifically use for evading detection "
        "or avoiding other defenses."
    ),
    "Command & Control": (
        "Techniques that allow attackers to communicate with controlled "
        "systems within a target network."
    ),
    "Pivoting": (
        "Tunneling traffic through a controlled system to other systems "
        "that are not directly accessible."
    ),
    "Discovery": (
        "Techniques that allow an attacker to gain knowledge about a system "
        "and its network environment."
    ),
    "Privilege Escalation": (
        "The result of techniques that provide an attacker with higher "
        "permissions on a system or network."
    ),
    "Execution": (
        "Techniques that result in execution of attacker-controlled code "
        "on a local or remote system."
    ),
    "Credential Access": (
        "Techniques resulting in the access of, or control over, system, "
        "service or domain credentials."
    ),
    "Lateral Movement": (
        "Techniques that enable an adversary to horizontally access and "
        "control other remote systems."
    ),
    "Collection": (
        "Techniques used to identify and gather data from a target network "
        "prior to exfiltration."
    ),
    "Exfiltration": (
        "Techniques that result or aid in an attacker removing data from "
        "a target network."
    ),
    "Impact": (
        "Techniques aimed at manipulating, interrupting or destroying the "
        "target system or data."
    ),
    "Objectives": (
        "Socio-technical objectives of an attack that are intended to "
        "achieve a strategic goal."
    ),
}

# keys are STIX kill_chain_phases phase_name values,
# direct mappings have a single UKC phase
ATTACK_TACTIC_TO_UKC: dict[str, list[str]] = {
    "reconnaissance": ["Reconnaissance"],
    "resource-development": ["Resource Development"],
    "initial-access": ["Delivery", "Social Engineering", "Exploitation"],
    "execution": ["Execution"],
    "persistence": ["Persistence"],
    "privilege-escalation": ["Privilege Escalation"],
    "defense-evasion": ["Defense Evasion"],
    "credential-access": ["Credential Access"],
    "discovery": ["Discovery"],
    "lateral-movement": ["Pivoting", "Lateral Movement"],
    "collection": ["Collection"],
    "command-and-control": ["Command & Control"],
    "exfiltration": ["Exfiltration"],
    "impact": ["Impact", "Objectives"],
}

_DELIVERY_KEYWORDS = {"delivery", "weaponized", "supply chain", "drive-by"}
_SOCIAL_KEYWORDS = {
    "phishing",
    "spearphishing",
    "social engineering",
    "pretexting",
    "user action",
    "click",
    "credential phish",
}
_EXPLOIT_KEYWORDS = {
    "exploit",
    "client exploit",
    "server exploit",
    "code execution",
    "vulnerability",
    "CVE",
    "overflow",
}
_PIVOT_KEYWORDS = {
    "pivot",
    "proxy",
    "tunnel",
    "port forward",
    "ssh tunnel",
    "socks",
    "network gateways",
}


def _phase_matches_technique(phase_name: str, ttp: TTP) -> bool:
    text = (ttp.name + " " + ttp.description).lower()

    if phase_name == "Delivery":
        return any(kw in text for kw in _DELIVERY_KEYWORDS)
    if phase_name == "Social Engineering":
        return any(kw in text for kw in _SOCIAL_KEYWORDS)
    if phase_name == "Exploitation":
        return any(kw in text for kw in _EXPLOIT_KEYWORDS)
    if phase_name == "Pivoting":
        return any(kw in text for kw in _PIVOT_KEYWORDS)
    return True


class TTPInfoService:
    """for MITRE ATT&CK techniques and map them to UKC"""

    def __init__(self, graph: AttackGraph) -> None:
        self._graph = graph

    def get_ttps_by_apt(self, apt_mitre_id: str) -> list[TTP]:
        """all TTPs used by given APT"""
        apt = self._graph.apts.get(apt_mitre_id)
        if apt is None:
            return []
        return [
            self._graph.ttps[tid]
            for tid in apt.technique_ids
            if tid in self._graph.ttps
        ]

    def get_ttp_info(self, ttp_mitre_id: str) -> TTP | None:
        return self._graph.ttps.get(ttp_mitre_id)

    def get_ttps_by_phase(self, phase_name: str) -> list[TTP]:
        tactic_ids = self._get_tactics_for_phase(phase_name)
        if not tactic_ids:
            return []

        tactic_set = set(tactic_ids)
        result: list[TTP] = []

        for ttp in self._graph.ttps.values():
            if not tactic_set.intersection(ttp.tactic_ids):
                continue
            # clarify phases that share a tactic
            if len(tactic_ids) > 1 and not _phase_matches_technique(phase_name, ttp):
                continue
            result.append(ttp)

        return result

    def get_phase_for_ttp(self, ttp_mitre_id: str) -> list[str]:
        ttp = self._graph.ttps.get(ttp_mitre_id)
        if ttp is None:
            return []

        matched: list[str] = []
        for phase_name, tactics in ATTACK_TACTIC_TO_UKC.items():
            if not set(tactics).intersection(ttp.tactic_ids):
                continue
            if len(tactics) > 1 and not _phase_matches_technique(phase_name, ttp):
                continue
            matched.append(phase_name)

        return matched

    @staticmethod
    def _get_tactics_for_phase(phase_name: str) -> list[str]:
        # invert the mapping: find which tactics belong to this phase
        result: list[str] = []
        for tactic, phases in ATTACK_TACTIC_TO_UKC.items():
            if phase_name in phases:
                result.append(tactic)
        return result

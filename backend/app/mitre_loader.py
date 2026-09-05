"""
MITRE ATT&CK STIX bundle loader.
Streams the enterprise-attack.json with ijson to build an in-memory
AttackGraph of APTs and TTPs linked via "uses" relationships.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import ijson

logger = logging.getLogger(__name__)


@dataclass
class APT:
    mitre_id: str  # like G0016, mitre format
    stix_id: str
    name: str
    source_country: str
    alt_names: list[str]
    technique_ids: list[str] = field(default_factory=list)


@dataclass
class TTP:
    mitre_id: str  # like T1566
    stix_id: str
    name: str
    description: str
    references: list[str] = field(default_factory=list)
    tactic_ids: list[str] = field(default_factory=list)  # like ta0001


@dataclass
class AttackGraph:
    apts: dict[str, APT]
    ttps: dict[str, TTP]


_COUNTRY_CODES: dict[str, str] = {
    "china": "CN",
    "russia": "RU",
    "iran": "IR",
    "north korea": "KP",
    "south korea": "KR",
    "united states": "US",
    "israel": "IL",
    "pakistan": "PK",
    "india": "IN",
    "vietnam": "VN",
    "turkey": "TR",
    "belgium": "BE",
    "colombia": "CO",
    "lebanon": "LB",
    "romania": "RO",
    "united kingdom": "GB",
}


def _normalize_country(countries: list[str]) -> str:
    if not countries:
        return "UNKNOWN"
    c = countries[0].strip().lower()
    if c in ("[unknown]", "unknown", ""):
        return "UNKNOWN"
    code = _COUNTRY_CODES.get(c)
    if code:
        return code
    min_country_code_len = 2
    if len(c) >= min_country_code_len:
        return c[:min_country_code_len].upper()
    return "UNKNOWN"


def _load_threat_group_cards(path: Path) -> dict[str, str]:
    """APT to country code lookup from ThaiCERT threat group cards"""
    data = json.loads(path.read_text())
    alias_to_country: dict[str, str] = {}

    for card in data.get("values", []):
        country = _normalize_country(card.get("country", []))
        if country == "UNKNOWN":
            continue

        actor = card.get("actor", "").strip()
        if actor:
            alias_to_country[actor.lower()] = country
        for name_obj in card.get("names", []):
            name = name_obj.get("name", "").strip()
            if name:
                alias_to_country[name.lower()] = country

    logger.info("loaded %d threat group card aliases", len(alias_to_country))
    return alias_to_country


def _extract_mitre_id(refs: list[dict]) -> str:
    for ref in refs:
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"]
    return ""


def _parse_intrusion_set(obj: dict, alias_to_country: dict[str, str]) -> APT | None:
    refs = obj.get("external_references", [])
    mitre_id = _extract_mitre_id(refs)
    if not mitre_id:
        return None

    name = obj.get("name", "")
    aliases = obj.get("aliases", [])

    # resolve country from name / aliases
    country = alias_to_country.get(name.lower().strip(), "UNKNOWN")
    if country == "UNKNOWN":
        for alias in aliases:
            country = alias_to_country.get(alias.lower().strip(), "UNKNOWN")
            if country != "UNKNOWN":
                break

    return APT(
        mitre_id=mitre_id,
        stix_id=obj.get("id", ""),
        name=name,
        source_country=country,
        alt_names=aliases,
    )


def _parse_attack_pattern(obj: dict) -> TTP | None:
    refs = obj.get("external_references", [])
    mitre_id = _extract_mitre_id(refs)
    if not mitre_id:
        return None

    urls = [r["url"] for r in refs if r.get("url")]

    # extract tactic IDs from kill_chain_phases
    # format: [{"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}]
    tactic_ids: list[str] = []
    for kc in obj.get("kill_chain_phases", []):
        if kc.get("kill_chain_name") == "mitre-attack":
            tactic_ids.append(kc.get("phase_name", ""))

    return TTP(
        mitre_id=mitre_id,
        stix_id=obj.get("id", ""),
        name=obj.get("name", ""),
        description=obj.get("description", ""),
        references=urls,
        tactic_ids=tactic_ids,
    )


def load_attack_graph(mitre_path: Path, thg_cards_path: Path) -> AttackGraph:
    """stream MITRE ATT&CK STIX data and build an AttackGraph"""
    alias_to_country = _load_threat_group_cards(thg_cards_path)

    apts: dict[str, APT] = {}
    ttps: dict[str, TTP] = {}
    stix_to_apt: dict[str, str] = {}
    stix_to_ttp: dict[str, str] = {}
    uses_rels: list[tuple[str, str]] = []

    with open(mitre_path, "rb") as f:
        for obj in ijson.items(f, "objects.item"):
            obj_type = obj.get("type", "")

            if obj_type == "intrusion-set":
                apt = _parse_intrusion_set(obj, alias_to_country)
                if apt and apt.mitre_id:
                    apts[apt.mitre_id] = apt
                    stix_to_apt[obj["id"]] = apt.mitre_id

            elif obj_type == "attack-pattern":
                ttp = _parse_attack_pattern(obj)
                if ttp and ttp.mitre_id:
                    ttps[ttp.mitre_id] = ttp
                    stix_to_ttp[obj["id"]] = ttp.mitre_id

            elif obj_type == "relationship":
                if obj.get("relationship_type") == "uses":
                    uses_rels.append((obj["source_ref"], obj["target_ref"]))

    # link APTs to TTPs via "uses" relationships
    for src, tgt in uses_rels:
        apt_id = stix_to_apt.get(src)
        ttp_id = stix_to_ttp.get(tgt)
        if apt_id and ttp_id and apt_id in apts:
            apts[apt_id].technique_ids.append(ttp_id)

    logger.info("loaded %d APTs, %d TTPs", len(apts), len(ttps))
    return AttackGraph(apts=apts, ttps=ttps)

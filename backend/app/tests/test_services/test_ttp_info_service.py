"""
Module for test MITRE ATT&CK lookups, UKC phase mapping,
and APT uses next-TTP suggestions.
"""

import pytest

from app.mitre_loader import APT, TTP, AttackGraph, build_apt_chain_index
from app.services.ttp_info_service import TTPInfoService


def _ttp(
    mitre_id: str,
    name: str,
    description: str,
    tactic_ids: list[str],
) -> TTP:
    return TTP(
        mitre_id=mitre_id,
        stix_id=f"attack-pattern--{mitre_id}",
        name=name,
        description=description,
        references=[],
        tactic_ids=tactic_ids,
    )


@pytest.fixture(name="graph")
def fixture_graph() -> AttackGraph:
    ttps = {
        "T1566": _ttp(
            "T1566",
            "Phishing",
            "spearphishing link, user click, credential phish",
            ["initial-access"],
        ),
        "T1059": _ttp(
            "T1059",
            "Command and Scripting Interpreter",
            "executes code via shell",
            ["execution"],
        ),
        "T1204": _ttp(
            "T1204",
            "User Execution",
            "user opens malicious attachment, execution of code",
            ["execution"],
        ),
        "T1078": _ttp(
            "T1078",
            "Valid Accounts",
            "uses stolen credentials for persistence",
            ["persistence"],
        ),
        "T1048": _ttp(
            "T1048",
            "Exfiltration Over Alternative Protocol",
            "removes data from the network",
            ["exfiltration"],
        ),
        "T1572": _ttp(
            "T1572",
            "Protocol Tunneling",
            "proxy tunnel socks traffic through controlled host",
            ["lateral-movement"],
        ),
        "T1021": _ttp(
            "T1021",
            "Remote Services",
            "uses remote desktop for access",
            ["lateral-movement"],
        ),
        "T0000": _ttp(
            "T0000",
            "Unmapped Technique",
            "no tactic mapping at all",
            ["non-existent-tactic"],
        ),
    }
    apts = {
        "G0001": APT(
            mitre_id="G0001",
            stix_id="intrusion-set--g0001",
            name="apt-one",
            source_country="CN",
            alt_names=[],
            technique_ids=["T1566", "T1059", "T1078"],
        ),
        "G0002": APT(
            mitre_id="G0002",
            stix_id="intrusion-set--g0002",
            name="apt-two",
            source_country="RU",
            alt_names=[],
            technique_ids=["T1566", "T1059", "T1048"],
        ),
        "G0003": APT(
            mitre_id="G0003",
            stix_id="intrusion-set--g0003",
            name="apt-three",
            source_country="IR",
            alt_names=[],
            technique_ids=["T1059", "T1204"],
        ),
    }
    return AttackGraph(apts=apts, ttps=ttps)


@pytest.fixture(name="service")
def fixture_service(graph: AttackGraph) -> TTPInfoService:
    svc = TTPInfoService(graph)
    index = build_apt_chain_index(graph, svc.get_phase_for_ttp)
    return TTPInfoService(graph, index)


def test_get_phase_for_single_phase_tactic(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    assert svc.get_phase_for_ttp("T1059") == ["Execution"]
    assert svc.get_phase_for_ttp("T1078") == ["Persistence"]


def test_get_phase_for_shared_tactic_uses_keywords(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    assert svc.get_phase_for_ttp("T1566") == ["Social Engineering"]
    assert svc.get_phase_for_ttp("T1572") == ["Pivoting", "Lateral Movement"]
    assert svc.get_phase_for_ttp("T1021") == ["Lateral Movement"]


def test_get_phase_for_unknown_ttp(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    assert svc.get_phase_for_ttp("T9999") == []
    assert svc.get_phase_for_ttp("T0000") == []


def test_get_ttps_by_phase_splits_shared_tactic(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    social = {t.mitre_id for t in svc.get_ttps_by_phase("Social Engineering")}
    delivery = {t.mitre_id for t in svc.get_ttps_by_phase("Delivery")}
    assert "T1566" in social
    assert "T1566" not in delivery
    assert {t.mitre_id for t in svc.get_ttps_by_phase("Execution")} == {
        "T1059",
        "T1204",
    }


def test_get_ttps_by_unknown_phase(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    assert svc.get_ttps_by_phase("No Such Phase") == []


def test_chain_index_ranks_by_co_use(service: TTPInfoService) -> None:
    assert service._chain_index is not None
    top = service._chain_index.suggest("T1566", limit=10)
    both_apts_use_t1059 = 2
    assert top[0].mitre_id == "T1059"
    assert top[0].apt_count == both_apts_use_t1059
    assert service._chain_index.get_all("T9999") == []
    assert service._chain_index.suggest("T9999") == []


def test_suggest_next_ttps_forward_only(service: TTPInfoService) -> None:
    results = service.suggest_next_ttps("T1566")
    assert results
    assert results[0]["mitre_id"] == "T1059"
    # nothing from a UKC phase strictly before Social Engineering
    assert {r["mitre_id"] for r in results} == {"T1059", "T1078", "T1048"}
    # late-phase technique has no forward suggestions in this fixture
    assert service.suggest_next_ttps("T1048") == []


def test_suggest_next_ttps_limit_and_filters(service: TTPInfoService) -> None:
    limited = service.suggest_next_ttps("T1566", limit=1)
    assert [r["mitre_id"] for r in limited] == ["T1059"]
    same_phase = service.suggest_next_ttps("T1059", same_phase_only=True)
    assert {r["mitre_id"] for r in same_phase} == {"T1204"}
    targeted = service.suggest_next_ttps("T1566", target_phase="Persistence")
    assert [r["mitre_id"] for r in targeted] == ["T1078"]


def test_suggest_next_ttps_empty_cases(graph: AttackGraph) -> None:
    assert TTPInfoService(graph).suggest_next_ttps("T1566") == []
    svc = TTPInfoService(
        graph, build_apt_chain_index(graph, TTPInfoService(graph).get_phase_for_ttp)
    )
    assert svc.suggest_next_ttps("T9999") == []
    assert svc.suggest_next_ttps("T0000") == []


def test_get_ttps_by_apt_and_info(graph: AttackGraph) -> None:
    svc = TTPInfoService(graph)
    assert {t.mitre_id for t in svc.get_ttps_by_apt("G0001")} == {
        "T1566",
        "T1059",
        "T1078",
    }
    assert svc.get_ttps_by_apt("G9999") == []
    assert svc.get_ttp_info("T1059") is not None
    assert svc.get_ttp_info("T9999") is None

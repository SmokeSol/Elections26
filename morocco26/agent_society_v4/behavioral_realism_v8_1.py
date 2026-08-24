from __future__ import annotations

"""Behavioral-realism gates V8.1 - testability aware.

Additive to `behavioral_realism`, which is left untouched.

Two corrections, both forced by the V9 Ain Chock pilot:

1. A gate the environment cannot feed is `NOT_TESTABLE_MISSING_DATA`, not FAIL.
   BR1-REGIONAL failed in both arms because the regional surface was the local
   ballot with the candidate erased. Charging the model with that degeneracy
   confuses a data gap with a behavioural defect.

2. A LOCAL-only run has no regional simplex at all. The V8 auditor raises on the
   missing key; V8.1 scopes every regional measurement behind the certificate.
"""

import math
import pathlib
import statistics
from collections import Counter
from typing import Any, Mapping, Sequence

from .behavioral_realism import (
    BehavioralRealismError,
    _entropy,
    _fingerprint,
    _first_person_pov,
    _l1,
    _normalized_opening,
    _simplex,
    _technical_pov_tokens,
    _winner,
    discover_run_rows,
)
from .p3_data_layers_v1 import NOT_TESTABLE, TESTABLE

AUDIT_V8_1_SCHEMA = "AGENT_SOCIETY_BEHAVIORAL_REALISM_AUDIT_V1_1"


def _testability(certificate: Mapping[str, Any] | None) -> dict[str, str]:
    if not certificate:
        return {}
    return dict(certificate.get("gate_testability") or {})


def _not_testable(gate: str, testability: Mapping[str, str]) -> bool:
    return str(testability.get(gate) or TESTABLE) == NOT_TESTABLE


def audit_rows_v8_1(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_rows: int = 32,
    certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    testability = _testability(certificate)
    regional_expected = not _not_testable("BR1_REGIONAL", testability)

    if len(rows) != expected_rows:
        br0 = {"status": "FAIL_ROW_COUNT", "observed": len(rows), "expected": expected_rows}
    else:
        br0 = {"status": "PASS", "observed": len(rows), "expected": expected_rows}
    archetypes = [str(row.get("weighted_archetype_id") or "") for row in rows]
    if any(not item for item in archetypes) or len(set(archetypes)) != len(archetypes):
        br0 = {**br0, "status": "FAIL_ARCHETYPE_IDENTITY"}

    local_vectors: list[dict[str, float]] = []
    regional_vectors: list[dict[str, float]] = []
    turnout: list[float] = []
    povs: list[str] = []
    legacy_rationale_rows = 0
    stray_regional_rows = 0
    for index, row in enumerate(rows):
        local_vectors.append(_simplex(row.get("local_party_probabilities"), f"row[{index}].local"))
        if regional_expected:
            regional_vectors.append(
                _simplex(row.get("regional_party_probabilities"), f"row[{index}].regional")
            )
        elif row.get("regional_party_probabilities") is not None:
            stray_regional_rows += 1
        try:
            value = float(row.get("turnout_probability"))
        except (TypeError, ValueError) as exc:
            raise BehavioralRealismError(f"row[{index}].turnout_probability invalid") from exc
        if not 0.0 <= value <= 1.0:
            raise BehavioralRealismError(f"row[{index}].turnout_probability outside [0,1]")
        turnout.append(value)
        if isinstance(row.get("pov_fr"), str):
            povs.append(str(row["pov_fr"]))
        elif isinstance(row.get("observable_rationale"), Mapping):
            legacy_rationale_rows += 1
            povs.append("")
        else:
            povs.append("")

    if stray_regional_rows:
        br0 = {
            **br0,
            "status": "FAIL_REGIONAL_VOTE_ON_MISSING_SURFACE",
            "rows_with_regional_vote_but_no_regional_surface": stray_regional_rows,
        }

    unique_local = len({_fingerprint(item) for item in local_vectors})
    local_l1 = [
        _l1(local_vectors[i], local_vectors[j])
        for i in range(len(local_vectors))
        for j in range(i + 1, len(local_vectors))
    ]
    br1_local = {
        "status": "PASS_NONDEGENERATE" if unique_local > 1 else "FAIL_DEGENERATE_LOCAL",
        "unique_local_probability_vectors": unique_local,
        "local_winner_counts": dict(sorted(Counter(_winner(item) for item in local_vectors).items())),
        "mean_local_entropy_bits": round(statistics.fmean(_entropy(item) for item in local_vectors), 6),
        "mean_pairwise_local_l1": round(statistics.fmean(local_l1), 6) if local_l1 else 0.0,
        "mean_top_two_margin": round(
            statistics.fmean(
                sorted(vector.values(), reverse=True)[0] - sorted(vector.values(), reverse=True)[1]
                for vector in local_vectors
            ),
            6,
        ),
        "exact_tie_rows": sum(
            1
            for vector in local_vectors
            if math.isclose(
                sorted(vector.values(), reverse=True)[0],
                sorted(vector.values(), reverse=True)[1],
                abs_tol=1e-12,
            )
        ),
    }

    if regional_expected:
        unique_regional = len({_fingerprint(item) for item in regional_vectors})
        regional_l1 = [
            _l1(regional_vectors[i], regional_vectors[j])
            for i in range(len(regional_vectors))
            for j in range(i + 1, len(regional_vectors))
        ]
        br1_regional = {
            "status": "PASS_NONDEGENERATE" if unique_regional > 1 else "FAIL_DEGENERATE_REGIONAL",
            "unique_regional_probability_vectors": unique_regional,
            "regional_winner_counts": dict(
                sorted(Counter(_winner(item) for item in regional_vectors).items())
            ),
            "mean_regional_entropy_bits": round(
                statistics.fmean(_entropy(item) for item in regional_vectors), 6
            ),
            "mean_pairwise_regional_l1": round(statistics.fmean(regional_l1), 6) if regional_l1 else 0.0,
        }
        split = {
            "status": "MEASURED",
            "rows_with_different_local_and_regional_leader": sum(
                1
                for local, regional in zip(local_vectors, regional_vectors)
                if _winner(local) != _winner(regional)
            ),
        }
    else:
        br1_regional = {
            "status": NOT_TESTABLE,
            "reason": "REGIONAL_SURFACE_STATUS=MISSING: no regional ballot was collected for this snapshot",
        }
        split = {
            "status": NOT_TESTABLE,
            "reason": "split-ticket is undefined without a second, independently informative ballot",
        }

    turnout_unique = len({round(value, 6) for value in turnout})
    br6 = {
        "status": "PASS_NONDEGENERATE" if turnout_unique > 1 else "FAIL_DEGENERATE_TURNOUT",
        "unique_turnout_values": turnout_unique,
        "turnout_mean": round(statistics.fmean(turnout), 6),
        "turnout_pstdev": round(statistics.pstdev(turnout) if len(turnout) > 1 else 0.0, 6),
    }

    pov_present = sum(bool(text.strip()) for text in povs)
    first_person = sum(_first_person_pov(text) for text in povs if text.strip())
    technical_findings = {
        archetypes[index]: _technical_pov_tokens(text)
        for index, text in enumerate(povs)
        if text.strip() and _technical_pov_tokens(text)
    }
    opening_counts = Counter(_normalized_opening(text) for text in povs if text.strip())
    if legacy_rationale_rows:
        br8_status = "FAIL_LEGACY_ANALYST_RATIONALE"
    elif pov_present != len(rows):
        br8_status = "FAIL_POV_MISSING"
    elif first_person != len(rows):
        br8_status = "FAIL_NOT_FIRST_PERSON"
    elif technical_findings:
        br8_status = "FAIL_RESEARCH_ONTOLOGY_IN_VOICE"
    else:
        br8_status = "PASS"
    br8 = {
        "status": br8_status,
        "pov_rows": pov_present,
        "unique_povs": len({text.strip() for text in povs if text.strip()}),
        "first_person_rows": first_person,
        "legacy_observable_rationale_rows": legacy_rationale_rows,
        "technical_ontology_findings": technical_findings,
        "max_identical_normalized_opening_count": max(opening_counts.values(), default=0),
    }

    def scoped(gate: str, payload: dict[str, Any], required_layer_gate: str) -> dict[str, Any]:
        if _not_testable(required_layer_gate, testability):
            return {
                "status": NOT_TESTABLE,
                "reason": f"{required_layer_gate} cannot be fed by the certified data layers",
            }
        return payload

    br2 = {
        "status": "NOT_TESTED",
        "required_test": "PAIRED_PERSONA_SENSITIVITY: same world, controlled voter-state perturbation",
    }
    br3 = scoped(
        "BR3",
        {
            "status": "NOT_TESTED",
            "required_test": "PAIRED_CANDIDATE_SENSITIVITY: UNKNOWN->KNOWN candidate on the same archetypes",
        },
        "BR3_CANDIDATE",
    )
    br4 = scoped(
        "BR4",
        {
            "status": "NOT_TESTED",
            "required_test": "PAIRED_PROGRAMME_SENSITIVITY: change one visible programme position",
        },
        "BR4_PROGRAMME",
    )
    br5 = scoped(
        "BR5",
        {
            "status": "NOT_TESTED",
            "required_test": "PARTY_MEMORY_SENSITIVITY: prior support/rejection anchors must move behaviour",
        },
        "BR5_PARTY_MEMORY",
    )
    br7 = {
        "status": "NOT_TESTED",
        "required_test": "NONINFORMATIVE_PLACEBO: irrelevant packet perturbation should have near-zero effect",
    }

    testable_verdicts = {
        "BR0_integrity": br0["status"],
        "BR1_local": br1_local["status"],
        "BR1_regional": br1_regional["status"],
        "BR6_turnout_mechanism": br6["status"],
        "BR8_pov_fidelity": br8["status"],
    }
    failed = sorted(
        name
        for name, status in testable_verdicts.items()
        if status not in {"PASS", "PASS_NONDEGENERATE", NOT_TESTABLE}
    )
    not_testable = sorted(name for name, status in testable_verdicts.items() if status == NOT_TESTABLE)
    return {
        "schema_version": AUDIT_V8_1_SCHEMA,
        "rows": len(rows),
        "ballots_audited": ["LOCAL"] + (["REGIONAL"] if regional_expected else []),
        "data_layer_certificate_sha256": (certificate or {}).get("certificate_sha256"),
        "gate_testability": dict(sorted(testability.items())),
        "BR0_integrity": br0,
        "BR1_local_heterogeneity": br1_local,
        "BR1_regional_heterogeneity": br1_regional,
        "BR2_persona_sensitivity": br2,
        "BR3_candidate_sensitivity": br3,
        "BR4_programme_sensitivity": br4,
        "BR5_party_memory_sensitivity": br5,
        "BR6_turnout_mechanism": br6,
        "BR7_placebo": br7,
        "BR8_pov_fidelity": br8,
        "split_ticket": split,
        "failed_testable_gates": failed,
        "not_testable_gates": not_testable,
        "pilot_pass_over_testable_gates": not failed,
        "interpretation_boundary": (
            "pilot_pass_over_testable_gates says the model behaved non-degenerately on the "
            "gates the environment could actually feed. It says nothing about the gates listed "
            "in not_testable_gates, and nothing about external Moroccan realism."
        ),
    }


def audit_run_v8_1(
    run_root: pathlib.Path,
    *,
    expected_rows: int = 32,
    certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return audit_rows_v8_1(
        discover_run_rows(run_root), expected_rows=expected_rows, certificate=certificate
    )

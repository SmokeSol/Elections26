from __future__ import annotations

"""Behavioral-realism gates for small Agent Society pilots.

The gates detect degenerate LLM behavior; they do not certify that synthetic
voters are real Moroccan voters. Promotion beyond a pilot additionally requires
paired perturbation tests and historical out-of-sample validation.
"""

import json
import math
import pathlib
import re
import statistics
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from .behavioral_mind_v8 import TECHNICAL_OUTPUT_ONTOLOGY_TOKENS

AUDIT_SCHEMA = "AGENT_SOCIETY_BEHAVIORAL_REALISM_AUDIT_V1"


class BehavioralRealismError(ValueError):
    pass


def _simplex(value: Any, label: str) -> dict[str, float]:
    if not isinstance(value, Mapping) or len(value) < 2:
        raise BehavioralRealismError(f"{label} is not a valid probability object")
    result: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool):
            raise BehavioralRealismError(f"{label}.{key} is boolean")
        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise BehavioralRealismError(f"{label}.{key} is not numeric") from exc
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise BehavioralRealismError(f"{label}.{key} outside [0,1]")
        result[str(key)] = number
    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise BehavioralRealismError(f"{label} does not sum to one")
    return result


def _fingerprint(vector: Mapping[str, float], digits: int = 6) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(key), round(float(value), digits)) for key, value in vector.items()))


def _winner(vector: Mapping[str, float]) -> str:
    return sorted(vector.items(), key=lambda pair: (-pair[1], pair[0]))[0][0]


def _entropy(vector: Mapping[str, float]) -> float:
    return -sum(value * math.log(value, 2) for value in vector.values() if value > 0)


def _l1(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    keys = set(a) | set(b)
    return sum(abs(float(a.get(key, 0.0)) - float(b.get(key, 0.0))) for key in keys)


def _first_person_pov(text: str) -> bool:
    value = " " + str(text or "").lower() + " "
    return bool(re.search(r"\bje\b|\bj['’]|\bmoi\b|\bmon\b|\bma\b|\bmes\b", value))


def _technical_pov_tokens(text: str) -> list[str]:
    lower = str(text or "").lower()
    return [token for token in TECHNICAL_OUTPUT_ONTOLOGY_TOKENS if token in lower]


def _normalized_opening(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    value = re.sub(r"\d+(?:[.,]\d+)?", "#", value)
    return value[:120]


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BehavioralRealismError(f"invalid JSONL {path}:{number}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise BehavioralRealismError(f"row {number} is not an object")
        rows.append(dict(value))
    return rows


def discover_run_rows(run_root: pathlib.Path) -> list[dict[str, Any]]:
    run_root = run_root.expanduser().resolve()
    output_root = run_root / "outputs"
    if not output_root.is_dir():
        raise BehavioralRealismError(f"outputs directory missing under {run_root}")
    paths = sorted(path for path in output_root.rglob("*.jsonl") if "all_outputs" not in path.name)
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(load_jsonl(path))
    if not rows:
        raise BehavioralRealismError("no output rows discovered")
    return rows


def audit_rows(rows: Sequence[Mapping[str, Any]], *, expected_rows: int = 32) -> dict[str, Any]:
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
    for i, row in enumerate(rows):
        local_vectors.append(_simplex(row.get("local_party_probabilities"), f"row[{i}].local"))
        regional_vectors.append(_simplex(row.get("regional_party_probabilities"), f"row[{i}].regional"))
        try:
            t = float(row.get("turnout_probability"))
        except (TypeError, ValueError) as exc:
            raise BehavioralRealismError(f"row[{i}].turnout_probability invalid") from exc
        if not 0.0 <= t <= 1.0:
            raise BehavioralRealismError(f"row[{i}].turnout_probability outside [0,1]")
        turnout.append(t)
        if isinstance(row.get("pov_fr"), str):
            povs.append(str(row["pov_fr"]))
        elif isinstance(row.get("observable_rationale"), Mapping):
            legacy_rationale_rows += 1
            povs.append("")
        else:
            povs.append("")

    local_fps = [_fingerprint(item) for item in local_vectors]
    regional_fps = [_fingerprint(item) for item in regional_vectors]
    unique_local = len(set(local_fps))
    unique_regional = len(set(regional_fps))
    br1_status = "PASS_NONDEGENERATE"
    reasons = []
    if unique_local <= 1:
        br1_status = "FAIL_DEGENERATE_LOCAL"
        reasons.append("all voter profiles produced the same LOCAL probability vector")
    if unique_regional <= 1:
        br1_status = "FAIL_DEGENERATE_BOTH" if unique_local <= 1 else "FAIL_DEGENERATE_REGIONAL"
        reasons.append("all voter profiles produced the same REGIONAL probability vector")
    br1 = {
        "status": br1_status,
        "unique_local_probability_vectors": unique_local,
        "unique_regional_probability_vectors": unique_regional,
        "local_winner_counts": dict(sorted(Counter(_winner(item) for item in local_vectors).items())),
        "regional_winner_counts": dict(sorted(Counter(_winner(item) for item in regional_vectors).items())),
        "mean_local_entropy_bits": round(statistics.fmean(_entropy(item) for item in local_vectors), 6),
        "mean_regional_entropy_bits": round(statistics.fmean(_entropy(item) for item in regional_vectors), 6),
        "reasons": reasons,
    }

    local_l1 = []
    regional_l1 = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            local_l1.append(_l1(local_vectors[i], local_vectors[j]))
            regional_l1.append(_l1(regional_vectors[i], regional_vectors[j]))
    br1["mean_pairwise_local_l1"] = round(statistics.fmean(local_l1), 6) if local_l1 else 0.0
    br1["mean_pairwise_regional_l1"] = round(statistics.fmean(regional_l1), 6) if regional_l1 else 0.0

    turnout_unique = len({round(value, 6) for value in turnout})
    turnout_std = statistics.pstdev(turnout) if len(turnout) > 1 else 0.0
    br6 = {
        "status": "PASS_NONDEGENERATE" if turnout_unique > 1 else "FAIL_DEGENERATE_TURNOUT",
        "unique_turnout_values": turnout_unique,
        "turnout_mean": round(statistics.fmean(turnout), 6),
        "turnout_pstdev": round(turnout_std, 6),
    }

    pov_present = sum(bool(text.strip()) for text in povs)
    first_person = sum(_first_person_pov(text) for text in povs if text.strip())
    technical_findings = {
        archetypes[i]: _technical_pov_tokens(text)
        for i, text in enumerate(povs)
        if text.strip() and _technical_pov_tokens(text)
    }
    opening_counts = Counter(_normalized_opening(text) for text in povs if text.strip())
    max_opening_repetition = max(opening_counts.values(), default=0)
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
        "first_person_rows": first_person,
        "legacy_observable_rationale_rows": legacy_rationale_rows,
        "technical_ontology_findings": technical_findings,
        "max_identical_normalized_opening_count": max_opening_repetition,
    }

    br2 = {"status": "NOT_TESTED", "required_test": "PAIRED_PERSONA_SENSITIVITY: same world, controlled voter-state perturbation"}
    br3 = {"status": "NOT_TESTED", "required_test": "PAIRED_CANDIDATE_SENSITIVITY: UNKNOWN->KNOWN candidate; local-oriented voters should move more than party/program-oriented voters"}
    br4 = {"status": "NOT_TESTED", "required_test": "PAIRED_PROGRAMME_SENSITIVITY: change one visible programme fact and test heterogeneous response"}
    br5 = {"status": "NOT_TESTED", "required_test": "PARTY_MEMORY_SENSITIVITY: prior support/rejection anchors must affect behavior without deterministically forcing it"}
    br7 = {"status": "NOT_TESTED", "required_test": "NONINFORMATIVE_PLACEBO: irrelevant packet perturbation should have near-zero effect"}

    pilot_integrity_pass = br0["status"] == "PASS"
    pilot_behavior_pass = (
        br1["status"] == "PASS_NONDEGENERATE"
        and br6["status"] == "PASS_NONDEGENERATE"
        and br8["status"] == "PASS"
    )
    scale_validation_pass = all(gate["status"] == "PASS" for gate in (br2, br3, br4, br5, br7))
    return {
        "schema_version": AUDIT_SCHEMA,
        "rows": len(rows),
        "BR0_integrity": br0,
        "BR1_partisan_heterogeneity": br1,
        "BR2_persona_sensitivity": br2,
        "BR3_candidate_sensitivity": br3,
        "BR4_programme_sensitivity": br4,
        "BR5_party_memory_sensitivity": br5,
        "BR6_turnout_mechanism": br6,
        "BR7_placebo": br7,
        "BR8_pov_fidelity": br8,
        "pilot_pass": pilot_integrity_pass and pilot_behavior_pass,
        "scale_allowed": pilot_integrity_pass and pilot_behavior_pass and scale_validation_pass,
        "interpretation_boundary": "PASS detects non-degenerate internally coherent synthetic behavior; it does not prove external Moroccan voter realism.",
    }


def audit_run(run_root: pathlib.Path, *, expected_rows: int = 32) -> dict[str, Any]:
    return audit_rows(discover_run_rows(run_root), expected_rows=expected_rows)


def paired_delta(
    base_rows: Sequence[Mapping[str, Any]],
    treatment_rows: Sequence[Mapping[str, Any]],
    *,
    ballot: str,
    party_id: str,
) -> dict[str, Any]:
    """Measure a paired synthetic response for BR2-BR4 experiments."""
    key = "local_party_probabilities" if ballot.upper() == "LOCAL" else "regional_party_probabilities"
    base = {str(row.get("weighted_archetype_id")): row for row in base_rows}
    treatment = {str(row.get("weighted_archetype_id")): row for row in treatment_rows}
    if set(base) != set(treatment) or not base:
        raise BehavioralRealismError("paired rows do not contain the same archetypes")
    deltas = []
    for archetype in sorted(base):
        b = _simplex(base[archetype].get(key), f"base.{archetype}.{key}")
        t = _simplex(treatment[archetype].get(key), f"treatment.{archetype}.{key}")
        if party_id not in b or party_id not in t:
            raise BehavioralRealismError(f"party {party_id} absent from paired ballot")
        deltas.append(float(t[party_id]) - float(b[party_id]))
    return {
        "ballot": ballot.upper(),
        "party_id": party_id,
        "archetypes": len(deltas),
        "mean_probability_delta": round(statistics.fmean(deltas), 6),
        "min_probability_delta": round(min(deltas), 6),
        "max_probability_delta": round(max(deltas), 6),
        "nonzero_delta_rows": sum(abs(value) > 1e-9 for value in deltas),
    }

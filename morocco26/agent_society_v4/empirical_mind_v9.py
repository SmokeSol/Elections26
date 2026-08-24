from __future__ import annotations

"""Empirical Moroccan Mind V9.

V8 defines the cognitive architecture. V9 adds a strict evidence hierarchy and
an explicit catalogue of human dimensions. It never upgrades population or
territorial evidence into an observed individual fact.
"""

import copy
from datetime import date
import json
import math
from typing import Any, Mapping, Sequence

from .empirical_priors_v9 import (
    ALLOWED_EPISTEMIC_STATUSES,
    CALIBRATED_STATUS,
    DIRECT_EVIDENCE_ONLY_DIMENSIONS,
    PriorSelection,
    deterministic_draw,
    dimension_index,
    select_prior,
    sha256_json,
    source_index,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)

EMPIRICAL_MIND_SCHEMA = "AGENT_SOCIETY_EMPIRICAL_MOROCCAN_MIND_V9"
EMPIRICAL_DIMENSION_STATE_SCHEMA = "AGENT_SOCIETY_EMPIRICAL_DIMENSION_STATE_V1"

EPISTEMIC_PRECEDENCE = {
    "OBSERVED_INDIVIDUAL": 60,
    "OBSERVED_HOUSEHOLD": 50,
    "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY": 40,
    "ECOLOGICAL_CONTEXT_ONLY": 30,
    "REGISTERED_EXPERIMENTAL_PRIOR": 20,
    "UNKNOWN": 0,
}

MODEL_HIDDEN_KEYS = {
    "source_ids",
    "source_url",
    "source_urls",
    "provenance",
    "raw_value",
    "posterior_distribution",
    "conditioning_fields",
    "audit",
    "processed_artifact_sha256",
}

FORBIDDEN_CULTURAL_INVENTION_KEYS = {
    "invented_clientelism",
    "invented_notable_network",
    "invented_tribal_alignment",
    "invented_family_recommendation",
    "invented_candidate_reputation",
    "invented_party_affinity",
    "invented_party_rejection",
}


class EmpiricalMindError(ValueError):
    pass


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise EmpiricalMindError(f"invalid ISO date {value!r}") from exc


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _normalize_value(value: Any, spec: Mapping[str, Any]) -> tuple[Any, str | None]:
    value_type = str(spec.get("value_type") or "CATEGORICAL")
    if value_type in {"UNIT_INTERVAL", "SIGNED_UNIT_INTERVAL"}:
        number = _finite_number(value)
        if number is None:
            return None, None
        if 1.0 < number <= 100.0 and value_type == "UNIT_INTERVAL":
            number /= 100.0
        if value_type == "UNIT_INTERVAL" and not 0.0 <= number <= 1.0:
            return None, None
        if value_type == "SIGNED_UNIT_INTERVAL" and not -1.0 <= number <= 1.0:
            if 0.0 <= number <= 1.0:
                number = 2.0 * number - 1.0
            else:
                return None, None
        if value_type == "SIGNED_UNIT_INTERVAL":
            band = "NEGATIVE" if number < -0.33 else "POSITIVE" if number > 0.33 else "MIXED_OR_NEUTRAL"
        else:
            band = "LOW" if number < 0.34 else "HIGH" if number >= 0.67 else "MEDIUM"
        return round(number, 6), band
    if value_type == "BOOLEAN":
        if isinstance(value, bool):
            return value, "YES" if value else "NO"
        if str(value).upper() in {"YES", "TRUE", "1"}:
            return True, "YES"
        if str(value).upper() in {"NO", "FALSE", "0"}:
            return False, "NO"
        return None, None
    if value_type == "COUNT":
        number = _finite_number(value)
        if number is None or number < 0:
            return None, None
        return int(round(number)), str(int(round(number)))
    if value_type == "CATEGORICAL":
        text = str(value).strip() if value is not None else ""
        if not text or text.upper() in {"UNKNOWN", "MISSING", "NOT_FOUND", "UNVERIFIED"}:
            return None, None
        categories = [str(x) for x in spec.get("categories") or []]
        if categories and text not in categories:
            upper_map = {item.upper(): item for item in categories}
            if text.upper() not in upper_map:
                return None, None
            text = upper_map[text.upper()]
        return text, text
    if value_type == "TEXT":
        text = str(value).strip() if value is not None else ""
        return (text, "PRESENT") if text else (None, None)
    return None, None


def _first_field(container: Mapping[str, Any], fields: Sequence[str]) -> tuple[Any, str | None]:
    for field in fields:
        if field in container and container.get(field) is not None:
            return container.get(field), field
    return None, None


def _unknown_state(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": "UNKNOWN",
        "value": None,
        "band_or_category": "UNKNOWN",
        "uncertainty": "MAXIMAL_OR_UNQUANTIFIED",
        "model_visibility": "UNKNOWN_MARKER",
        "behavioral_use": "DO_NOT_IMPUTE",
        "source_ids": [],
        "known_as_of": None,
        "conditioning_fields": [],
        "individual_fact_claimed": False,
    }


def _observed_state(
    *,
    spec: Mapping[str, Any],
    value: Any,
    source_field: str,
    household: bool,
    snapshot_date: str,
) -> dict[str, Any]:
    normalized, band = _normalize_value(value, spec)
    if normalized is None:
        return _unknown_state(spec)
    status = "OBSERVED_HOUSEHOLD" if household else "OBSERVED_INDIVIDUAL"
    visibility = (spec.get("model_visibility") or {}).get(
        "observed", "DIRECT_STATEMENT"
    )
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": status,
        "value": normalized,
        "band_or_category": band,
        "uncertainty": "SOURCE_MEASUREMENT_UNCERTAINTY",
        "model_visibility": visibility,
        "behavioral_use": str(spec.get("behavioral_use") or "SOFT_CONTEXT"),
        "source_ids": [f"INPUT_FIELD:{source_field}"],
        "known_as_of": snapshot_date,
        "conditioning_fields": [],
        "source_field": source_field,
        "individual_fact_claimed": not household,
        "household_fact_claimed": household,
    }


def _survey_state(
    *,
    spec: Mapping[str, Any],
    selection: PriorSelection,
    snapshot_id: str,
    voter_id: str,
    replicate_id: str,
) -> dict[str, Any]:
    draw = deterministic_draw(
        selection,
        snapshot_id=snapshot_id,
        voter_id=voter_id,
        replicate_id=replicate_id,
    )
    visibility = (spec.get("model_visibility") or {}).get(
        "survey_prior", "HIDDEN_CALIBRATION_ONLY"
    )
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY",
        "value": draw,
        "band_or_category": draw,
        "uncertainty": "POSTERIOR_DISTRIBUTION_RETAINED",
        "model_visibility": visibility,
        "behavioral_use": str(spec.get("behavioral_use") or "SOFT_CONTEXT"),
        "source_ids": list(selection.source_ids),
        "known_as_of": selection.known_as_of,
        "conditioning_fields": list(selection.conditioning_fields),
        "prior_id": selection.prior_id,
        "prior_cell_id": selection.cell_id,
        "posterior_distribution": dict(selection.distribution),
        "support_n": selection.support_n,
        "effective_sample_size": selection.effective_sample_size,
        "replicate_id": replicate_id,
        "individual_fact_claimed": False,
        "synthetic_latent_state_claimed": True,
    }


def _ecological_state(
    *,
    spec: Mapping[str, Any],
    value: Any,
    source_field: str,
    snapshot_date: str,
) -> dict[str, Any]:
    normalized, band = _normalize_value(value, spec)
    if normalized is None:
        return _unknown_state(spec)
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": "ECOLOGICAL_CONTEXT_ONLY",
        "value": None,
        "context_value": normalized,
        "band_or_category": band,
        "uncertainty": "NOT_AN_INDIVIDUAL_MEASUREMENT",
        "model_visibility": (spec.get("model_visibility") or {}).get(
            "ecological", "CONTEXT_ONLY"
        ),
        "behavioral_use": "CONTEXT_ONLY_NOT_INDIVIDUAL_TRAIT",
        "source_ids": [f"CONTEXT_FIELD:{source_field}"],
        "known_as_of": snapshot_date,
        "conditioning_fields": [],
        "source_field": source_field,
        "individual_fact_claimed": False,
    }


def resolve_dimension(
    *,
    voter: Mapping[str, Any],
    household: Mapping[str, Any],
    ecological_context: Mapping[str, Any],
    spec: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_id: str,
    snapshot_date: str,
    replicate_id: str,
) -> dict[str, Any]:
    value, field = _first_field(voter, tuple(map(str, spec.get("individual_source_fields") or [])))
    if field:
        state = _observed_state(
            spec=spec,
            value=value,
            source_field=field,
            household=False,
            snapshot_date=snapshot_date,
        )
        if state["epistemic_status"] != "UNKNOWN":
            return state
    value, field = _first_field(
        household, tuple(map(str, spec.get("household_source_fields") or []))
    )
    if field:
        state = _observed_state(
            spec=spec,
            value=value,
            source_field=field,
            household=True,
            snapshot_date=snapshot_date,
        )
        if state["epistemic_status"] != "UNKNOWN":
            return state
    dimension_id = str(spec["dimension_id"])
    if prior_pack and prior_pack.get("status") == CALIBRATED_STATUS and spec.get("survey_prior_allowed"):
        selection = select_prior(prior_pack, dimension_id=dimension_id, voter=voter)
        if selection:
            return _survey_state(
                spec=spec,
                selection=selection,
                snapshot_id=snapshot_id,
                voter_id=str(voter.get("weighted_archetype_id") or voter.get("archetype_id") or voter.get("cell_id") or "UNKNOWN"),
                replicate_id=replicate_id,
            )
    value, field = _first_field(
        ecological_context,
        tuple(map(str, spec.get("ecological_context_fields") or [])),
    )
    if field:
        return _ecological_state(
            spec=spec,
            value=value,
            source_field=field,
            snapshot_date=snapshot_date,
        )
    return _unknown_state(spec)


def _strip_hidden(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): _strip_hidden(v)
            for k, v in value.items()
            if str(k) not in MODEL_HIDDEN_KEYS
        }
    if isinstance(value, list):
        return [_strip_hidden(item) for item in value]
    return copy.deepcopy(value)


def _render_statement(state: Mapping[str, Any], spec: Mapping[str, Any]) -> str | None:
    visibility = str(state.get("model_visibility") or "")
    if visibility not in {"DIRECT_STATEMENT", "PROBABILISTIC_CONTEXT", "CONTEXT_ONLY"}:
        return None
    template = str((spec.get("rendering") or {}).get("fr") or "").strip()
    if not template:
        return None
    category = str(state.get("band_or_category") or "UNKNOWN")
    if state.get("epistemic_status") == "ECOLOGICAL_CONTEXT_ONLY":
        prefix = "Dans ton environnement, "
    elif state.get("epistemic_status") == "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY":
        prefix = "Dans cette réplique synthétique calibrée sur des personnes comparables, "
    else:
        prefix = ""
    return prefix + template.replace("{value}", category.lower().replace("_", " "))


def assert_no_cultural_fabrication(mind: Mapping[str, Any]) -> None:
    text = json.dumps(mind, ensure_ascii=False, sort_keys=True).lower()
    forbidden_true = [
        key
        for key in FORBIDDEN_CULTURAL_INVENTION_KEYS
        if f'"{key}": true' in text
    ]
    if forbidden_true:
        raise EmpiricalMindError(
            f"mind claims invented cultural mechanisms: {sorted(forbidden_true)}"
        )
    dimensions = mind.get("dimensions") or {}
    for dimension_id in DIRECT_EVIDENCE_ONLY_DIMENSIONS:
        state = dimensions.get(dimension_id)
        if not isinstance(state, Mapping):
            continue
        if state.get("epistemic_status") not in {
            "OBSERVED_INDIVIDUAL",
            "OBSERVED_HOUSEHOLD",
            "UNKNOWN",
        }:
            raise EmpiricalMindError(
                f"{dimension_id} requires direct evidence, got {state.get('epistemic_status')}"
            )


def build_empirical_mind(
    *,
    voter: Mapping[str, Any],
    dimension_registry: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_id: str,
    snapshot_date: str,
    replicate_id: str = "R00",
    household: Mapping[str, Any] | None = None,
    ecological_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_dimension_registry(dimension_registry)
    validate_source_registry(source_registry, snapshot_date=snapshot_date)
    dimensions = dimension_index(dimension_registry)
    sources = source_index(source_registry)
    if prior_pack is not None:
        validate_prior_pack(
            prior_pack,
            source_registry=source_registry,
            dimension_registry=dimension_registry,
            snapshot_date=snapshot_date,
            require_calibrated=False,
        )
    household = household or {}
    ecological_context = ecological_context or {}
    states: dict[str, dict[str, Any]] = {}
    statements: list[str] = []
    counts = {status: 0 for status in ALLOWED_EPISTEMIC_STATUSES}
    for dimension_id in sorted(dimensions):
        spec = dimensions[dimension_id]
        state = resolve_dimension(
            voter=voter,
            household=household,
            ecological_context=ecological_context,
            spec=spec,
            prior_pack=prior_pack,
            snapshot_id=snapshot_id,
            snapshot_date=snapshot_date,
            replicate_id=replicate_id,
        )
        status = str(state["epistemic_status"])
        if status not in counts:
            raise EmpiricalMindError(f"unexpected epistemic status {status}")
        counts[status] += 1
        states[dimension_id] = state
        statement = _render_statement(state, spec)
        if statement:
            statements.append(statement)
    mind = {
        "schema_version": EMPIRICAL_MIND_SCHEMA,
        "status": (
            "EMPIRICAL_MIND_CALIBRATED_PRIORS_PRESENT"
            if prior_pack and prior_pack.get("status") == CALIBRATED_STATUS
            else "EMPIRICAL_MIND_OBSERVED_ONLY_PRIORS_PENDING"
        ),
        "snapshot_id": snapshot_id,
        "snapshot_date": snapshot_date,
        "replicate_id": replicate_id,
        "identity": {
            "weighted_archetype_id": voter.get("weighted_archetype_id")
            or voter.get("archetype_id"),
            "cell_id": voter.get("cell_id"),
        },
        "dimensions": states,
        "model_visible_human_context_fr": statements,
        "epistemic_counts": counts,
        "source_registry_sha256": sha256_json(source_registry),
        "dimension_registry_sha256": sha256_json(dimension_registry),
        "prior_pack_sha256": sha256_json(prior_pack) if prior_pack else None,
        "raw_microdata_embedded": False,
        "population_prior_relabelled_as_individual_fact": False,
        "invented_clientelism": False,
        "invented_notable_network": False,
        "invented_tribal_alignment": False,
        "invented_family_recommendation": False,
        "invented_candidate_reputation": False,
        "invented_party_affinity": False,
        "invented_party_rejection": False,
        "registered_source_count": len(sources),
    }
    assert_no_cultural_fabrication(mind)
    audit = {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_AUDIT_V1",
        "weighted_archetype_id": mind["identity"]["weighted_archetype_id"],
        "epistemic_counts": counts,
        "dimensions": len(states),
        "unknown_share": round(counts["UNKNOWN"] / max(1, len(states)), 6),
        "model_visible_statement_count": len(statements),
        "direct_evidence_only_dimensions": sorted(DIRECT_EVIDENCE_ONLY_DIMENSIONS),
        "mind_sha256": sha256_json(mind),
    }
    return mind, audit


def empiricalize_behavioral_voter(
    behavioral_voter: Mapping[str, Any],
    *,
    dimension_registry: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_id: str,
    snapshot_date: str,
    replicate_id: str = "R00",
    household: Mapping[str, Any] | None = None,
    ecological_context: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    visible = copy.deepcopy(dict(behavioral_voter))
    mind, audit = build_empirical_mind(
        voter=visible,
        dimension_registry=dimension_registry,
        source_registry=source_registry,
        prior_pack=prior_pack,
        snapshot_id=snapshot_id,
        snapshot_date=snapshot_date,
        replicate_id=replicate_id,
        household=household,
        ecological_context=ecological_context,
    )
    visible["empirical_moroccan_mind"] = _strip_hidden(mind)
    visible["empirical_mind_contract"] = {
        "population_priors_are_not_individual_facts": True,
        "ecological_context_is_not_personal_psychology": True,
        "unknown_dimensions_must_remain_unknown": True,
        "direct_evidence_only_for_sensitive_cultural_mechanisms": True,
        "no_party_preference_from_demographics": True,
        "v8_cognitive_architecture_preserved": "voter_mind_state" in visible,
    }
    audit["model_visible_empirical_mind_sha256"] = sha256_json(
        visible["empirical_moroccan_mind"]
    )
    audit["full_empirical_mind"] = mind
    return visible, audit

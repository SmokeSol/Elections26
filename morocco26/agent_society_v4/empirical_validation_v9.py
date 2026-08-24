from __future__ import annotations

"""Fail-closed validation gates for Empirical Moroccan Mind V9."""

from datetime import date
from typing import Any, Mapping

from .empirical_mind_v9 import EMPIRICAL_MIND_SCHEMA, assert_no_cultural_fabrication
from .empirical_priors_v9 import (
    ALLOWED_EPISTEMIC_STATUSES,
    CALIBRATED_STATUS,
    DIRECT_EVIDENCE_ONLY_DIMENSIONS,
    dimension_index,
    source_index,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)


class EmpiricalValidationError(ValueError):
    pass


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise EmpiricalValidationError(f"invalid date {value!r}") from exc


def audit_empirical_mind(
    mind: Mapping[str, Any],
    *,
    dimension_registry: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_date: str,
    forecast_lambda: float = 0.0,
    paired_tests: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    validate_dimension_registry(dimension_registry)
    validate_source_registry(source_registry, snapshot_date=snapshot_date)
    specs = dimension_index(dimension_registry)
    sources = source_index(source_registry)
    prior_validation = None
    if prior_pack is not None:
        prior_validation = validate_prior_pack(
            prior_pack,
            source_registry=source_registry,
            dimension_registry=dimension_registry,
            snapshot_date=snapshot_date,
            require_calibrated=False,
        )
    snapshot = _parse_date(snapshot_date)
    dimensions = mind.get("dimensions") or {}
    em0 = (
        mind.get("schema_version") == EMPIRICAL_MIND_SCHEMA
        and set(dimensions) == set(specs)
        and all(
            isinstance(state, Mapping)
            and state.get("epistemic_status") in ALLOWED_EPISTEMIC_STATUSES
            for state in dimensions.values()
        )
    )
    temporal_violations = []
    ecological_overclaims = []
    prior_overclaims = []
    sensitive_prior_violations = []
    unknown_integrity_violations = []
    bad_sources = []
    for dimension_id, state in dimensions.items():
        status = state.get("epistemic_status")
        known = _parse_date(state.get("known_as_of"))
        if snapshot and known and known > snapshot:
            temporal_violations.append(dimension_id)
        for source_id in state.get("source_ids") or []:
            if str(source_id).startswith(("INPUT_FIELD:", "CONTEXT_FIELD:")):
                continue
            if source_id not in sources:
                bad_sources.append(f"{dimension_id}:{source_id}")
        if status == "ECOLOGICAL_CONTEXT_ONLY":
            if state.get("value") is not None or state.get("individual_fact_claimed") is True:
                ecological_overclaims.append(dimension_id)
            if state.get("model_visibility") == "DIRECT_STATEMENT":
                ecological_overclaims.append(dimension_id + ":direct")
        if status == "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY":
            if state.get("individual_fact_claimed") is True:
                prior_overclaims.append(dimension_id)
            if not isinstance(state.get("posterior_distribution"), Mapping):
                prior_overclaims.append(dimension_id + ":posterior_missing")
        if dimension_id in DIRECT_EVIDENCE_ONLY_DIMENSIONS and status not in {
            "OBSERVED_INDIVIDUAL",
            "OBSERVED_HOUSEHOLD",
            "UNKNOWN",
        }:
            sensitive_prior_violations.append(dimension_id)
        if status == "UNKNOWN":
            if state.get("value") is not None or state.get("behavioral_use") != "DO_NOT_IMPUTE":
                unknown_integrity_violations.append(dimension_id)
    try:
        assert_no_cultural_fabrication(mind)
        cultural_fabrication = False
    except Exception:
        cultural_fabrication = True
    calibrated = bool(prior_pack and prior_pack.get("status") == CALIBRATED_STATUS)
    calibration_metrics_present = calibrated and all(
        all(
            key in (prior.get("calibration_metrics") or {})
            for key in (
                "weighted_margin_max_abs_error",
                "subgroup_margin_max_abs_error",
                "effective_sample_size",
            )
        )
        for prior in prior_pack.get("priors") or []
    )
    paired_tests = dict(paired_tests or {})
    paired_required = {
        "EM6_PERSONA_SENSITIVITY": bool(paired_tests.get("EM6_PERSONA_SENSITIVITY")),
        "EM7_CANDIDATE_PROGRAMME_PLACEBO": bool(
            paired_tests.get("EM7_CANDIDATE_PROGRAMME_PLACEBO")
        ),
        "EM8_POV_FIDELITY": bool(paired_tests.get("EM8_POV_FIDELITY")),
    }
    gates = {
        "EM0_SCHEMA_AND_PROVENANCE": em0 and not bad_sources,
        "EM1_TEMPORAL_VALIDITY": not temporal_violations,
        "EM2_NO_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM": not ecological_overclaims,
        "EM3_MOROCCAN_PRIOR_PACK_CALIBRATED": calibrated,
        "EM4_MARGINAL_AND_SUBGROUP_CALIBRATION": calibration_metrics_present,
        "EM5_NO_DEMOGRAPHIC_PARTISAN_STEREOTYPE": (
            not prior_overclaims
            and not sensitive_prior_violations
            and not cultural_fabrication
        ),
        "EM6_PAIRED_PERSONA_SENSITIVITY": paired_required["EM6_PERSONA_SENSITIVITY"],
        "EM7_PAIRED_CAUSAL_AND_PLACEBO": paired_required[
            "EM7_CANDIDATE_PROGRAMME_PLACEBO"
        ],
        "EM8_FIRST_PERSON_POV_FIDELITY": paired_required["EM8_POV_FIDELITY"],
        "EM9_FORECAST_BOUNDARY_LAMBDA_ZERO_PREVALIDATION": abs(float(forecast_lambda)) <= 1e-15,
        "EM10_MISSINGNESS_HONESTY": not unknown_integrity_violations,
    }
    scale_allowed = all(gates.values())
    return {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_GATE_REPORT_V1",
        "status": "PASS_EMPIRICAL_MIND_SCALE_READY" if scale_allowed else "BLOCKED_EMPIRICAL_MIND_NOT_SCALE_READY",
        "gates": gates,
        "scale_allowed": scale_allowed,
        "diagnostics": {
            "temporal_violations": sorted(set(temporal_violations)),
            "ecological_overclaims": sorted(set(ecological_overclaims)),
            "prior_overclaims": sorted(set(prior_overclaims)),
            "sensitive_prior_violations": sorted(set(sensitive_prior_violations)),
            "unknown_integrity_violations": sorted(set(unknown_integrity_violations)),
            "bad_sources": sorted(set(bad_sources)),
            "prior_validation": prior_validation,
            "unknown_dimensions": sum(
                1
                for state in dimensions.values()
                if state.get("epistemic_status") == "UNKNOWN"
            ),
            "total_dimensions": len(dimensions),
        },
    }

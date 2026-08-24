from __future__ import annotations

"""Fail-closed validation gates for Empirical Moroccan Mind V9.1.

EM2 is the reason this file exists. In V9 the gate only looked for
ECOLOGICAL_CONTEXT_ONLY states claiming to be individual, so it passed while
twelve stratum posterior means were being stamped OBSERVED_INDIVIDUAL with
`individual_fact_claimed: true`. Here EM2 is measured against the source field
of every state, and the manifest assertion is computed rather than declared.
"""

from datetime import date
from typing import Any, Mapping

from .empirical_mind_v9_1 import (
    ALLOWED_EPISTEMIC_STATUSES_V9_1,
    DEFAULT_MATCHED_DONOR_FIELDS,
    EMPIRICAL_MIND_V9_1_SCHEMA,
    ENGINE_DERIVED_COMPOSITE,
    MATCHED_DONOR_LATENT_STATE,
    SURVEY_STRATUM_PRIOR,
    assert_no_cultural_fabrication_v9_1,
    is_engine_derived_field,
    is_matched_donor_field,
    is_stratum_field,
)
from .empirical_priors_v9 import (
    CALIBRATED_STATUS,
    DIRECT_EVIDENCE_ONLY_DIMENSIONS,
    dimension_index,
    source_index,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)


class EmpiricalValidationV91Error(ValueError):
    pass


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise EmpiricalValidationV91Error(f"invalid date {value!r}") from exc


def audit_empirical_mind_v9_1(
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
        mind.get("schema_version") == EMPIRICAL_MIND_V9_1_SCHEMA
        and set(dimensions) == set(specs)
        and all(
            isinstance(state, Mapping)
            and state.get("epistemic_status") in ALLOWED_EPISTEMIC_STATUSES_V9_1
            for state in dimensions.values()
        )
    )

    donor_fields = tuple(
        str(field)
        for field in dimension_registry.get("matched_donor_fields") or DEFAULT_MATCHED_DONOR_FIELDS
    )
    engine_fields = dict(dimension_registry.get("engine_derived_composite_fields") or {})
    known_source_families = {
        str(dimension_registry.get("matched_donor_source_family") or "ENCDM2014_SES_DONOR")
    }

    temporal_violations: list[str] = []
    ecological_overclaims: list[str] = []
    stratum_overclaims: list[str] = []
    donor_overclaims: list[str] = []
    engine_overclaims: list[str] = []
    stratum_dispersion_lost: list[str] = []
    prior_overclaims: list[str] = []
    sensitive_prior_violations: list[str] = []
    unknown_integrity_violations: list[str] = []
    bad_sources: list[str] = []

    for dimension_id, state in dimensions.items():
        status = str(state.get("epistemic_status") or "")
        source_field = str(state.get("source_field") or "")
        known = _parse_date(state.get("known_as_of"))
        if snapshot and known and known > snapshot:
            temporal_violations.append(dimension_id)
        for source_id in state.get("source_ids") or []:
            text = str(source_id)
            if text.startswith(
                (
                    "INPUT_FIELD:",
                    "CONTEXT_FIELD:",
                    "SURVEY_STRATUM_FIELD:",
                    "MATCHED_DONOR_FIELD:",
                    "ENGINE_FIELD:",
                    "AFROBAROMETER_",
                )
            ):
                continue
            if text in known_source_families:
                continue
            if text not in sources:
                bad_sources.append(f"{dimension_id}:{text}")

        # EM2, measured: a stratum mean may never surface as an individual fact.
        if is_stratum_field(source_field) and (
            status == "OBSERVED_INDIVIDUAL" or state.get("individual_fact_claimed") is True
        ):
            stratum_overclaims.append(dimension_id)

        # EM2 sibling: an ENCDM matched donor is not an observation either.
        if is_matched_donor_field(source_field, donor_fields) and status in {
            "OBSERVED_INDIVIDUAL",
            "OBSERVED_HOUSEHOLD",
        }:
            donor_overclaims.append(dimension_id)
        if status == MATCHED_DONOR_LATENT_STATE:
            if state.get("individual_fact_claimed") is not False:
                donor_overclaims.append(dimension_id + ":claimed")
            if state.get("value") is not None:
                donor_overclaims.append(dimension_id + ":individual_value_present")
            if str(state.get("model_visibility") or "") == "DIRECT_STATEMENT":
                donor_overclaims.append(dimension_id + ":direct")

        if status == SURVEY_STRATUM_PRIOR:
            if state.get("individual_fact_claimed") is not False:
                stratum_overclaims.append(dimension_id + ":claimed")
            if state.get("value") is not None:
                stratum_overclaims.append(dimension_id + ":individual_value_present")
            if str(state.get("model_visibility") or "") == "DIRECT_STATEMENT":
                stratum_overclaims.append(dimension_id + ":direct")
            if state.get("stratum_sd") is None and "stratum_sd" in state:
                stratum_dispersion_lost.append(dimension_id)

        # A composite the engine computed is never evidence and never spoken.
        if is_engine_derived_field(source_field, engine_fields) and status in {
            "OBSERVED_INDIVIDUAL",
            "OBSERVED_HOUSEHOLD",
        }:
            engine_overclaims.append(dimension_id)
        if status == ENGINE_DERIVED_COMPOSITE:
            if state.get("individual_fact_claimed") is not False:
                engine_overclaims.append(dimension_id + ":claimed")
            if state.get("value") is not None:
                engine_overclaims.append(dimension_id + ":individual_value_present")
            if str(state.get("model_visibility") or "") != "HIDDEN_CALIBRATION_ONLY":
                engine_overclaims.append(dimension_id + ":model_visible")

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
        assert_no_cultural_fabrication_v9_1(mind)
        cultural_fabrication = False
    except Exception:
        cultural_fabrication = True

    declared = mind.get("population_prior_relabelled_as_individual_fact")
    measured = bool(
        stratum_overclaims or donor_overclaims or ecological_overclaims or engine_overclaims
    )
    assertion_matches_measurement = declared is measured or (declared is False and not measured)

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
    gates = {
        "EM0_SCHEMA_AND_PROVENANCE": em0 and not bad_sources,
        "EM1_TEMPORAL_VALIDITY": not temporal_violations,
        "EM2_NO_POPULATION_OR_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM": (
            not ecological_overclaims
            and not stratum_overclaims
            and not donor_overclaims
            and assertion_matches_measurement
        ),
        "EM3_MOROCCAN_PRIOR_PACK_CALIBRATED": calibrated,
        "EM4_MARGINAL_AND_SUBGROUP_CALIBRATION": calibration_metrics_present,
        "EM5_NO_DEMOGRAPHIC_PARTISAN_STEREOTYPE": (
            not prior_overclaims and not sensitive_prior_violations and not cultural_fabrication
        ),
        "EM6_PAIRED_PERSONA_SENSITIVITY": bool(paired_tests.get("EM6_PERSONA_SENSITIVITY")),
        "EM7_PAIRED_CAUSAL_AND_PLACEBO": bool(paired_tests.get("EM7_CANDIDATE_PROGRAMME_PLACEBO")),
        "EM8_FIRST_PERSON_POV_FIDELITY": bool(paired_tests.get("EM8_POV_FIDELITY")),
        "EM9_FORECAST_BOUNDARY_LAMBDA_ZERO_PREVALIDATION": abs(float(forecast_lambda)) <= 1e-15,
        "EM10_MISSINGNESS_HONESTY": not unknown_integrity_violations,
        "EM11_STRATUM_DISPERSION_RETAINED": not stratum_dispersion_lost,
        "EM12_MANIFEST_ASSERTIONS_MEASURED": (
            assertion_matches_measurement and bool((mind.get("epistemic_audit") or {}).get("measured"))
        ),
        "EM13_NO_ENGINE_COMPOSITE_COUNTED_AS_EVIDENCE": not engine_overclaims,
    }
    scale_allowed = all(gates.values())
    counts = mind.get("epistemic_counts") or {}
    return {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_V9_1_GATE_REPORT_V1",
        "status": "PASS_EMPIRICAL_MIND_V9_1_SCALE_READY"
        if scale_allowed
        else "BLOCKED_EMPIRICAL_MIND_V9_1_NOT_SCALE_READY",
        "gates": gates,
        "scale_allowed": scale_allowed,
        "diagnostics": {
            "temporal_violations": sorted(set(temporal_violations)),
            "ecological_overclaims": sorted(set(ecological_overclaims)),
            "stratum_overclaims": sorted(set(stratum_overclaims)),
            "matched_donor_overclaims": sorted(set(donor_overclaims)),
            "engine_composite_overclaims": sorted(set(engine_overclaims)),
            "stratum_dispersion_lost": sorted(set(stratum_dispersion_lost)),
            "prior_overclaims": sorted(set(prior_overclaims)),
            "sensitive_prior_violations": sorted(set(sensitive_prior_violations)),
            "unknown_integrity_violations": sorted(set(unknown_integrity_violations)),
            "bad_sources": sorted(set(bad_sources)),
            "prior_validation": prior_validation,
            "declared_population_prior_relabelled": declared,
            "measured_population_prior_relabelled": measured,
            "epistemic_counts": dict(sorted(counts.items())) if isinstance(counts, Mapping) else counts,
            "unknown_dimensions": sum(
                1 for state in dimensions.values() if state.get("epistemic_status") == "UNKNOWN"
            ),
            "stratum_prior_dimensions": sum(
                1 for state in dimensions.values() if state.get("epistemic_status") == SURVEY_STRATUM_PRIOR
            ),
            "matched_donor_dimensions": sum(
                1
                for state in dimensions.values()
                if state.get("epistemic_status") == MATCHED_DONOR_LATENT_STATE
            ),
            "engine_derived_composite_dimensions": sum(
                1
                for state in dimensions.values()
                if state.get("epistemic_status") == ENGINE_DERIVED_COMPOSITE
            ),
            "independent_evidence_dimensions": sum(
                1
                for state in dimensions.values()
                if state.get("epistemic_status")
                not in {"UNKNOWN", ENGINE_DERIVED_COMPOSITE}
            ),
            "total_dimensions": len(dimensions),
        },
    }

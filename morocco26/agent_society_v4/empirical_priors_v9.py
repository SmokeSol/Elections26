from __future__ import annotations

"""Validation and deterministic use of empirical Moroccan prior packs.

The module deliberately separates population evidence from individual facts.
A calibrated prior may generate a labelled synthetic posterior draw for a
synthetic voter, but it can never be relabelled as observed individual data.
"""

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

SOURCE_REGISTRY_SCHEMA = "ATLAS_EMPIRICAL_SOURCE_REGISTRY_V1"
DIMENSION_REGISTRY_SCHEMA = "ATLAS_EMPIRICAL_MIND_DIMENSIONS_V1"
PRIOR_PACK_SCHEMA = "ATLAS_EMPIRICAL_MOROCCAN_PRIOR_PACK_V1"
CALIBRATED_STATUS = "PASS_CALIBRATED_MOROCCAN_PRIOR_PACK_V1"
BLOCKED_STATUS = "BLOCKED_PENDING_CALIBRATED_MOROCCAN_PRIOR_PACK"

ALLOWED_EPISTEMIC_STATUSES = {
    "OBSERVED_INDIVIDUAL",
    "OBSERVED_HOUSEHOLD",
    "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY",
    "ECOLOGICAL_CONTEXT_ONLY",
    "REGISTERED_EXPERIMENTAL_PRIOR",
    "UNKNOWN",
}

# These states may never be fabricated from demographic or ecological priors.
DIRECT_EVIDENCE_ONLY_DIMENSIONS = {
    "party_affinity",
    "party_rejection",
    "candidate_personal_familiarity",
    "candidate_personal_relationship",
    "candidate_personal_valence",
    "family_vote_recommendation",
    "neighborhood_vote_recommendation",
    "workplace_vote_recommendation",
    "community_identity_party_alignment",
    "clientelistic_exchange_exposure",
    "vote_buying_exposure",
    "coercion_or_pressure_exposure",
    "specific_campaign_contact",
}

FORBIDDEN_DIRECT_PARTISAN_TARGETS = {
    "vote_choice",
    "local_vote_choice",
    "regional_vote_choice",
    "party_affinity",
    "party_rejection",
    "candidate_personal_valence",
}

PROTECTED_OR_IDENTITY_CONDITIONING_FIELDS = {
    "sex",
    "gender",
    "religion",
    "ethnicity",
    "race",
    "language",
    "tribe",
    "community",
}


class EmpiricalPriorError(ValueError):
    pass


@dataclass(frozen=True)
class PriorSelection:
    prior_id: str
    dimension_id: str
    cell_id: str
    distribution: dict[str, float]
    source_ids: tuple[str, ...]
    conditioning_fields: tuple[str, ...]
    support_n: int | None
    effective_sample_size: float | None
    known_as_of: str
    calibration_status: str


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise EmpiricalPriorError(f"{field} must be an ISO date, got {value!r}") from exc


def _finite_probability(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EmpiricalPriorError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise EmpiricalPriorError(f"{field} must be in [0,1]")
    return number


def dimension_index(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_dimension_registry(registry)
    return {str(row["dimension_id"]): dict(row) for row in registry["dimensions"]}


def source_index(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    validate_source_registry(registry)
    return {str(row["source_id"]): dict(row) for row in registry["sources"]}


def validate_source_registry(
    registry: Mapping[str, Any], *, snapshot_date: str | None = None
) -> dict[str, Any]:
    if registry.get("schema_version") != SOURCE_REGISTRY_SCHEMA:
        raise EmpiricalPriorError("unexpected source registry schema")
    rows = registry.get("sources")
    if not isinstance(rows, list) or not rows:
        raise EmpiricalPriorError("source registry must contain sources")
    seen: set[str] = set()
    cutoff = _parse_date(snapshot_date, "snapshot_date") if snapshot_date else None
    for idx, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise EmpiricalPriorError(f"source {idx} is not an object")
        source_id = str(raw.get("source_id") or "")
        if not source_id or source_id in seen:
            raise EmpiricalPriorError(f"invalid/duplicate source_id {source_id!r}")
        seen.add(source_id)
        for field in (
            "publisher",
            "title",
            "url",
            "evidence_type",
            "geographic_coverage",
            "known_as_of",
            "allowed_uses",
        ):
            if raw.get(field) in (None, "", []):
                raise EmpiricalPriorError(f"source {source_id}: missing {field}")
        known = _parse_date(raw["known_as_of"], f"source {source_id}.known_as_of")
        if cutoff and known > cutoff:
            raise EmpiricalPriorError(
                f"source {source_id} known after snapshot ({known} > {cutoff})"
            )
        if not isinstance(raw.get("allowed_uses"), list):
            raise EmpiricalPriorError(f"source {source_id}.allowed_uses must be a list")
        if raw.get("microdata_ingested") is True and not raw.get("processed_artifact_sha256"):
            raise EmpiricalPriorError(
                f"source {source_id}: ingested microdata lacks processed artifact hash"
            )
    return {
        "status": "PASS_EMPIRICAL_SOURCE_REGISTRY",
        "sources": len(rows),
        "registry_sha256": sha256_json(registry),
    }


def validate_dimension_registry(registry: Mapping[str, Any]) -> dict[str, Any]:
    if registry.get("schema_version") != DIMENSION_REGISTRY_SCHEMA:
        raise EmpiricalPriorError("unexpected dimension registry schema")
    rows = registry.get("dimensions")
    if not isinstance(rows, list) or not rows:
        raise EmpiricalPriorError("dimension registry must contain dimensions")
    seen: set[str] = set()
    families: set[str] = set()
    for idx, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise EmpiricalPriorError(f"dimension {idx} is not an object")
        dimension_id = str(raw.get("dimension_id") or "")
        if not dimension_id or dimension_id in seen:
            raise EmpiricalPriorError(f"invalid/duplicate dimension_id {dimension_id!r}")
        seen.add(dimension_id)
        family = str(raw.get("family") or "")
        if not family:
            raise EmpiricalPriorError(f"dimension {dimension_id}: missing family")
        families.add(family)
        if raw.get("default_epistemic_status") != "UNKNOWN":
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: default must be UNKNOWN"
            )
        if not isinstance(raw.get("individual_source_fields"), list):
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: individual_source_fields must be list"
            )
        if not isinstance(raw.get("household_source_fields"), list):
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: household_source_fields must be list"
            )
        survey_allowed = bool(raw.get("survey_prior_allowed"))
        if dimension_id in DIRECT_EVIDENCE_ONLY_DIMENSIONS and survey_allowed:
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: sensitive mechanism must be direct-evidence-only"
            )
        if raw.get("partisan_target") is True and survey_allowed:
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: partisan target cannot be filled by survey prior"
            )
        visibility = raw.get("model_visibility") or {}
        if not isinstance(visibility, Mapping):
            raise EmpiricalPriorError(
                f"dimension {dimension_id}: model_visibility must be object"
            )
    return {
        "status": "PASS_EMPIRICAL_DIMENSION_REGISTRY",
        "dimensions": len(rows),
        "families": len(families),
        "registry_sha256": sha256_json(registry),
    }


def _validate_distribution(
    distribution: Mapping[str, Any], *, field: str, allowed_categories: Sequence[str] | None
) -> dict[str, float]:
    if not isinstance(distribution, Mapping) or len(distribution) < 2:
        raise EmpiricalPriorError(f"{field} must have at least two categories")
    result = {str(k): _finite_probability(v, f"{field}.{k}") for k, v in distribution.items()}
    total = sum(result.values())
    if abs(total - 1.0) > 1e-8:
        raise EmpiricalPriorError(f"{field} does not sum to 1 (got {total})")
    if allowed_categories:
        unknown = set(result) - set(map(str, allowed_categories))
        if unknown:
            raise EmpiricalPriorError(f"{field} has unknown categories {sorted(unknown)}")
    return result


def validate_prior_pack(
    pack: Mapping[str, Any],
    *,
    source_registry: Mapping[str, Any],
    dimension_registry: Mapping[str, Any],
    snapshot_date: str | None = None,
    require_calibrated: bool = True,
) -> dict[str, Any]:
    validate_source_registry(source_registry, snapshot_date=snapshot_date)
    validate_dimension_registry(dimension_registry)
    sources = source_index(source_registry)
    dimensions = dimension_index(dimension_registry)
    if pack.get("schema_version") != PRIOR_PACK_SCHEMA:
        raise EmpiricalPriorError("unexpected prior pack schema")
    status = str(pack.get("status") or "")
    if require_calibrated and status != CALIBRATED_STATUS:
        raise EmpiricalPriorError(
            f"prior pack is not calibrated: {status or 'MISSING_STATUS'}"
        )
    if status not in {CALIBRATED_STATUS, BLOCKED_STATUS}:
        raise EmpiricalPriorError(f"invalid prior pack status {status!r}")
    if pack.get("raw_microdata_embedded") is not False:
        raise EmpiricalPriorError("prior pack must not embed raw microdata")
    if pack.get("individual_facts_claimed") is not False:
        raise EmpiricalPriorError("population prior pack cannot claim individual facts")
    if pack.get("direct_party_choice_prior_present") is not False:
        raise EmpiricalPriorError("direct party-choice priors are forbidden")
    cutoff = _parse_date(snapshot_date, "snapshot_date") if snapshot_date else None
    priors = pack.get("priors")
    if not isinstance(priors, list):
        raise EmpiricalPriorError("prior pack priors must be a list")
    seen_prior_ids: set[str] = set()
    cells_count = 0
    for raw in priors:
        if not isinstance(raw, Mapping):
            raise EmpiricalPriorError("prior entry is not an object")
        prior_id = str(raw.get("prior_id") or "")
        dimension_id = str(raw.get("dimension_id") or "")
        if not prior_id or prior_id in seen_prior_ids:
            raise EmpiricalPriorError(f"invalid/duplicate prior_id {prior_id!r}")
        seen_prior_ids.add(prior_id)
        if dimension_id not in dimensions:
            raise EmpiricalPriorError(f"prior {prior_id}: unknown dimension {dimension_id}")
        spec = dimensions[dimension_id]
        if not spec.get("survey_prior_allowed"):
            raise EmpiricalPriorError(
                f"prior {prior_id}: dimension {dimension_id} forbids survey priors"
            )
        if dimension_id in DIRECT_EVIDENCE_ONLY_DIMENSIONS:
            raise EmpiricalPriorError(
                f"prior {prior_id}: direct-evidence-only dimension cannot be modeled"
            )
        if dimension_id in FORBIDDEN_DIRECT_PARTISAN_TARGETS or spec.get("partisan_target"):
            raise EmpiricalPriorError(
                f"prior {prior_id}: partisan target is forbidden"
            )
        source_ids = tuple(map(str, raw.get("source_ids") or []))
        if not source_ids or any(source_id not in sources for source_id in source_ids):
            raise EmpiricalPriorError(f"prior {prior_id}: invalid source_ids")
        known = _parse_date(raw.get("known_as_of"), f"prior {prior_id}.known_as_of")
        if cutoff and known > cutoff:
            raise EmpiricalPriorError(
                f"prior {prior_id} known after snapshot ({known} > {cutoff})"
            )
        conditioning_fields = tuple(map(str, raw.get("conditioning_fields") or []))
        protected = set(conditioning_fields) & PROTECTED_OR_IDENTITY_CONDITIONING_FIELDS
        if protected and not raw.get("ecological_inference_guard"):
            raise EmpiricalPriorError(
                f"prior {prior_id}: protected conditioning requires ecological_inference_guard"
            )
        if protected and raw.get("may_create_partisan_preference") is not False:
            raise EmpiricalPriorError(
                f"prior {prior_id}: protected conditioning cannot create partisan preference"
            )
        cells = raw.get("cells")
        if not isinstance(cells, list) or not cells:
            raise EmpiricalPriorError(f"prior {prior_id}: cells missing")
        allowed_categories = spec.get("categories")
        cell_ids: set[str] = set()
        for cell in cells:
            if not isinstance(cell, Mapping):
                raise EmpiricalPriorError(f"prior {prior_id}: cell is not object")
            cell_id = str(cell.get("cell_id") or "")
            if not cell_id or cell_id in cell_ids:
                raise EmpiricalPriorError(
                    f"prior {prior_id}: invalid/duplicate cell_id {cell_id!r}"
                )
            cell_ids.add(cell_id)
            conditions = cell.get("conditions") or {}
            if not isinstance(conditions, Mapping):
                raise EmpiricalPriorError(
                    f"prior {prior_id}/{cell_id}: conditions must be object"
                )
            if set(map(str, conditions)) - set(conditioning_fields):
                raise EmpiricalPriorError(
                    f"prior {prior_id}/{cell_id}: condition outside conditioning_fields"
                )
            _validate_distribution(
                cell.get("distribution") or {},
                field=f"prior {prior_id}/{cell_id}.distribution",
                allowed_categories=allowed_categories,
            )
            support_n = cell.get("support_n")
            if support_n is not None and (not isinstance(support_n, int) or support_n < 1):
                raise EmpiricalPriorError(
                    f"prior {prior_id}/{cell_id}: invalid support_n"
                )
            cells_count += 1
        metrics = raw.get("calibration_metrics") or {}
        if status == CALIBRATED_STATUS:
            required_metrics = (
                "weighted_margin_max_abs_error",
                "subgroup_margin_max_abs_error",
                "effective_sample_size",
            )
            missing = [key for key in required_metrics if key not in metrics]
            if missing:
                raise EmpiricalPriorError(
                    f"prior {prior_id}: missing calibration metrics {missing}"
                )
    return {
        "status": (
            "PASS_CALIBRATED_PRIOR_PACK_VALIDATION"
            if status == CALIBRATED_STATUS
            else "PASS_BLOCKED_PRIOR_PACK_TEMPLATE_VALIDATION"
        ),
        "priors": len(priors),
        "cells": cells_count,
        "pack_sha256": sha256_json(pack),
    }


def _condition_matches(value: Any, rule: Any) -> bool:
    if isinstance(rule, Mapping):
        if "in" in rule:
            return value in rule["in"]
        if "not_in" in rule:
            return value not in rule["not_in"]
        if "min" in rule or "max" in rule:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return False
            if "min" in rule and number < float(rule["min"]):
                return False
            if "max" in rule and number > float(rule["max"]):
                return False
            return True
        if "equals" in rule:
            return value == rule["equals"]
        return False
    return value == rule


def select_prior(
    pack: Mapping[str, Any], *, dimension_id: str, voter: Mapping[str, Any]
) -> PriorSelection | None:
    if pack.get("status") != CALIBRATED_STATUS:
        return None
    candidates = [
        raw
        for raw in pack.get("priors") or []
        if str(raw.get("dimension_id")) == dimension_id
    ]
    if not candidates:
        return None
    matched: list[tuple[int, str, Mapping[str, Any], Mapping[str, Any]]] = []
    for prior in candidates:
        fields = tuple(map(str, prior.get("conditioning_fields") or []))
        for cell in prior.get("cells") or []:
            conditions = cell.get("conditions") or {}
            if all(_condition_matches(voter.get(field), rule) for field, rule in conditions.items()):
                matched.append((len(conditions), str(cell.get("cell_id")), prior, cell))
    if not matched:
        return None
    matched.sort(key=lambda row: (-row[0], row[1], str(row[2].get("prior_id"))))
    _, cell_id, prior, cell = matched[0]
    distribution = {
        str(k): float(v) for k, v in (cell.get("distribution") or {}).items()
    }
    return PriorSelection(
        prior_id=str(prior["prior_id"]),
        dimension_id=dimension_id,
        cell_id=cell_id,
        distribution=distribution,
        source_ids=tuple(map(str, prior.get("source_ids") or [])),
        conditioning_fields=tuple(map(str, prior.get("conditioning_fields") or [])),
        support_n=cell.get("support_n"),
        effective_sample_size=(
            float(cell["effective_sample_size"])
            if cell.get("effective_sample_size") is not None
            else None
        ),
        known_as_of=str(prior["known_as_of"]),
        calibration_status=str(prior.get("calibration_status") or "CALIBRATED"),
    )


def deterministic_draw(
    selection: PriorSelection, *, snapshot_id: str, voter_id: str, replicate_id: str
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (
                snapshot_id,
                voter_id,
                replicate_id,
                selection.prior_id,
                selection.cell_id,
                selection.dimension_id,
            )
        ).encode("utf-8")
    ).digest()
    u = int.from_bytes(digest[:8], "big") / float(2**64)
    cumulative = 0.0
    items = sorted(selection.distribution.items())
    for category, probability in items:
        cumulative += probability
        if u < cumulative:
            return category
    return items[-1][0]

from __future__ import annotations

"""Empirical Moroccan Mind V9.1 - amendment 01.

The frozen V9 payload is not edited. This module loads the frozen registry,
applies `EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json` on top of it, and
resolves dimensions with two corrections:

EM2. `latent_attitude_<x>_mean` is an Afrobarometer stratum posterior mean with
     a companion `_sd` and a stratum `n`. V9 stamped it OBSERVED_INDIVIDUAL with
     `individual_fact_claimed: true`, and never consumed the `_sd`. V9.1 routes
     it to SURVEY_STRATUM_PRIOR, keeps the dispersion and the support, and never
     lets the model speak it as a personal fact.

Vocabulary. Three fields the named 2026 pipeline actually carries had no V9
     dimension: `attention_score`, `localism`, `prior_vote_or_abstention`. They
     are registered as `political_attention`, `territorial_local_orientation`
     and `turnout_memory`. `information_diet_tier` is deliberately *not*
     registered: it is the engine's information-distribution rule, not a
     psychological state.

Nothing here fabricates a value. Every change either relabels evidence
correctly or connects a field that already existed.
"""

import copy
import json
from typing import Any, Mapping, Sequence

from .empirical_mind_v9 import (
    EMPIRICAL_DIMENSION_STATE_SCHEMA,
    FORBIDDEN_CULTURAL_INVENTION_KEYS,
    MODEL_HIDDEN_KEYS,
    EmpiricalMindError,
    _finite_number,
    _normalize_value,
    _observed_state,
    _survey_state,
    _ecological_state,
    _strip_hidden,
    _unknown_state,
)
from .empirical_priors_v9 import (
    ALLOWED_EPISTEMIC_STATUSES,
    CALIBRATED_STATUS,
    DIRECT_EVIDENCE_ONLY_DIMENSIONS,
    dimension_index,
    select_prior,
    sha256_json,
    source_index,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)

EMPIRICAL_MIND_V9_1_SCHEMA = "AGENT_SOCIETY_EMPIRICAL_MOROCCAN_MIND_V9_1"
AMENDMENT_SCHEMA = "ATLAS_EMPIRICAL_MIND_DIMENSIONS_AMENDMENT_V9_1"

SURVEY_STRATUM_PRIOR = "SURVEY_STRATUM_PRIOR"
MATCHED_DONOR_LATENT_STATE = "MATCHED_DONOR_LATENT_STATE"
ENGINE_DERIVED_COMPOSITE = "ENGINE_DERIVED_COMPOSITE"
STRATUM_VISIBILITY = "STRATUM_CONTEXT"
DONOR_VISIBILITY = "DONOR_CONTEXT"
ENGINE_VISIBILITY = "HIDDEN_CALIBRATION_ONLY"

ALLOWED_EPISTEMIC_STATUSES_V9_1 = frozenset(ALLOWED_EPISTEMIC_STATUSES) | {
    SURVEY_STRATUM_PRIOR,
    MATCHED_DONOR_LATENT_STATE,
    ENGINE_DERIVED_COMPOSITE,
}

EPISTEMIC_PRECEDENCE_V9_1 = {
    "OBSERVED_INDIVIDUAL": 60,
    "OBSERVED_HOUSEHOLD": 50,
    MATCHED_DONOR_LATENT_STATE: 45,
    "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY": 40,
    SURVEY_STRATUM_PRIOR: 35,
    "ECOLOGICAL_CONTEXT_ONLY": 30,
    "REGISTERED_EXPERIMENTAL_PRIOR": 20,
    ENGINE_DERIVED_COMPOSITE: 10,
    "UNKNOWN": 0,
}

# ENCDM donor-matched latent states. The rich feature manifest already calls
# these "not an observed fact about that synthetic person"; V9.1 enforces it.
DEFAULT_MATCHED_DONOR_FIELDS = (
    "latent_ses_decile",
    "latent_poverty_risk",
    "latent_vulnerability_risk",
    "latent_food_budget_share",
    "latent_housing_energy_budget_share",
    "latent_health_hygiene_budget_share",
    "latent_transport_communications_budget_share",
    "latent_education_culture_budget_share",
)

STRATUM_PREFIX = "latent_attitude_"
STRATUM_MEAN_SUFFIX = "_mean"
STRATUM_SD_SUFFIX = "_sd"
STRATUM_SUPPORT_FIELD = "attitude_posterior_stratum_n"
STRATUM_MATCH_FIELD = "attitude_posterior_match_level"
STRATUM_SOURCE_FIELD = "attitude_source"
STRATUM_BLOCK_KEY = "survey_stratum"

MODEL_HIDDEN_KEYS_V9_1 = frozenset(MODEL_HIDDEN_KEYS) | {"stratum_distribution"}

# Model-visibility values `_render_statement_v9_1` will speak.
RENDERABLE_VISIBILITIES = frozenset(
    {
        "DIRECT_STATEMENT",
        "PROBABILISTIC_CONTEXT",
        "CONTEXT_ONLY",
        STRATUM_VISIBILITY,
        DONOR_VISIBILITY,
    }
)


class EmpiricalMindV91Error(EmpiricalMindError):
    pass


def is_stratum_field(field: str) -> bool:
    name = str(field)
    return name.startswith(STRATUM_PREFIX) and name.endswith(STRATUM_MEAN_SUFFIX)


def is_matched_donor_field(field: str, donor_fields: Sequence[str] = ()) -> bool:
    return str(field) in (tuple(donor_fields) or DEFAULT_MATCHED_DONOR_FIELDS)


def is_engine_derived_field(field: str, engine_fields: Mapping[str, Any] | None = None) -> bool:
    return str(field) in dict(engine_fields or {})


def is_non_individual_field(
    field: str,
    donor_fields: Sequence[str] = (),
    engine_fields: Mapping[str, Any] | None = None,
) -> bool:
    return (
        is_stratum_field(field)
        or is_matched_donor_field(field, donor_fields)
        or is_engine_derived_field(field, engine_fields)
    )


def apply_registry_amendment(
    base_registry: Mapping[str, Any], amendment: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the V9.1 effective registry. The base registry is never mutated."""
    if str(amendment.get("schema_version") or "") != AMENDMENT_SCHEMA:
        raise EmpiricalMindV91Error("unexpected amendment schema")
    effective = copy.deepcopy(dict(base_registry))
    dimensions = [dict(row) for row in effective.get("dimensions") or []]
    known = {str(row.get("dimension_id")) for row in dimensions}

    for extension in amendment.get("alias_extensions") or []:
        dimension_id = str(extension.get("dimension_id") or "")
        if dimension_id not in known:
            raise EmpiricalMindV91Error(f"alias extension targets unknown dimension {dimension_id}")
        for row in dimensions:
            if str(row.get("dimension_id")) != dimension_id:
                continue
            for key in ("individual_source_fields", "household_source_fields", "ecological_context_fields"):
                added = [str(item) for item in extension.get(key) or []]
                if added:
                    row[key] = list(dict.fromkeys(list(row.get(key) or []) + added))

    label_extensions = amendment.get("category_label_extensions") or {}
    for dimension_id, labels in label_extensions.items():
        if str(dimension_id) not in known:
            raise EmpiricalMindV91Error(f"label extension targets unknown dimension {dimension_id}")
        for row in dimensions:
            if str(row.get("dimension_id")) == str(dimension_id):
                merged = dict(row.get("category_labels_fr") or {})
                merged.update({str(k): str(v) for k, v in dict(labels).items()})
                row["category_labels_fr"] = merged

    for row in amendment.get("new_dimensions") or []:
        dimension_id = str(row.get("dimension_id") or "")
        if not dimension_id:
            raise EmpiricalMindV91Error("new dimension without dimension_id")
        if dimension_id in known:
            raise EmpiricalMindV91Error(f"amendment redefines existing dimension {dimension_id}")
        known.add(dimension_id)
        dimensions.append(dict(row))

    effective["dimensions"] = dimensions
    effective["version"] = str(amendment.get("version") or "V9.1")
    effective["status"] = "FROZEN_DIMENSION_CATALOGUE_V9_1_AMENDED"
    effective["amendment_id"] = amendment.get("amendment_id")
    effective["base_registry_sha256"] = sha256_json(base_registry)
    effective["field_transforms"] = dict(amendment.get("field_transforms") or {})
    effective["matched_donor_fields"] = [
        str(field)
        for field in (amendment.get("matched_donor_source_detection") or {}).get("field_patterns")
        or DEFAULT_MATCHED_DONOR_FIELDS
    ]
    effective["matched_donor_source_family"] = (
        amendment.get("matched_donor_source_detection") or {}
    ).get("source_family")
    effective["engine_only_fields"] = sorted(amendment.get("engine_only_fields") or {})
    effective["engine_derived_composite_fields"] = dict(
        amendment.get("engine_derived_composite_fields") or {}
    )
    validate_dimension_registry(effective)
    expected = amendment.get("expected_dimension_count_after_amendment")
    if isinstance(expected, int) and expected != len(dimensions):
        raise EmpiricalMindV91Error(
            f"amendment expected {expected} dimensions, produced {len(dimensions)}"
        )
    return effective


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _count(container: Mapping[str, Any], key: str) -> float | None:
    return _finite_number(container.get(key))


def _yes_no(value: Any) -> str | None:
    if isinstance(value, bool):
        return "YES" if value else "NO"
    text = str(value or "").strip().lower()
    if text in {"oui", "yes", "1", "1.0", "true", "vrai"}:
        return "YES"
    if text in {"non", "no", "0", "0.0", "false", "faux"}:
        return "NO"
    return None


def apply_field_transform(
    value: Any, transform: str | None, container: Mapping[str, Any]
) -> Any:
    """Declared, auditable folds. Anything unmatched returns None -> UNKNOWN.

    A transform never invents a value: it either recognises the measured coding
    or leaves the dimension unknown.
    """
    if not transform:
        return value
    if transform == "PRIOR_VOTE_TO_TURNOUT_MEMORY":
        text = str(value or "").strip()
        if not text or text.upper() in {"UNKNOWN", "NONE", "NULL", "MISSING"}:
            return None
        return "PRIOR_ABSTENTION" if text.upper() == "ABSTAIN" else "PRIOR_TURNOUT"
    if transform == "ACTIVITY_STATUS_TO_EMPLOYMENT":
        text = str(value or "").strip().upper()
        return {
            "ACTIVE_EMPLOYED": "EMPLOYED",
            "EMPLOYED": "EMPLOYED",
            "UNEMPLOYED": "UNEMPLOYED",
            "INACTIVE": "INACTIVE",
            "STUDENT": "STUDENT",
            "RETIRED": "RETIRED",
        }.get(text)
    if transform == "EDUCATION_LABEL_TO_LEVEL":
        text = str(value or "").strip()
        upper = text.upper()
        if upper in {"NONE", "PRIMARY", "SECONDARY", "HIGH_SCHOOL", "TERTIARY", "OTHER"}:
            return upper
        lowered = text.lower()
        if not lowered or lowered in {"missing", "unknown"}:
            return None
        if "sup" in lowered:
            return "TERTIARY"
        if any(token in lowered for token in ("second", "coll", "qualif", "lyc")):
            return "SECONDARY"
        if "prim" in lowered:
            return "PRIMARY"
        if any(token in lowered for token in ("aucun", "prescol", "préscol", "neant", "néant")):
            return "NONE"
        return None
    if transform == "PERSONS_PER_ROOM_TO_CROWDING":
        number = _finite_number(value)
        if number is None or number <= 0:
            return None
        return round(_clip01((number - 1.0) / 3.0), 6)
    if transform == "UNEMPLOYED_COUNT_TO_BURDEN":
        unemployed = _finite_number(value)
        adults = _count(container, "household_adult_count")
        if unemployed is None or adults is None:
            return None
        return round(_clip01(unemployed / max(1.0, adults)), 6)
    if transform == "CARE_DEPENDENTS_TO_BURDEN":
        children = _finite_number(value)
        elderly = _count(container, "household_elderly_count")
        adults = _count(container, "household_adult_count")
        if children is None or adults is None:
            return None
        dependents = children + (elderly or 0.0)
        return round(_clip01(dependents / max(1.0, adults) / 3.0), 6)
    if transform == "TENURE_LABEL_TO_HOUSING_SECURITY":
        lowered = str(value or "").strip().lower()
        if not lowered or lowered in {"missing", "unknown"}:
            return None
        if "propri" in lowered or "owner" in lowered:
            return 0.9
        if "accession" in lowered or "credit" in lowered or "crédit" in lowered:
            return 0.75
        if "locat" in lowered or "tenant" in lowered or "rent" in lowered:
            return 0.5
        if "gratuit" in lowered or "free" in lowered or "logé" in lowered or "loge" in lowered:
            return 0.35
        return None
    if transform == "YES_NO_LABEL_TO_BOOLEAN":
        return _yes_no(value)
    raise EmpiricalMindV91Error(f"unknown field transform {transform!r}")


def _stratum_lookup(
    voter: Mapping[str, Any], field: str
) -> tuple[Any, float | None, int | None, str | None, str | None]:
    """Read a stratum mean plus its dispersion and support, from either a flat
    row (the attitude-overlay shape) or a `survey_stratum` block."""
    block = voter.get(STRATUM_BLOCK_KEY)
    containers = [voter]
    if isinstance(block, Mapping):
        containers.insert(0, block)
    for container in containers:
        if field in container and container.get(field) is not None:
            sd_field = field[: -len(STRATUM_MEAN_SUFFIX)] + STRATUM_SD_SUFFIX
            return (
                container.get(field),
                _finite_number(container.get(sd_field)),
                (
                    int(container[STRATUM_SUPPORT_FIELD])
                    if str(container.get(STRATUM_SUPPORT_FIELD) or "").lstrip("-").isdigit()
                    else None
                ),
                (str(container.get(STRATUM_MATCH_FIELD)) if container.get(STRATUM_MATCH_FIELD) else None),
                (str(container.get(STRATUM_SOURCE_FIELD)) if container.get(STRATUM_SOURCE_FIELD) else None),
            )
    return None, None, None, None, None


def _dispersion_band(sd: float | None) -> str:
    if sd is None:
        return "UNQUANTIFIED"
    if sd < 0.15:
        return "TIGHT"
    if sd < 0.30:
        return "MODERATE"
    return "WIDE"


def _stratum_state(
    *,
    spec: Mapping[str, Any],
    value: Any,
    sd: float | None,
    support_n: int | None,
    match_level: str | None,
    survey_source: str | None,
    source_field: str,
    snapshot_date: str,
    stratum_visibility: str = "context",
) -> dict[str, Any]:
    normalized, band = _normalize_value(value, spec)
    if normalized is None:
        return _unknown_state(spec)
    visibility = (spec.get("model_visibility") or {}).get("survey_stratum", STRATUM_VISIBILITY)
    if str(stratum_visibility).lower() == "hidden":
        visibility = "HIDDEN_CALIBRATION_ONLY"
    if visibility == "DIRECT_STATEMENT":
        raise EmpiricalMindV91Error(
            f"{spec.get('dimension_id')}: a stratum prior may never be a direct statement"
        )
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": SURVEY_STRATUM_PRIOR,
        "value": None,
        "stratum_mean": normalized,
        "stratum_sd": None if sd is None else round(float(sd), 6),
        "stratum_support_n": support_n,
        "stratum_match_level": match_level,
        "stratum_dispersion_band": _dispersion_band(sd),
        "band_or_category": band,
        "uncertainty": "STRATUM_POSTERIOR_SD_RETAINED" if sd is not None else "STRATUM_SD_ABSENT",
        "model_visibility": visibility,
        "behavioral_use": "CONTEXT_ONLY_NOT_INDIVIDUAL_TRAIT",
        "source_ids": [f"SURVEY_STRATUM_FIELD:{source_field}"] + ([survey_source] if survey_source else []),
        "known_as_of": snapshot_date,
        "conditioning_fields": [],
        "source_field": source_field,
        "individual_fact_claimed": False,
        "stratum_fact_claimed": True,
        "promotion_to_individual_forbidden": True,
    }


def _donor_state(
    *,
    spec: Mapping[str, Any],
    value: Any,
    source_field: str,
    snapshot_date: str,
    donor_source_family: str | None,
) -> dict[str, Any]:
    normalized, band = _normalize_value(value, spec)
    if normalized is None:
        return _unknown_state(spec)
    visibility = (spec.get("model_visibility") or {}).get("matched_donor", DONOR_VISIBILITY)
    if visibility == "DIRECT_STATEMENT":
        raise EmpiricalMindV91Error(
            f"{spec.get('dimension_id')}: a matched donor state may never be a direct statement"
        )
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": MATCHED_DONOR_LATENT_STATE,
        "value": None,
        "donor_value": normalized,
        "band_or_category": band,
        "uncertainty": "DONOR_MATCHING_UNCERTAINTY_NOT_QUANTIFIED",
        "model_visibility": visibility,
        "behavioral_use": "SOFT_CONTEXT_SYNTHETIC_LATENT_STATE",
        "source_ids": [f"MATCHED_DONOR_FIELD:{source_field}"]
        + ([donor_source_family] if donor_source_family else []),
        "known_as_of": snapshot_date,
        "conditioning_fields": [],
        "source_field": source_field,
        "individual_fact_claimed": False,
        "synthetic_latent_state_claimed": True,
        "promotion_to_individual_forbidden": True,
    }


def _engine_composite_state(
    *,
    spec: Mapping[str, Any],
    value: Any,
    source_field: str,
    snapshot_date: str,
    declaration: Mapping[str, Any],
) -> dict[str, Any]:
    """A value the engine computed from other fields is not evidence.

    `attention_score` in the named 2026 pipeline is
    `.45*political_discussion + .30*education_score + .15*0.4 + .10*localism`,
    verified exactly on 2944/2944 rows. Reporting it as an observation would
    both misstate its provenance and double-count three dimensions that are
    already registered separately.
    """
    normalized, band = _normalize_value(value, spec)
    if normalized is None:
        return _unknown_state(spec)
    visibility = (spec.get("model_visibility") or {}).get("engine_derived", ENGINE_VISIBILITY)
    if visibility in {"DIRECT_STATEMENT", "PROBABILISTIC_CONTEXT", "CONTEXT_ONLY", STRATUM_VISIBILITY, DONOR_VISIBILITY}:
        raise EmpiricalMindV91Error(
            f"{spec.get('dimension_id')}: an engine-derived composite may not be spoken to the model"
        )
    return {
        "schema_version": EMPIRICAL_DIMENSION_STATE_SCHEMA,
        "dimension_id": str(spec["dimension_id"]),
        "family": str(spec["family"]),
        "epistemic_status": ENGINE_DERIVED_COMPOSITE,
        "value": None,
        "engine_value": normalized,
        "band_or_category": band,
        "uncertainty": "NOT_AN_INDEPENDENT_MEASUREMENT",
        "model_visibility": visibility,
        "behavioral_use": "DO_NOT_IMPUTE",
        "source_ids": [f"ENGINE_FIELD:{source_field}"],
        "known_as_of": snapshot_date,
        "conditioning_fields": list(declaration.get("inputs") or []),
        "source_field": source_field,
        "engine_formula": declaration.get("formula"),
        "redundant_with": list(declaration.get("redundant_with") or []),
        "individual_fact_claimed": False,
        "independent_evidence": False,
    }


def resolve_dimension_v9_1(
    *,
    voter: Mapping[str, Any],
    household: Mapping[str, Any],
    ecological_context: Mapping[str, Any],
    spec: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_id: str,
    snapshot_date: str,
    replicate_id: str,
    field_transforms: Mapping[str, str] | None = None,
    donor_fields: Sequence[str] = (),
    donor_source_family: str | None = None,
    engine_fields: Mapping[str, Any] | None = None,
    stratum_visibility: str = "context",
) -> dict[str, Any]:
    field_transforms = field_transforms or {}
    engine_fields = dict(engine_fields or {})
    fallback_transform = spec.get("value_transform")
    individual_fields = [str(field) for field in spec.get("individual_source_fields") or []]

    def transform_for(field: str) -> str | None:
        return str(field_transforms.get(field) or fallback_transform or "") or None

    # 1. genuine individual observations, in declared order; stratum and donor
    #    fields are deliberately skipped here, they are not observations
    for field in individual_fields:
        if is_non_individual_field(field, donor_fields, engine_fields):
            continue
        if field in voter and voter.get(field) is not None:
            value = apply_field_transform(voter.get(field), transform_for(field), voter)
            if value is None:
                continue
            state = _observed_state(
                spec=spec, value=value, source_field=field, household=False, snapshot_date=snapshot_date
            )
            if state["epistemic_status"] != "UNKNOWN":
                return state

    # 2. household observations
    for field in [str(item) for item in spec.get("household_source_fields") or []]:
        if is_non_individual_field(field, donor_fields, engine_fields):
            continue
        if field in household and household.get(field) is not None:
            value = apply_field_transform(household.get(field), transform_for(field), household)
            if value is None:
                continue
            state = _observed_state(
                spec=spec, value=value, source_field=field, household=True, snapshot_date=snapshot_date
            )
            if state["epistemic_status"] != "UNKNOWN":
                return state

    dimension_id = str(spec["dimension_id"])

    # 3. ENCDM matched donor latent states, labelled as such
    if not spec.get("direct_evidence_only") and dimension_id not in DIRECT_EVIDENCE_ONLY_DIMENSIONS:
        for field in individual_fields + [str(item) for item in spec.get("household_source_fields") or []]:
            if not is_matched_donor_field(field, donor_fields):
                continue
            for container in (voter, household):
                if field in container and container.get(field) is not None:
                    state = _donor_state(
                        spec=spec,
                        value=container.get(field),
                        source_field=field,
                        snapshot_date=snapshot_date,
                        donor_source_family=donor_source_family,
                    )
                    if state["epistemic_status"] != "UNKNOWN":
                        return state

    # 4. calibrated survey posterior draw (unchanged from V9, still gated on EM3)
    if prior_pack and prior_pack.get("status") == CALIBRATED_STATUS and spec.get("survey_prior_allowed"):
        selection = select_prior(prior_pack, dimension_id=dimension_id, voter=voter)
        if selection:
            return _survey_state(
                spec=spec,
                selection=selection,
                snapshot_id=snapshot_id,
                voter_id=str(
                    voter.get("weighted_archetype_id") or voter.get("archetype_id") or voter.get("cell_id") or "UNKNOWN"
                ),
                replicate_id=replicate_id,
            )

    # 5. EM2 correction: survey stratum priors, labelled as such
    if not spec.get("direct_evidence_only") and dimension_id not in DIRECT_EVIDENCE_ONLY_DIMENSIONS:
        for field in individual_fields:
            if not is_stratum_field(field):
                continue
            value, sd, support_n, match_level, survey_source = _stratum_lookup(voter, field)
            if value is None:
                continue
            state = _stratum_state(
                spec=spec,
                value=value,
                sd=sd,
                support_n=support_n,
                match_level=match_level,
                survey_source=survey_source,
                source_field=field,
                snapshot_date=snapshot_date,
                stratum_visibility=stratum_visibility,
            )
            if state["epistemic_status"] != "UNKNOWN":
                return state

    # 6. ecological context
    for field in [str(item) for item in spec.get("ecological_context_fields") or []]:
        if field in ecological_context and ecological_context.get(field) is not None:
            return _ecological_state(
                spec=spec,
                value=ecological_context.get(field),
                source_field=field,
                snapshot_date=snapshot_date,
            )

    # 7. last resort: a composite the engine computed from other fields. It is
    #    recorded for the audit and never shown to the model.
    for field in individual_fields:
        declaration = engine_fields.get(field)
        if not declaration:
            continue
        for container in (voter, household):
            if field in container and container.get(field) is not None:
                state = _engine_composite_state(
                    spec=spec,
                    value=container.get(field),
                    source_field=field,
                    snapshot_date=snapshot_date,
                    declaration=declaration,
                )
                if state["epistemic_status"] != "UNKNOWN":
                    return state
    return _unknown_state(spec)


# Bare adjectives, used only after "à un niveau ..." in the stratum sentence.
BAND_FR = {
    "LOW": "bas",
    "MEDIUM": "moyen",
    "HIGH": "élevé",
    "NEGATIVE": "négatif",
    "POSITIVE": "positif",
    "MIXED_OR_NEUTRAL": "partagé",
    "YES": "présent",
    "NO": "absent",
}
# Self-contained noun phrases, so a band can be dropped into any template
# without creating a French gender-agreement error.
BAND_LABEL_FR = {
    "LOW": "niveau bas",
    "MEDIUM": "niveau moyen",
    "HIGH": "niveau élevé",
    "NEGATIVE": "orientation négative",
    "POSITIVE": "orientation positive",
    "MIXED_OR_NEUTRAL": "orientation partagée",
    "YES": "oui",
    "NO": "non",
}
DISPERSION_FR = {
    "TIGHT": "les gens de ce groupe se ressemblent beaucoup là-dessus",
    "MODERATE": "les avis y sont assez partagés",
    "WIDE": "les avis y sont très partagés",
    "UNQUANTIFIED": "la dispersion du groupe n'est pas connue",
}


def _category_label(category: str, spec: Mapping[str, Any]) -> str:
    """Human wording for a resolved category.

    A dimension may carry `category_labels_fr`; otherwise the code is softened
    to lower case with underscores turned into spaces, except for coded bands
    such as 18_24 where the underscore is a range separator.
    """
    labels = spec.get("category_labels_fr")
    if isinstance(labels, Mapping) and category in labels:
        return str(labels[category])
    if category in BAND_LABEL_FR:
        return BAND_LABEL_FR[category]
    if any(char.isdigit() for char in category):
        return category.replace("_", "-").lower()
    return category.lower().replace("_", " ")


def _render_statement_v9_1(state: Mapping[str, Any], spec: Mapping[str, Any]) -> str | None:
    visibility = str(state.get("model_visibility") or "")
    if visibility not in RENDERABLE_VISIBILITIES:
        return None
    category = str(state.get("band_or_category") or "UNKNOWN")
    status = state.get("epistemic_status")

    if status == SURVEY_STRATUM_PRIOR:
        # Never reuse the second-person template here: the sentence is about a
        # group of comparable people, not about this voter. The dimension is
        # named as a quoted quantity so it cannot be read as a personal claim.
        label = str(spec.get("description_fr") or spec.get("dimension_id") or "").strip().rstrip(".")
        if not label:
            return None
        level = BAND_FR.get(category, category.lower().replace("_", " "))
        dispersion = DISPERSION_FR[str(state.get("stratum_dispersion_band") or "UNQUANTIFIED")]
        return (
            f"Autour de toi, chez des personnes comparables, « {label} » se situe en moyenne "
            f"à un niveau {level} ; {dispersion}. Ce n'est pas forcément ton cas."
        )

    template = str((spec.get("rendering") or {}).get("fr") or "").strip()
    if not template:
        return None
    if status == "ECOLOGICAL_CONTEXT_ONLY":
        prefix = "Dans ton environnement, "
    elif status == "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY":
        prefix = "Dans cette réplique synthétique calibrée sur des personnes comparables, "
    elif status == MATCHED_DONOR_LATENT_STATE:
        prefix = "Dans cette réplique synthétique, appariée à des ménages comparables, "
    else:
        prefix = ""
    if prefix:
        template = template[:1].lower() + template[1:]
    return prefix + template.replace("{value}", _category_label(category, spec))


def measure_relabelling(
    states: Mapping[str, Mapping[str, Any]],
    *,
    donor_fields: Sequence[str] = (),
    engine_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The assertion V9 hard-coded, actually measured."""
    engine_fields = dict(engine_fields or {})
    engine_as_individual = []
    stratum_as_individual = []
    donor_as_individual = []
    ecological_as_individual = []
    stratum_without_dispersion = []
    stratum_spoken_directly = []
    for dimension_id, state in states.items():
        status = str(state.get("epistemic_status") or "")
        source_field = str(state.get("source_field") or "")
        claimed = state.get("individual_fact_claimed") is True
        if is_stratum_field(source_field) and (status == "OBSERVED_INDIVIDUAL" or claimed):
            stratum_as_individual.append(dimension_id)
        if is_matched_donor_field(source_field, donor_fields) and (
            status == "OBSERVED_INDIVIDUAL" or status == "OBSERVED_HOUSEHOLD" or claimed
        ):
            donor_as_individual.append(dimension_id)
        if status == "ECOLOGICAL_CONTEXT_ONLY" and claimed:
            ecological_as_individual.append(dimension_id)
        if status == SURVEY_STRATUM_PRIOR:
            if state.get("stratum_sd") is None:
                stratum_without_dispersion.append(dimension_id)
            if str(state.get("model_visibility") or "") == "DIRECT_STATEMENT":
                stratum_spoken_directly.append(dimension_id)
        if status == MATCHED_DONOR_LATENT_STATE and claimed:
            donor_as_individual.append(dimension_id)
        if is_engine_derived_field(source_field, engine_fields) and (
            status in {"OBSERVED_INDIVIDUAL", "OBSERVED_HOUSEHOLD"} or claimed
        ):
            engine_as_individual.append(dimension_id)
    offending = sorted(
        set(stratum_as_individual)
        | set(donor_as_individual)
        | set(ecological_as_individual)
        | set(engine_as_individual)
    )
    return {
        "population_prior_relabelled_as_individual_fact": bool(
            stratum_as_individual or donor_as_individual
        ),
        "survey_stratum_relabelled_as_individual_fact": bool(stratum_as_individual),
        "matched_donor_relabelled_as_individual_fact": bool(donor_as_individual),
        "engine_composite_relabelled_as_individual_fact": bool(engine_as_individual),
        "ecological_context_relabelled_as_individual_fact": bool(ecological_as_individual),
        "stratum_priors_without_retained_dispersion": sorted(stratum_without_dispersion),
        "stratum_priors_spoken_as_direct_statement": sorted(stratum_spoken_directly),
        "offending_dimensions": offending,
        "measured": True,
    }


def assert_no_cultural_fabrication_v9_1(mind: Mapping[str, Any]) -> None:
    text = json.dumps(mind, ensure_ascii=False, sort_keys=True).lower()
    forbidden_true = [key for key in FORBIDDEN_CULTURAL_INVENTION_KEYS if f'"{key}": true' in text]
    if forbidden_true:
        raise EmpiricalMindV91Error(f"mind claims invented cultural mechanisms: {sorted(forbidden_true)}")
    dimensions = mind.get("dimensions") or {}
    for dimension_id in DIRECT_EVIDENCE_ONLY_DIMENSIONS:
        state = dimensions.get(dimension_id)
        if not isinstance(state, Mapping):
            continue
        if state.get("epistemic_status") not in {"OBSERVED_INDIVIDUAL", "OBSERVED_HOUSEHOLD", "UNKNOWN"}:
            raise EmpiricalMindV91Error(
                f"{dimension_id} requires direct evidence, got {state.get('epistemic_status')}"
            )


def build_empirical_mind_v9_1(
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
    stratum_visibility: str = "context",
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
    field_transforms = dict(dimension_registry.get("field_transforms") or {})
    donor_fields = tuple(
        str(field) for field in dimension_registry.get("matched_donor_fields") or DEFAULT_MATCHED_DONOR_FIELDS
    )
    donor_source_family = dimension_registry.get("matched_donor_source_family")
    engine_fields = dict(dimension_registry.get("engine_derived_composite_fields") or {})
    states: dict[str, dict[str, Any]] = {}
    statements: list[str] = []
    counts = {status: 0 for status in sorted(ALLOWED_EPISTEMIC_STATUSES_V9_1)}
    for dimension_id in sorted(dimensions):
        spec = dimensions[dimension_id]
        state = resolve_dimension_v9_1(
            voter=voter,
            household=household,
            ecological_context=ecological_context,
            spec=spec,
            prior_pack=prior_pack,
            snapshot_id=snapshot_id,
            snapshot_date=snapshot_date,
            replicate_id=replicate_id,
            field_transforms=field_transforms,
            donor_fields=donor_fields,
            donor_source_family=donor_source_family,
            engine_fields=engine_fields,
            stratum_visibility=stratum_visibility,
        )
        status = str(state["epistemic_status"])
        if status not in counts:
            raise EmpiricalMindV91Error(f"unexpected epistemic status {status}")
        counts[status] += 1
        states[dimension_id] = state
        statement = _render_statement_v9_1(state, spec)
        if statement:
            statements.append(statement)

    relabelling = measure_relabelling(
        states, donor_fields=donor_fields, engine_fields=engine_fields
    )
    mind = {
        "schema_version": EMPIRICAL_MIND_V9_1_SCHEMA,
        "amendment_id": dimension_registry.get("amendment_id") or "V9_AMENDMENT_01",
        "status": (
            "EMPIRICAL_MIND_CALIBRATED_PRIORS_PRESENT"
            if prior_pack and prior_pack.get("status") == CALIBRATED_STATUS
            else "EMPIRICAL_MIND_OBSERVED_AND_STRATUM_PRIORS_PENDING_CALIBRATION"
        ),
        "snapshot_id": snapshot_id,
        "snapshot_date": snapshot_date,
        "replicate_id": replicate_id,
        "identity": {
            "weighted_archetype_id": voter.get("weighted_archetype_id") or voter.get("archetype_id"),
            "cell_id": voter.get("cell_id"),
        },
        "dimensions": states,
        "model_visible_human_context_fr": statements,
        "epistemic_counts": counts,
        "source_registry_sha256": sha256_json(source_registry),
        "dimension_registry_sha256": sha256_json(dimension_registry),
        "prior_pack_sha256": sha256_json(prior_pack) if prior_pack else None,
        "raw_microdata_embedded": False,
        "invented_clientelism": False,
        "invented_notable_network": False,
        "invented_tribal_alignment": False,
        "invented_family_recommendation": False,
        "invented_candidate_reputation": False,
        "invented_party_affinity": False,
        "invented_party_rejection": False,
        "registered_source_count": len(sources),
        "survey_stratum_model_visibility": str(stratum_visibility).lower(),
        "epistemic_audit": relabelling,
        "population_prior_relabelled_as_individual_fact": relabelling[
            "population_prior_relabelled_as_individual_fact"
        ],
    }
    assert_no_cultural_fabrication_v9_1(mind)
    if mind["population_prior_relabelled_as_individual_fact"]:
        raise EmpiricalMindV91Error(
            "EM2 violated: stratum priors relabelled as individual facts for "
            f"{relabelling['offending_dimensions']}"
        )
    populated = len(states) - counts["UNKNOWN"]
    independent = populated - counts[ENGINE_DERIVED_COMPOSITE]
    audit = {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_V9_1_AUDIT_V1",
        "weighted_archetype_id": mind["identity"]["weighted_archetype_id"],
        "epistemic_counts": counts,
        "dimensions": len(states),
        "populated_dimensions": populated,
        "independent_evidence_dimensions": independent,
        "engine_derived_composite_dimensions": counts[ENGINE_DERIVED_COMPOSITE],
        "unknown_share": round(counts["UNKNOWN"] / max(1, len(states)), 6),
        "model_visible_statement_count": len(statements),
        "direct_evidence_only_dimensions": sorted(DIRECT_EVIDENCE_ONLY_DIMENSIONS),
        "epistemic_audit": relabelling,
        "mind_sha256": sha256_json(mind),
    }
    return mind, audit


def empiricalize_behavioral_voter_v9_1(
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
    stratum_visibility: str = "context",
) -> tuple[dict[str, Any], dict[str, Any]]:
    visible = copy.deepcopy(dict(behavioral_voter))
    voter_household = household
    if voter_household is None and isinstance(visible.get("household_context"), Mapping):
        voter_household = dict(visible["household_context"])
    voter_context = ecological_context
    if voter_context is None and isinstance(visible.get("territory_context"), Mapping):
        voter_context = dict(visible["territory_context"])
    mind, audit = build_empirical_mind_v9_1(
        voter=visible,
        dimension_registry=dimension_registry,
        source_registry=source_registry,
        prior_pack=prior_pack,
        snapshot_id=snapshot_id,
        snapshot_date=snapshot_date,
        replicate_id=replicate_id,
        household=voter_household,
        ecological_context=voter_context,
        stratum_visibility=stratum_visibility,
    )
    stripped = _strip_hidden(mind)
    stripped = {
        key: value for key, value in stripped.items() if key not in MODEL_HIDDEN_KEYS_V9_1
    }
    # Raw stratum and donor values never reach the model view: only the labelled band.
    for state in (stripped.get("dimensions") or {}).values():
        if not isinstance(state, dict):
            continue
        if state.get("epistemic_status") == SURVEY_STRATUM_PRIOR:
            state.pop("stratum_mean", None)
            state.pop("stratum_sd", None)
        if state.get("epistemic_status") == MATCHED_DONOR_LATENT_STATE:
            state.pop("donor_value", None)
        if state.get("epistemic_status") == ENGINE_DERIVED_COMPOSITE:
            state.pop("engine_value", None)
    visible["empirical_moroccan_mind"] = stripped
    visible["empirical_mind_contract"] = {
        "population_priors_are_not_individual_facts": True,
        "survey_stratum_priors_are_not_individual_facts": True,
        "matched_donor_states_are_not_individual_facts": True,
        "engine_derived_composites_are_not_evidence": True,
        "ecological_context_is_not_personal_psychology": True,
        "unknown_dimensions_must_remain_unknown": True,
        "direct_evidence_only_for_sensitive_cultural_mechanisms": True,
        "no_party_preference_from_demographics": True,
        "v8_cognitive_architecture_preserved": "voter_mind_state" in visible,
    }
    audit["model_visible_empirical_mind_sha256"] = sha256_json(visible["empirical_moroccan_mind"])
    audit["full_empirical_mind"] = mind
    return visible, audit

from __future__ import annotations

"""Subjective voter-state layer for Agent Society current-vintage 2026 pilots.

Unknown psychopolitical dimensions stay UNKNOWN. The layer never invents
personal ties, candidate reputation/valence, clientelism, notability, party
rejection, or other Morocco-specific mechanisms that are absent upstream.
"""

import copy
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

BEHAVIORAL_MIND_SCHEMA = "AGENT_SOCIETY_BEHAVIORAL_MIND_V8"
MIND_STATE_SCHEMA = "AGENT_SOCIETY_VOTER_MIND_STATE_V1"
SUBJECTIVE_WORLD_SCHEMA = "AGENT_SOCIETY_SUBJECTIVE_ELECTORAL_WORLD_V1"

MODEL_HIDDEN_VOTER_KEYS = {
    "population_weight", "weight", "registered_weight_prior",
    "registered_electorate_weight", "registration_propensity_prior",
    "registration_calibration_factor", "poststratification_target",
    "source_record_ids", "source_record_id", "source_url", "url", "sha256",
    "provenance",
}
PROTECTED_OR_DEMOGRAPHIC_DERIVATION_EXCLUSIONS = {
    "sex", "gender", "age", "age_band", "religion", "ethnicity", "race",
    "language", "income", "income_band", "region", "region_id",
    "territory_id", "territory_name",
}
TECHNICAL_OUTPUT_ONTOLOGY_TOKENS = (
    "factor_importance", "cited_factors", "reason_codes", "policy_program_fit",
    "local_candidate_context", "government_reward_punishment",
    "territorial_rural_fit",
)


class BehavioralMindError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _unit(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if 1.0 < number <= 100.0:
        number /= 100.0
    return number if 0.0 <= number <= 1.0 else None


def _first_unit(voter: Mapping[str, Any], keys: Sequence[str]) -> tuple[float | None, str | None]:
    for key in keys:
        value = _unit(voter.get(key))
        if value is not None:
            return value, key
    return None, None


def _band(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "LOW" if value < 0.34 else "MEDIUM" if value < 0.67 else "HIGH"


def _signed_band(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "NEGATIVE" if value < 0.34 else "MIXED_OR_NEUTRAL" if value < 0.67 else "POSITIVE"


def _education_literacy(voter: Mapping[str, Any]) -> float | None:
    # Education is only a programme-literacy input, never a party-preference input.
    return {
        "NONE": .10, "PRIMARY": .30, "SECONDARY": .55, "HIGH_SCHOOL": .65,
        "TERTIARY": .90, "SUPERIEUR": .90, "SUPÉRIEUR": .90,
    }.get(str(voter.get("education_level") or "").upper())


def _information_profile(voter: Mapping[str, Any]) -> Mapping[str, Any]:
    diet = voter.get("information_diet")
    if isinstance(diet, Mapping) and isinstance(diet.get("profile"), Mapping):
        return diet["profile"]
    return {}


def _anchor(voter: Mapping[str, Any], keys: Sequence[str], *, signed: bool = False) -> dict[str, Any]:
    value, source = _first_unit(voter, keys)
    return {
        "band": _signed_band(value) if signed else _band(value),
        "observed_value": None if value is None else round(value, 6),
        "status": "OBSERVED_OR_UPSTREAM_LATENT" if value is not None else "UNKNOWN",
        "source_field": source,
    }


def _party_vector(voter: Mapping[str, Any], keys: Sequence[str], party_ids: Sequence[str], label: str) -> dict[str, Any]:
    raw = None
    source = None
    for key in keys:
        if isinstance(voter.get(key), Mapping):
            raw, source = voter[key], key
            break
    values, observed = {}, 0
    for party in party_ids:
        value = _unit(raw.get(party)) if isinstance(raw, Mapping) else None
        if value is None:
            values[str(party)] = {"band": "UNKNOWN", "value": None, "status": "UNKNOWN"}
        else:
            observed += 1
            values[str(party)] = {"band": _band(value), "value": round(value, 6), "status": "OBSERVED_OR_UPSTREAM_LATENT"}
    return {"label": label, "source_field": source, "observed_party_count": observed, "values": values}


def _fraction(*parts: Any) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def derive_voter_mind_state(voter: Mapping[str, Any], *, snapshot_id: str, party_ids: Sequence[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = _information_profile(voter)
    discussion, discussion_source = _first_unit(voter, ("latent_attitude_political_discussion_mean", "political_discussion"))
    if discussion is None:
        discussion = _unit(profile.get("attention")); discussion_source = "information_diet.profile.attention" if discussion is not None else None
    localism, localism_source = _first_unit(voter, ("latent_attitude_local_responsiveness_mean", "localism", "local_orientation"))
    if localism is None:
        localism = _unit(profile.get("localism")); localism_source = "information_diet.profile.localism" if localism is not None else None
    literacy, literacy_source = _first_unit(voter, ("program_literacy", "programme_literacy", "political_program_literacy"))
    if literacy is None:
        literacy = _unit(profile.get("program_literacy"))
        if literacy is not None:
            literacy_source = "information_diet.profile.program_literacy"
        else:
            edu = _education_literacy(voter)
            if edu is not None and discussion is not None:
                literacy = max(0.0, min(1.0, .55 * edu + .45 * discussion)); literacy_source = "DERIVED_EDUCATION_PLUS_POLITICAL_DISCUSSION"
    social = _unit(profile.get("social_reliance")); social_source = "information_diet.profile.social_reliance" if social is not None else None
    if social is None:
        social, social_source = _first_unit(voter, ("social_reliance", "trusted_network_reliance", "political_social_reliance"))
    attention = _unit(profile.get("attention")); attention_source = "information_diet.profile.attention" if attention is not None else None
    if attention is None and discussion is not None:
        attention, attention_source = discussion, discussion_source

    prior = str(voter.get("prior_vote_or_abstention") or "").strip()
    turnout_memory = (
        {"state": "UNKNOWN", "status": "UNKNOWN"} if not prior else
        {"state": "PRIOR_ABSTENTION" if prior.upper() == "ABSTAIN" else "PRIOR_TURNOUT", "status": "OBSERVED_FROM_SYNTHETIC_HISTORY"}
    )
    party_memory = {str(p): "UNSPECIFIED" for p in party_ids}
    if prior and prior.upper() != "ABSTAIN" and prior in party_memory:
        party_memory[prior] = "PRIOR_SUPPORTED"

    if localism is None or literacy is None:
        orientation, score, orientation_status = "UNKNOWN", None, "UNKNOWN"
    else:
        score = localism - literacy
        orientation = "LOCAL_PERSON_CANDIDATE_LEAN" if score > .20 else "PARTY_PROGRAMME_LEAN" if score < -.20 else "MIXED"
        orientation_status = "EXPERIMENTAL_DERIVED_UNVALIDATED"

    anchors = {
        "political_attention": {"band": _band(attention), "observed_value": None if attention is None else round(attention, 6), "status": "DERIVED_FROM_ALLOWED_INFORMATION_SIGNALS" if attention is not None else "UNKNOWN", "source_field": attention_source},
        "local_orientation": {"band": _band(localism), "observed_value": None if localism is None else round(localism, 6), "status": "OBSERVED_OR_UPSTREAM_LATENT" if localism is not None else "UNKNOWN", "source_field": localism_source},
        "programme_literacy": {"band": _band(literacy), "observed_value": None if literacy is None else round(literacy, 6), "status": "OBSERVED_OR_TRANSPARENT_DERIVED" if literacy is not None else "UNKNOWN", "source_field": literacy_source},
        "social_reliance": {"band": _band(social), "observed_value": None if social is None else round(social, 6), "status": "OBSERVED_OR_UPSTREAM_DERIVED" if social is not None else "UNKNOWN", "source_field": social_source},
        "government_evaluation": _anchor(voter, ("government_evaluation", "government_satisfaction", "latent_attitude_government_performance_mean", "government_performance"), signed=True),
        "political_efficacy": _anchor(voter, ("political_efficacy", "vote_efficacy", "latent_attitude_political_efficacy_mean", "efficacy_of_vote")),
        "institutional_trust": _anchor(voter, ("institutional_trust", "trust_in_institutions", "latent_attitude_institutional_trust_mean", "political_trust")),
        "personal_economic_mood": _anchor(voter, ("personal_economic_conditions", "economic_satisfaction", "latent_attitude_personal_economy_mean", "personal_economic_outlook"), signed=True),
        "protest_propensity": _anchor(voter, ("protest_vote_propensity", "protest_propensity", "latent_attitude_protest_mean")),
    }
    unknown = sorted(key for key, value in anchors.items() if value["band"] == "UNKNOWN")
    state = {
        "schema_version": MIND_STATE_SCHEMA,
        "snapshot_id": snapshot_id,
        "identity": {"weighted_archetype_id": voter.get("weighted_archetype_id") or voter.get("archetype_id"), "cell_id": voter.get("cell_id")},
        "before_this_election": {
            "turnout_memory": turnout_memory,
            "party_memory": party_memory,
            "party_affinity": _party_vector(voter, ("party_affinity", "party_affinities", "party_affinity_vector"), party_ids, "PARTY_AFFINITY"),
            "party_rejection": _party_vector(voter, ("party_rejection", "party_rejections", "party_rejection_vector"), party_ids, "PARTY_REJECTION"),
            "party_attachment_strength": _anchor(voter, ("party_attachment_strength", "partisan_attachment_strength", "party_loyalty_strength")),
            "habitual_turnout": _anchor(voter, ("habitual_turnout", "turnout_habit", "habitual_voting_propensity")),
            "anchors": anchors,
            "candidate_vs_party_orientation": {"state": orientation, "score": None if score is None else round(score, 6), "status": orientation_status, "interpretation": "soft predisposition, never a voting instruction"},
        },
        "explicit_unknowns": unknown,
        "invented_personal_relationships": False,
        "invented_clientelism_or_notability": False,
        "invented_party_rejection": False,
        "invented_candidate_valence": False,
    }
    audit = {
        "schema_version": BEHAVIORAL_MIND_SCHEMA,
        "weighted_archetype_id": state["identity"]["weighted_archetype_id"],
        "observed_or_derived_anchor_count": len(anchors) - len(unknown),
        "unknown_anchor_count": len(unknown), "unknown_anchors": unknown,
        "orientation_status": orientation_status,
        "protected_or_demographic_fields_used_for_political_inference": [],
        "derivation_exclusion_policy": sorted(PROTECTED_OR_DEMOGRAPHIC_DERIVATION_EXCLUSIONS),
    }
    audit["mind_state_sha256"] = sha256_json(state)
    return state, audit


def _strip_provenance(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _strip_provenance(v) for k, v in value.items() if str(k) not in MODEL_HIDDEN_VOTER_KEYS}
    if isinstance(value, list):
        return [_strip_provenance(item) for item in value]
    return value


def _regionalize_card(card: Mapping[str, Any]) -> dict[str, Any]:
    result = _strip_provenance(copy.deepcopy(dict(card)))
    explicit = result.pop("regional_candidate", None)
    for key in ("candidate_id", "candidate_name", "candidate_verification_state", "candidate_familiarity", "candidate_verified_profile", "local_viability_band"):
        result.pop(key, None)
    result["regional_candidate"] = _strip_provenance(explicit) if isinstance(explicit, Mapping) else None
    result["region_specific_candidate_information_present"] = isinstance(explicit, Mapping)
    return result


def _candidate_awareness(card: Mapping[str, Any], *, mind_state: Mapping[str, Any], voter_id: str, snapshot_id: str) -> tuple[bool, dict[str, Any]]:
    if not card.get("candidate_name"):
        return False, {"status": "NO_NAMED_CANDIDATE_IN_SUBJECTIVE_INPUT", "visible": False}
    explicit = card.get("candidate_known_to_agent")
    if isinstance(explicit, bool):
        return explicit, {"status": "EXPLICIT_UPSTREAM_VISIBILITY", "visible": explicit}
    anchors = (mind_state.get("before_this_election") or {}).get("anchors") or {}
    attention = _unit((anchors.get("political_attention") or {}).get("observed_value"))
    if attention is None:
        attention = .5
    localism = _unit((anchors.get("local_orientation") or {}).get("observed_value"))
    if localism is None:
        localism = .5
    tier = _band(attention); threshold = {"LOW": .78, "MEDIUM": .52, "HIGH": .22}.get(tier, .52)
    score = attention + .22 * localism + .08 * _fraction(snapshot_id, voter_id, card.get("party_id"))
    visible = score >= threshold
    return visible, {"status": "EXPERIMENTAL_DETERMINISTIC_AWARENESS_UNVALIDATED", "visible": visible, "attention_band": tier, "score": round(score, 6), "threshold": threshold, "does_not_imply_candidate_valence": True}


def _mask_local_candidate(card: Mapping[str, Any], *, mind_state: Mapping[str, Any], voter_id: str, snapshot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _strip_provenance(copy.deepcopy(dict(card)))
    visible, audit = _candidate_awareness(result, mind_state=mind_state, voter_id=voter_id, snapshot_id=snapshot_id)
    result["candidate_known_to_voter"] = visible
    if not visible:
        for key in ("candidate_id", "candidate_name", "candidate_familiarity", "candidate_verified_profile", "local_viability_band"):
            result.pop(key, None)
        result["candidate_information_state"] = "NOT_IN_THIS_VOTER_INFORMATION_DIET"
    else:
        result["candidate_information_state"] = "VISIBLE_IN_THIS_VOTER_INFORMATION_DIET"
    return result, audit


def build_subjective_electoral_world(voter: Mapping[str, Any], *, mind_state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    surface = voter.get("known_electoral_surface")
    if not isinstance(surface, Mapping) or not isinstance(surface.get("ballot_cards"), list) or len(surface["ballot_cards"]) < 2:
        raise BehavioralMindError("voter lacks a usable known_electoral_surface")
    voter_id = str(voter.get("weighted_archetype_id") or voter.get("archetype_id") or voter.get("cell_id") or "UNKNOWN_VOTER")
    snapshot_id = str(mind_state.get("snapshot_id") or "")
    local, awareness = [], {}
    for item in surface["ballot_cards"]:
        masked, audit = _mask_local_candidate(item, mind_state=mind_state, voter_id=voter_id, snapshot_id=snapshot_id)
        local.append(masked); awareness[str(item.get("party_id") or "")] = audit
    explicit_regional = surface.get("regional_ballot_cards")
    if isinstance(explicit_regional, list) and len(explicit_regional) >= 2:
        regional = [_strip_provenance(copy.deepcopy(item)) for item in explicit_regional]
        regional_source = "EXPLICIT_REGION_SPECIFIC_SURFACE"
    else:
        regional = [_regionalize_card(item) for item in surface["ballot_cards"]]
        regional_source = "PARTY_PROGRAMME_ONLY_LOCAL_CANDIDATE_STRIPPED"
    party_memory = (mind_state.get("before_this_election") or {}).get("party_memory") or {}
    for options in (local, regional):
        for item in options:
            item["prior_party_memory"] = party_memory.get(str(item.get("party_id") or ""), "UNSPECIFIED")
    world = {
        "schema_version": SUBJECTIVE_WORLD_SCHEMA,
        "information_boundary": "Only these facts are in this voter's current election world. Missing facts remain unknown; do not import current facts from outside the packet.",
        "LOCAL": {"options": local, "local_candidate_information_allowed": True},
        "REGIONAL": {"options": regional, "surface_source": regional_source, "local_candidate_information_allowed": False},
    }
    audit = {
        "local_option_count": len(local), "regional_option_count": len(regional),
        "regional_surface_source": regional_source,
        "local_candidate_removed_from_regional_default": regional_source != "EXPLICIT_REGION_SPECIFIC_SURFACE",
        "candidate_awareness_audit": awareness,
        "subjective_world_sha256": sha256_json(world),
    }
    return world, audit


def behavioralize_voter(voter: Mapping[str, Any], *, snapshot_id: str, party_ids: Sequence[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    visible = {str(k): copy.deepcopy(v) for k, v in voter.items() if str(k) not in MODEL_HIDDEN_VOTER_KEYS and str(k) not in {"information_diet", "known_electoral_surface"}}
    mind, mind_audit = derive_voter_mind_state(voter, snapshot_id=snapshot_id, party_ids=party_ids)
    world, world_audit = build_subjective_electoral_world(voter, mind_state=mind)
    visible["voter_mind_state"] = mind
    visible["electoral_world_as_seen"] = world
    visible["behavioral_contract"] = {
        "voter_is_not_an_analyst": True, "free_first_person_pov_required": True,
        "technical_factor_taxonomy_in_voice_forbidden": True, "unknown_is_allowed": True,
        "abstention_is_allowed": True, "local_and_regional_may_differ": True,
        "outside_current_facts_forbidden": True,
    }
    audit = {
        "schema_version": BEHAVIORAL_MIND_SCHEMA,
        "weighted_archetype_id": visible.get("weighted_archetype_id") or visible.get("archetype_id"),
        "mind": mind_audit, "world": world_audit,
        "technical_input_fields_removed_from_model_view": sorted(set(voter).intersection(MODEL_HIDDEN_VOTER_KEYS | {"information_diet", "known_electoral_surface"})),
    }
    audit["model_visible_voter_sha256"] = sha256_json(visible)
    return visible, audit


def assert_no_analyst_ontology_in_pov(text: str) -> None:
    lower = str(text or "").lower()
    findings = [token for token in TECHNICAL_OUTPUT_ONTOLOGY_TOKENS if token in lower]
    if findings:
        raise BehavioralMindError(f"POV contains technical research ontology: {findings}")

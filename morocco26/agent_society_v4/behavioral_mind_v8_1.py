from __future__ import annotations

"""Behavioral Mind V8.1 - strict electoral surface.

V8 is unchanged and is not edited. V8.1 is an additive amendment that removes
two ways the environment could lie to the model:

1. The silent regional fallback. When `regional_ballot_cards` is absent, V8
   copies the LOCAL ballot, strips the candidate, and calls the result REGIONAL.
   That is not a second contest, it is the first one amputated, and it made
   BR1-REGIONAL a test of the packet rather than of the voter mind. V8.1 sets
   REGIONAL_SURFACE_STATUS = MISSING and forbids the regional simulation.

2. The programme scaffold. When the party-programme layer is a placeholder
   (`direction = VERIFIED_POSITION_AVAILABLE`, i.e. "a position exists" without
   its content), V8.1 removes the axes from the model-visible card and replaces
   them with an explicit "not collected" marker, instead of letting nine
   alphabetical rotations masquerade as programmatic differentiation.

Nothing here invents data. Both changes remove fabricated differentiation.
"""

import copy
from typing import Any, Mapping, Sequence

from .behavioral_mind_v8 import (
    MODEL_HIDDEN_VOTER_KEYS,
    BehavioralMindError,
    _mask_local_candidate,
    _strip_provenance,
    derive_voter_mind_state,
    sha256_json,
)
from .p3_data_layers_v1 import USABLE_LAYER_STATES

BEHAVIORAL_MIND_V8_1_SCHEMA = "AGENT_SOCIETY_BEHAVIORAL_MIND_V8_1"
STRICT_WORLD_SCHEMA = "AGENT_SOCIETY_SUBJECTIVE_ELECTORAL_WORLD_V1_1_STRICT"

REGIONAL_PRESENT = "EXPLICIT_REGION_SPECIFIC_SURFACE"
REGIONAL_MISSING = "MISSING"

PROGRAMME_NOT_COLLECTED = "NOT_COLLECTED_AS_OF_SNAPSHOT"
PROGRAMME_COLLECTED = "COLLECTED_AND_SOURCED"

# The 2026 axis cells say only that a position exists. Keeping them visible
# manufactures differentiation with no empirical origin.
CONTENTLESS_DIRECTIONS = frozenset(
    {"VERIFIED_POSITION_AVAILABLE", "POSITION_AVAILABLE", "PRESENT", "UNKNOWN", ""}
)


class StrictSurfaceError(BehavioralMindError):
    pass


def programme_layer_is_usable(certificate: Mapping[str, Any] | None) -> bool:
    if certificate is None:
        return True
    state = (certificate.get("layer_states") or {}).get("PARTY_PROGRAMMES")
    return str(state) in USABLE_LAYER_STATES


def regional_layer_is_usable(certificate: Mapping[str, Any] | None) -> bool:
    if certificate is None:
        return True
    state = (certificate.get("layer_states") or {}).get("REGIONAL_BALLOT")
    return str(state) in USABLE_LAYER_STATES


def _axis_is_contentless(raw: Any) -> bool:
    if not isinstance(raw, Mapping):
        return True
    if str(raw.get("direction") or "") not in CONTENTLESS_DIRECTIONS:
        return False
    return not any(
        str(raw.get(key) or "").strip()
        for key in ("position_summary", "actual_position_summary", "commitments", "quote", "statement")
    )


def suppress_programme_scaffold(card: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Remove axis cells that carry no position, and say so explicitly."""
    result = dict(card)
    axes = result.get("programme_axes")
    if not isinstance(axes, Mapping) or not axes:
        result["programme_axes"] = {}
        result["programme_information_state"] = PROGRAMME_NOT_COLLECTED
        return result, False
    kept = {axis: raw for axis, raw in axes.items() if not _axis_is_contentless(raw)}
    removed = len(axes) - len(kept)
    result["programme_axes"] = kept
    result["programme_information_state"] = PROGRAMME_COLLECTED if kept else PROGRAMME_NOT_COLLECTED
    if removed:
        result["programme_axes_withheld_as_scaffold"] = removed
    return result, bool(kept)


def build_strict_subjective_world(
    voter: Mapping[str, Any],
    *,
    mind_state: Mapping[str, Any],
    certificate: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    surface = voter.get("known_electoral_surface")
    if (
        not isinstance(surface, Mapping)
        or not isinstance(surface.get("ballot_cards"), list)
        or len(surface["ballot_cards"]) < 2
    ):
        raise StrictSurfaceError("voter lacks a usable known_electoral_surface")
    voter_id = str(
        voter.get("weighted_archetype_id") or voter.get("archetype_id") or voter.get("cell_id") or "UNKNOWN_VOTER"
    )
    snapshot_id = str(mind_state.get("snapshot_id") or "")

    programmes_usable = programme_layer_is_usable(certificate)
    local: list[dict[str, Any]] = []
    awareness: dict[str, Any] = {}
    programme_cards_with_content = 0
    for item in surface["ballot_cards"]:
        masked, audit = _mask_local_candidate(
            item, mind_state=mind_state, voter_id=voter_id, snapshot_id=snapshot_id
        )
        if programmes_usable:
            masked, has_content = suppress_programme_scaffold(masked)
        else:
            masked = dict(masked)
            masked["programme_axes"] = {}
            masked["programme_information_state"] = PROGRAMME_NOT_COLLECTED
            has_content = False
        programme_cards_with_content += int(has_content)
        local.append(masked)
        awareness[str(item.get("party_id") or "")] = audit

    explicit_regional = surface.get("regional_ballot_cards")
    regional_available = isinstance(explicit_regional, list) and len(explicit_regional) >= 2
    if regional_available and regional_layer_is_usable(certificate):
        regional_options = [_strip_provenance(copy.deepcopy(item)) for item in explicit_regional]
        regional_status = REGIONAL_PRESENT
        regional_allowed = True
    else:
        regional_options = []
        regional_status = REGIONAL_MISSING
        regional_allowed = False

    party_memory = (mind_state.get("before_this_election") or {}).get("party_memory") or {}
    for item in local:
        item["prior_party_memory"] = party_memory.get(str(item.get("party_id") or ""), "UNSPECIFIED")
    for item in regional_options:
        item["prior_party_memory"] = party_memory.get(str(item.get("party_id") or ""), "UNSPECIFIED")

    world: dict[str, Any] = {
        "schema_version": STRICT_WORLD_SCHEMA,
        "information_boundary": (
            "Only these facts are in this voter's current election world. Missing facts "
            "remain unknown; do not import current facts from outside the packet."
        ),
        "ballots_available_to_this_voter": ["LOCAL"] + (["REGIONAL"] if regional_allowed else []),
        "LOCAL": {"options": local, "local_candidate_information_allowed": True},
        "REGIONAL": {
            "REGIONAL_SURFACE_STATUS": regional_status,
            "REGIONAL_SIMULATION_ALLOWED": regional_allowed,
            "options": regional_options,
            "surface_source": regional_status if regional_allowed else None,
            "local_candidate_information_allowed": False,
            "note": (
                None
                if regional_allowed
                else "No regional ballot has been collected for this snapshot. Do not produce a "
                "regional vote and do not reuse the local ballot as a substitute."
            ),
        },
    }
    audit = {
        "schema_version": BEHAVIORAL_MIND_V8_1_SCHEMA,
        "local_option_count": len(local),
        "regional_option_count": len(regional_options),
        "regional_surface_status": regional_status,
        "regional_simulation_allowed": regional_allowed,
        "regional_fallback_used": False,
        "programme_layer_usable": programmes_usable,
        "local_cards_with_programme_content": programme_cards_with_content,
        "candidate_awareness_audit": awareness,
        "subjective_world_sha256": sha256_json(world),
    }
    return world, audit


def behavioralize_voter_strict(
    voter: Mapping[str, Any],
    *,
    snapshot_id: str,
    party_ids: Sequence[str],
    certificate: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    visible = {
        str(key): copy.deepcopy(value)
        for key, value in voter.items()
        if str(key) not in MODEL_HIDDEN_VOTER_KEYS
        and str(key) not in {"information_diet", "known_electoral_surface"}
    }
    mind, mind_audit = derive_voter_mind_state(voter, snapshot_id=snapshot_id, party_ids=party_ids)
    world, world_audit = build_strict_subjective_world(
        voter, mind_state=mind, certificate=certificate
    )
    visible["voter_mind_state"] = mind
    visible["electoral_world_as_seen"] = world
    visible["behavioral_contract"] = {
        "voter_is_not_an_analyst": True,
        "free_first_person_pov_required": True,
        "technical_factor_taxonomy_in_voice_forbidden": True,
        "unknown_is_allowed": True,
        "abstention_is_allowed": True,
        "local_and_regional_may_differ": world["REGIONAL"]["REGIONAL_SIMULATION_ALLOWED"],
        "regional_ballot_simulated": world["REGIONAL"]["REGIONAL_SIMULATION_ALLOWED"],
        "outside_current_facts_forbidden": True,
        "programme_positions_available": world_audit["local_cards_with_programme_content"] > 0,
    }
    audit = {
        "schema_version": BEHAVIORAL_MIND_V8_1_SCHEMA,
        "weighted_archetype_id": visible.get("weighted_archetype_id") or visible.get("archetype_id"),
        "mind": mind_audit,
        "world": world_audit,
        "technical_input_fields_removed_from_model_view": sorted(
            set(voter).intersection(MODEL_HIDDEN_VOTER_KEYS | {"information_diet", "known_electoral_surface"})
        ),
    }
    audit["model_visible_voter_sha256"] = sha256_json(visible)
    return visible, audit

from __future__ import annotations

"""R0 - P3 data-layer certification.

The V9 Ain Chock pilot failed BR1-REGIONAL for a reason that has nothing to do
with the voter mind: three of the four data layers a substantive dual-ballot P3
needs were never collected, and the fourth was disconnected upstream. This
module measures each layer against the artifacts that actually exist and emits a
machine-readable certificate, so the environment can no longer present a
placeholder to the model as if it were electoral information.

A layer is exactly one of:

    REAL           collected, sourced, and substantively populated
    PARTIAL_REAL   collected and sourced, honestly incomplete
    PLACEHOLDER    structurally present but carrying no measured content
    DISCONNECTED   the data exists upstream and is not wired into this pipeline
    MISSING        never collected

Gates are then TESTABLE or NOT_TESTABLE_MISSING_DATA. NOT_TESTABLE is not FAIL:
a gate that cannot be fed cannot be failed by the model.
"""

import hashlib
import json
import pathlib
from typing import Any, Mapping, Sequence

CERTIFICATE_SCHEMA = "ATLAS_P3_DATA_LAYER_CERTIFICATE_V1"
POLICY_SCHEMA = "ATLAS_P3_DATA_LAYER_POLICY_V1"

LAYER_IDS = (
    "LOCAL_CANDIDATES",
    "PARTY_PROGRAMMES",
    "REGIONAL_BALLOT",
    "RICH_VOTER_STATE",
)
LAYER_STATES = ("REAL", "PARTIAL_REAL", "PLACEHOLDER", "DISCONNECTED", "MISSING")
USABLE_LAYER_STATES = frozenset({"REAL", "PARTIAL_REAL"})

TESTABLE = "TESTABLE"
NOT_TESTABLE = "NOT_TESTABLE_MISSING_DATA"

# A candidacy cell counts as substantive electoral information only in these
# states. The named pipeline emits the vintage_bridge_v7 vocabulary
# (OFFICIAL_CONFIRMED / DECLARED_BY_PARTY / REPORTED_UNCONFIRMED); the raw
# CandidateState vocabulary is accepted too so upstream snapshots also measure.
RESOLVED_CANDIDATE_STATES = frozenset(
    {
        "OFFICIAL_CONFIRMED",
        "DECLARED_BY_PARTY",
        "REPORTED_UNCONFIRMED",
        "OFFICIAL",
        "DECLARED",
        "REPORTED",
        "VERIFIED",
    }
)
# Cells that are honest absences rather than content.
EMPTY_CANDIDATE_STATES = frozenset(
    {"UNKNOWN_AS_OF_SNAPSHOT", "UNKNOWN", "NO_LIST_EVIDENCED", "NO_LIST"}
)

# direction values that assert only that a position exists.
CONTENTLESS_PROGRAMME_DIRECTIONS = frozenset(
    {
        "VERIFIED_POSITION_AVAILABLE",
        "POSITION_AVAILABLE",
        "PRESENT",
        "UNKNOWN",
        "",
    }
)

# Voter-row keys the named 2026 pipeline currently emits. Anything at or below
# this width is the seven-column service road, not the rich population.
NAMED_PIPELINE_BASELINE_FIELDS = frozenset(
    {
        "attention_score",
        "education_level",
        "information_diet_tier",
        "localism",
        "political_discussion",
        "prior_vote_or_abstention",
        "weighted_archetype_id",
    }
)
# The named pipeline carries seven columns. Twenty individual attributes plus a
# household block and a survey-stratum block is the point at which the voter
# state stops being a service road.
RICH_VOTER_MIN_INDIVIDUAL_FIELDS = 20

# Stratum-mean families that must never be counted as individual richness.
STRATUM_FIELD_PREFIX = "latent_attitude_"
STRATUM_METADATA_FIELDS = frozenset(
    {
        "attitude_posterior_match_level",
        "attitude_posterior_stratum_n",
        "attitude_source",
    }
)
RICH_BLOCK_KEYS = frozenset({"household_context", "survey_stratum", "territory_context"})


class P3DataLayerError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P3DataLayerError(f"cannot read JSON {path}: {exc}") from exc


def _rotation_offset(order: Sequence[str], canonical: Sequence[str]) -> int | None:
    """Return k if order is canonical rotated by k, else None."""
    size = len(canonical)
    if size == 0 or len(order) != size or set(order) != set(canonical):
        return None
    for offset in range(size):
        if all(order[i] == canonical[(i + offset) % size] for i in range(size)):
            return offset
    return None


def measure_party_programmes(programmes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Detect the synthetic alphabetical-rotation scaffold.

    The nine 2026 programmes are the same alphabetical list of canonical axes,
    each rotated by a party-specific offset, with every cell carrying the single
    value "a position exists". That is scaffolding, not a programme.
    """
    rows = [dict(item) for item in programmes or []]
    if not rows:
        return {
            "state": "MISSING",
            "parties": 0,
            "axis_cells": 0,
            "reason": "no programme record in the named input",
        }

    canonical = sorted({str(axis) for row in rows for axis in (row.get("axes") or {})})
    directions: dict[str, int] = {}
    rank_orders: dict[str, tuple[str, ...]] = {}
    substantive_cells = 0
    cells = 0
    parties_with_content: list[str] = []
    for row in rows:
        party_id = str(row.get("party_id") or "")
        axes = row.get("axes") or {}
        ranked = sorted(
            (int((raw or {}).get("national_salience_rank") or 9999), str(axis))
            for axis, raw in axes.items()
        )
        rank_orders[party_id] = tuple(axis for _, axis in ranked)
        party_content = 0
        for axis, raw in axes.items():
            cells += 1
            raw = raw if isinstance(raw, Mapping) else {}
            direction = str(raw.get("direction") or "")
            directions[direction] = directions.get(direction, 0) + 1
            has_text = any(
                str(raw.get(key) or "").strip()
                for key in (
                    "position_summary",
                    "actual_position_summary",
                    "commitments",
                    "quote",
                    "statement",
                )
            )
            if direction not in CONTENTLESS_PROGRAMME_DIRECTIONS or has_text:
                substantive_cells += 1
                party_content += 1
        if party_content:
            parties_with_content.append(party_id)

    offsets = {party: _rotation_offset(order, canonical) for party, order in rank_orders.items()}
    all_rotations = bool(offsets) and all(value is not None for value in offsets.values())
    distinct_profiles = len(set(rank_orders.values()))

    if substantive_cells == 0:
        state = "PLACEHOLDER"
        reason = (
            "every axis cell carries only the existence of a position "
            + str(sorted(directions))
            + ", never its content"
        )
    elif all_rotations and distinct_profiles < len(rows) and substantive_cells * 2 < cells:
        # Some content, but the ordering is still a shared synthetic rotation and
        # most cells stay empty: differentiation without an empirical origin.
        state = "PLACEHOLDER"
        reason = "axis salience is an alphabetical rotation shared by several parties"
    elif len(parties_with_content) < len(rows):
        state = "PARTIAL_REAL"
        reason = f"{len(parties_with_content)}/{len(rows)} parties carry measured positions"
    else:
        state = "REAL"
        reason = "every party carries measured positions"

    return {
        "state": state,
        "parties": len(rows),
        "axis_cells": cells,
        "canonical_axes": len(canonical),
        "substantive_position_cells": substantive_cells,
        "direction_census": dict(sorted(directions.items())),
        "alphabetical_rotation_offsets": {party: offset for party, offset in sorted(offsets.items())},
        "all_programmes_are_alphabetical_rotations": all_rotations,
        "shared_rotation_offsets_detected": all_rotations and distinct_profiles < len(rows),
        "distinct_axis_orderings": distinct_profiles,
        "parties_with_measured_positions": sorted(parties_with_content),
        "reason": reason,
    }


def measure_local_candidates(
    candidacies: Sequence[Mapping[str, Any]], *, territories: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    rows = [dict(item) for item in candidacies or []]
    if not rows:
        return {"state": "MISSING", "cells": 0, "reason": "no candidacy cell"}
    census: dict[str, int] = {}
    named = 0
    fabricated = 0
    for row in rows:
        state = str(row.get("verification_state") or "UNKNOWN")
        census[state] = census.get(state, 0) + 1
        if row.get("candidate_name"):
            named += 1
            if state in EMPTY_CANDIDATE_STATES:
                fabricated += 1
    resolved = sum(count for state, count in census.items() if state in RESOLVED_CANDIDATE_STATES)
    unknown = sum(count for state, count in census.items() if state in EMPTY_CANDIDATE_STATES)
    parties = sorted({str(row.get("party_id") or "") for row in rows})
    territory_ids = sorted({str(row.get("territory_id") or "") for row in rows})
    if fabricated:
        state = "PLACEHOLDER"
        reason = f"{fabricated} cells carry a name while declaring an UNKNOWN/NO_LIST state"
    elif resolved == 0:
        state = "MISSING"
        reason = "no cell reaches a verified candidate state"
    elif unknown:
        state = "PARTIAL_REAL"
        reason = f"{resolved}/{len(rows)} cells verified, {unknown} honestly unknown"
    else:
        state = "REAL"
        reason = "every ballot cell is verified"
    return {
        "state": state,
        "cells": len(rows),
        "named_candidates": named,
        "resolved_cells": resolved,
        "unknown_cells": unknown,
        "fabricated_named_unknown_cells": fabricated,
        "parties": len(parties),
        "territories": len(territory_ids),
        "declared_territories": len(territories or ()),
        "state_census": dict(sorted(census.items())),
        "reason": reason,
    }


def iter_named_voters(voter_population: Mapping[str, Any]):
    for batch in (voter_population or {}).get("batches") or []:
        territory_id = str(batch.get("territory_id") or batch.get("anonymous_territory_id") or "")
        for voter in batch.get("voters") or batch.get("voter_archetypes") or []:
            if isinstance(voter, Mapping):
                yield territory_id, dict(voter)


def measure_regional_ballot(
    named_input: Mapping[str, Any], *, regional_dataset: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    explicit_cards = 0
    for _, voter in iter_named_voters(named_input.get("voter_population") or {}):
        surface = voter.get("known_electoral_surface")
        if isinstance(surface, Mapping) and isinstance(surface.get("regional_ballot_cards"), list):
            explicit_cards += len(surface["regional_ballot_cards"])
    dataset_rows = 0
    dataset_status = None
    if isinstance(regional_dataset, Mapping):
        dataset_status = str(regional_dataset.get("status") or "")
        dataset_rows = len([row for row in regional_dataset.get("rows") or [] if isinstance(row, Mapping)])
    top_level = named_input.get("regional_ballot") or named_input.get("regional_ballots")
    top_level_rows = len(top_level) if isinstance(top_level, list) else 0
    total = explicit_cards + dataset_rows + top_level_rows
    if total == 0:
        state = "MISSING"
        reason = (
            "no regional_ballot_cards anywhere in the named input and no "
            "regional_ballot_2026 dataset rows; the V8 slot exists and is empty"
        )
    elif dataset_status and dataset_status != "PASS_REGIONAL_BALLOT_2026_COLLECTED":
        state = "PARTIAL_REAL"
        reason = f"regional dataset present with status {dataset_status}"
    else:
        state = "REAL"
        reason = "an explicit region-specific surface is available"
    return {
        "state": state,
        "explicit_regional_ballot_cards": explicit_cards,
        "regional_dataset_rows": dataset_rows,
        "regional_dataset_status": dataset_status,
        "top_level_regional_rows": top_level_rows,
        "reason": reason,
    }


def measure_rich_voter_state(
    named_input: Mapping[str, Any],
    *,
    rich_population_certificate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    widths: list[int] = []
    key_union: set[str] = set()
    stratum_fields = 0
    household_blocks = 0
    stratum_blocks = 0
    territory_blocks = 0
    voters = 0
    for _, voter in iter_named_voters(named_input.get("voter_population") or {}):
        voters += 1
        keys = {str(key) for key in voter}
        key_union |= keys
        block = voter.get("survey_stratum")
        block_keys = {str(key) for key in block} if isinstance(block, Mapping) else set()
        stratum_fields += sum(
            1
            for key in keys | block_keys
            if key.startswith(STRATUM_FIELD_PREFIX) or key in STRATUM_METADATA_FIELDS
        )
        individual = {
            key
            for key in keys
            if not key.startswith(STRATUM_FIELD_PREFIX)
            and key not in STRATUM_METADATA_FIELDS
            and key not in RICH_BLOCK_KEYS
        }
        widths.append(len(individual))
        household_blocks += isinstance(voter.get("household_context"), Mapping)
        stratum_blocks += isinstance(voter.get("survey_stratum"), Mapping)
        territory_blocks += isinstance(voter.get("territory_context"), Mapping)
    if voters == 0:
        return {"state": "MISSING", "voters": 0, "reason": "named input carries no voter"}
    mean_width = sum(widths) / len(widths)
    upstream_pass = bool(
        rich_population_certificate and str(rich_population_certificate.get("status") or "") == "PASS"
    )
    baseline_only = key_union.issubset(NAMED_PIPELINE_BASELINE_FIELDS)
    if (
        mean_width >= RICH_VOTER_MIN_INDIVIDUAL_FIELDS
        and household_blocks == voters
        and stratum_blocks == voters
    ):
        state = "REAL"
        reason = (
            f"individual ({mean_width:.0f} fields), household and survey-stratum blocks "
            "are wired in for every voter"
        )
    elif mean_width >= RICH_VOTER_MIN_INDIVIDUAL_FIELDS:
        state = "PARTIAL_REAL"
        reason = "rich individual fields present, household/stratum blocks incomplete"
    elif upstream_pass:
        state = "DISCONNECTED"
        reason = (
            f"named voters carry {mean_width:.0f} individual fields while a PASS rich "
            "population certificate exists upstream: this is wiring, not collection"
        )
    else:
        state = "MISSING"
        reason = "no rich population upstream and no rich fields downstream"
    return {
        "state": state,
        "voters": voters,
        "mean_individual_fields_per_voter": round(mean_width, 6),
        "distinct_voter_keys": sorted(key_union),
        "stratum_labelled_fields": stratum_fields,
        "voters_with_household_block": household_blocks,
        "voters_with_survey_stratum_block": stratum_blocks,
        "voters_with_territory_block": territory_blocks,
        "named_pipeline_baseline_only": baseline_only,
        "upstream_rich_population_certificate_pass": upstream_pass,
        "reason": reason,
    }


def measure_party_memory(named_input: Mapping[str, Any]) -> dict[str, Any]:
    voters = 0
    with_memory = 0
    for _, voter in iter_named_voters(named_input.get("voter_population") or {}):
        voters += 1
        prior = voter.get("prior_vote_or_abstention")
        if prior not in (None, "", "UNKNOWN"):
            with_memory += 1
    return {"voters": voters, "voters_with_prior_vote_memory": with_memory}


CELL_CENSUS_SCHEMA = "ATLAS_P3_CANDIDATE_BALLOT_CELL_CENSUS_V1"


def build_cell_census(
    *, named_input: Mapping[str, Any], named_input_sha256: str
) -> dict[str, Any]:
    """The canonical, cell-level snapshot of the LOCAL_CANDIDATES layer.

    The record-level `candidate_coverage_2026.json` counts collected candidate
    *records*; a P3 environment embeds ballot *cells*. Publishing this census
    beside the certificate is what makes "how many candidates do we have?" have
    a single answer for the artifact the model actually sees.
    """
    rows = [dict(item) for item in named_input.get("candidacies") or []]
    by_state: dict[str, int] = {}
    by_party: dict[str, dict[str, int]] = {}
    territories: set[str] = set()
    for row in rows:
        state = str(row.get("verification_state") or "UNKNOWN")
        party = str(row.get("party_id") or "")
        territories.add(str(row.get("territory_id") or ""))
        by_state[state] = by_state.get(state, 0) + 1
        bucket = by_party.setdefault(party, {})
        bucket[state] = bucket.get(state, 0) + 1
    resolved = sum(count for state, count in by_state.items() if state in RESOLVED_CANDIDATE_STATES)
    census = {
        "schema_version": CELL_CENSUS_SCHEMA,
        "artifact_id": "M26-P3-CANDIDATE-BALLOT-CELL-CENSUS-V1",
        "as_of": named_input.get("snapshot_known_as_of"),
        "named_input_sha256": named_input_sha256,
        "named_input_artifact_id": named_input.get("artifact_id"),
        "ballot_cells": len(rows),
        "resolved_cells": resolved,
        "unknown_cells": sum(
            count for state, count in by_state.items() if state in EMPTY_CANDIDATE_STATES
        ),
        "territories": len(territories),
        "parties": sorted(party for party in by_party if party),
        "state_census": dict(sorted(by_state.items())),
        "state_census_by_party": {
            party: dict(sorted(states.items())) for party, states in sorted(by_party.items())
        },
        "method_note": (
            "Counts are measured from the named 2026 input the environment embeds. "
            "Nothing is imputed. Cells are not records: see candidate_coverage_2026.json "
            "for the record-level collection coverage."
        ),
    }
    census["census_sha256"] = sha256_json(census)
    return census


def check_lineage(
    *,
    local_layer: Mapping[str, Any],
    named_input: Mapping[str, Any],
    named_input_sha256: str,
    cell_census: Mapping[str, Any] | None,
    cell_census_path: str | None,
    coverage_snapshot: Mapping[str, Any] | None,
    coverage_path: str | None,
) -> dict[str, Any]:
    """A P3 environment may not embed a layer whose canonical repo snapshot and
    certificate are not published together.

    The pilot ran on 828 cells / 521 confirmed while the canonical repo dataset
    still advertised 414 records as of an earlier date. One question, two
    answers: that is exactly the failure this rule exists to stop.
    """
    env_as_of = str(named_input.get("snapshot_known_as_of") or "")
    divergences: list[str] = []
    advisories: list[str] = []

    if not isinstance(cell_census, Mapping):
        divergences.append(
            "canonical ballot-cell census absent: publish candidate_ballot_cells_2026.json "
            "beside this certificate"
        )
    else:
        if str(cell_census.get("named_input_sha256") or "") != named_input_sha256:
            divergences.append(
                "ballot-cell census was published from a different named input "
                f"({cell_census.get('named_input_sha256')} != {named_input_sha256})"
            )
        if int(cell_census.get("ballot_cells") or -1) != int(local_layer.get("cells") or 0):
            divergences.append(
                f"ballot cells: environment {local_layer.get('cells')} vs census {cell_census.get('ballot_cells')}"
            )
        if int(cell_census.get("resolved_cells") or -1) != int(local_layer.get("resolved_cells") or 0):
            divergences.append(
                f"resolved cells: environment {local_layer.get('resolved_cells')} "
                f"vs census {cell_census.get('resolved_cells')}"
            )
        if str(cell_census.get("as_of") or "") != env_as_of:
            divergences.append(
                f"census as_of {cell_census.get('as_of')} != environment {env_as_of}"
            )

    coverage_as_of = None
    if isinstance(coverage_snapshot, Mapping):
        coverage_as_of = str(coverage_snapshot.get("as_of") or "") or None
        if coverage_as_of and env_as_of and coverage_as_of != env_as_of:
            advisories.append(
                f"record-level candidate_coverage_2026.json is dated {coverage_as_of} "
                f"while the environment snapshot is {env_as_of}: republish the collection "
                "coverage so a single answer exists to 'how many candidates do we have?'"
            )
        active = coverage_snapshot.get("active_local_records")
        if isinstance(active, int) and active != int(local_layer.get("resolved_cells") or 0):
            advisories.append(
                f"record-level active_local_records {active} != environment resolved cells "
                f"{local_layer.get('resolved_cells')}"
            )
        regional_records = coverage_snapshot.get("regional_records")
        if isinstance(regional_records, int) and regional_records > 0:
            advisories.append(
                f"record-level dataset reports {regional_records} regional records; these are "
                "rejected local rows, not a regional ballot, and must never be promoted into "
                "regional_ballot_cards"
            )
    else:
        advisories.append("record-level candidate coverage dataset not found in the repository")

    if divergences:
        status = "BLOCKED_LINEAGE_DIVERGENCE"
    elif advisories:
        status = "PASS_LINEAGE_PUBLISHED_TOGETHER_WITH_ADVISORY"
    else:
        status = "PASS_LINEAGE_PUBLISHED_TOGETHER"
    return {
        "status": status,
        "cell_census_path": cell_census_path,
        "coverage_path": coverage_path,
        "environment_as_of": env_as_of or None,
        "cell_census_as_of": (cell_census or {}).get("as_of"),
        "record_coverage_as_of": coverage_as_of,
        "environment_candidate_cells": local_layer.get("cells"),
        "environment_resolved_cells": local_layer.get("resolved_cells"),
        "divergences": divergences,
        "advisories": advisories,
    }


def gate_testability(
    layers: Mapping[str, Mapping[str, Any]], memory: Mapping[str, Any]
) -> dict[str, str]:
    usable = {name: str(layer.get("state")) in USABLE_LAYER_STATES for name, layer in layers.items()}
    return {
        "BR0_INTEGRITY": TESTABLE,
        "BR1_LOCAL": TESTABLE if usable.get("LOCAL_CANDIDATES") else NOT_TESTABLE,
        "BR1_REGIONAL": TESTABLE if usable.get("REGIONAL_BALLOT") else NOT_TESTABLE,
        "BR2_PERSONA": TESTABLE,
        "BR3_CANDIDATE": TESTABLE if usable.get("LOCAL_CANDIDATES") else NOT_TESTABLE,
        "BR4_PROGRAMME": TESTABLE if usable.get("PARTY_PROGRAMMES") else NOT_TESTABLE,
        "BR5_PARTY_MEMORY": (
            TESTABLE if int(memory.get("voters_with_prior_vote_memory") or 0) > 0 else NOT_TESTABLE
        ),
        "BR6_TURNOUT": TESTABLE,
        "BR7_PLACEBO": TESTABLE,
        "BR8_POV": TESTABLE,
        "SPLIT_TICKET": TESTABLE if usable.get("REGIONAL_BALLOT") else NOT_TESTABLE,
    }


def build_certificate(
    *,
    named_input: Mapping[str, Any],
    named_input_sha256: str,
    coverage_snapshot: Mapping[str, Any] | None = None,
    coverage_path: str | None = None,
    cell_census: Mapping[str, Any] | None = None,
    cell_census_path: str | None = None,
    rich_population_certificate: Mapping[str, Any] | None = None,
    rich_population_certificate_path: str | None = None,
    regional_dataset: Mapping[str, Any] | None = None,
    programme_dataset: Mapping[str, Any] | None = None,
    environment_id: str | None = None,
) -> dict[str, Any]:
    local_layer = measure_local_candidates(
        named_input.get("candidacies") or [], territories=named_input.get("territories") or []
    )
    programme_layer = measure_party_programmes(named_input.get("programmes") or [])
    if isinstance(programme_dataset, Mapping):
        programme_layer = {
            **programme_layer,
            "external_programme_dataset_rows": len(programme_dataset.get("rows") or []),
            "external_programme_dataset_status": programme_dataset.get("status"),
        }
    regional_layer = measure_regional_ballot(named_input, regional_dataset=regional_dataset)
    rich_layer = measure_rich_voter_state(
        named_input, rich_population_certificate=rich_population_certificate
    )
    layers = {
        "LOCAL_CANDIDATES": local_layer,
        "PARTY_PROGRAMMES": programme_layer,
        "REGIONAL_BALLOT": regional_layer,
        "RICH_VOTER_STATE": rich_layer,
    }
    for name, layer in layers.items():
        if str(layer.get("state")) not in LAYER_STATES:
            raise P3DataLayerError(f"layer {name} produced an illegal state {layer.get('state')!r}")
    memory = measure_party_memory(named_input)
    lineage = check_lineage(
        local_layer=local_layer,
        named_input=named_input,
        named_input_sha256=named_input_sha256,
        cell_census=cell_census,
        cell_census_path=cell_census_path,
        coverage_snapshot=coverage_snapshot,
        coverage_path=coverage_path,
    )
    gates = gate_testability(layers, memory)
    placeholders = sorted(name for name, layer in layers.items() if layer["state"] == "PLACEHOLDER")
    missing = sorted(name for name, layer in layers.items() if layer["state"] == "MISSING")
    disconnected = sorted(name for name, layer in layers.items() if layer["state"] == "DISCONNECTED")

    model_visibility = {
        name: (
            "MODEL_VISIBLE_AS_ELECTORAL_INFORMATION"
            if layer["state"] in USABLE_LAYER_STATES
            else "MODEL_VISIBLE_FOR_SUBSTANTIVE_VOTE_FALSE"
        )
        for name, layer in layers.items()
    }
    dual_ballot_allowed = str(regional_layer["state"]) in USABLE_LAYER_STATES
    blocking = list(lineage["divergences"])
    advisories = list(lineage["advisories"])
    if blocking:
        status = "BLOCKED_P3_DATA_LAYER_LINEAGE"
    elif advisories:
        status = "PASS_P3_DATA_LAYERS_CERTIFIED_WITH_LINEAGE_ADVISORY"
    else:
        status = "PASS_P3_DATA_LAYERS_CERTIFIED"
    certificate = {
        "schema_version": CERTIFICATE_SCHEMA,
        "certificate_id": "M26-P3-DATA-LAYER-CERTIFICATE-V1",
        "status": status,
        "environment_id": environment_id or str(named_input.get("artifact_id") or ""),
        "named_input_sha256": named_input_sha256,
        "snapshot_known_as_of": named_input.get("snapshot_known_as_of"),
        "regime_gate": named_input.get("regime_gate"),
        "layers": {name: dict(layer) for name, layer in layers.items()},
        "layer_states": {name: layer["state"] for name, layer in sorted(layers.items())},
        "model_visibility": dict(sorted(model_visibility.items())),
        "gate_testability": dict(sorted(gates.items())),
        "party_memory": memory,
        "lineage": lineage,
        "placeholder_layers": placeholders,
        "missing_layers": missing,
        "disconnected_layers": disconnected,
        "dual_ballot_simulation_allowed": dual_ballot_allowed,
        "regional_surface_fallback_allowed": False,
        "placeholder_presented_as_data": False,
        "blocking_findings": blocking,
        "advisory_findings": advisories,
        "inputs": {
            "candidate_coverage_path": coverage_path,
            "candidate_ballot_cell_census_path": cell_census_path,
            "rich_population_certificate_path": rich_population_certificate_path,
        },
        "interpretation_boundary": (
            "NOT_TESTABLE_MISSING_DATA is not a model failure. It states that the "
            "environment cannot feed the gate, so the gate carries no information "
            "about the voter mind."
        ),
    }
    certificate["certificate_sha256"] = sha256_json(certificate)
    return certificate


def assert_no_placeholder_is_model_visible(certificate: Mapping[str, Any]) -> None:
    """Fail closed if a PLACEHOLDER/MISSING layer would be shown as electoral data."""
    states = certificate.get("layer_states") or {}
    offenders = [
        name
        for name, visibility in (certificate.get("model_visibility") or {}).items()
        if visibility == "MODEL_VISIBLE_AS_ELECTORAL_INFORMATION"
        and states.get(name) not in USABLE_LAYER_STATES
    ]
    if offenders:
        raise P3DataLayerError(f"placeholder layers presented as data: {sorted(offenders)}")


def assert_regional_simulation_allowed(certificate: Mapping[str, Any]) -> None:
    if not certificate.get("dual_ballot_simulation_allowed"):
        raise P3DataLayerError(
            "REGIONAL_SURFACE_STATUS=MISSING: regional simulation is forbidden; "
            "the LOCAL ballot must not be copied and stripped to satisfy the schema"
        )


def load_certificate(path: pathlib.Path) -> dict[str, Any]:
    value = read_json(path)
    if not isinstance(value, Mapping) or value.get("schema_version") != CERTIFICATE_SCHEMA:
        raise P3DataLayerError(f"{path} is not a P3 data-layer certificate")
    stored = str(value.get("certificate_sha256") or "")
    recomputed = sha256_json({k: v for k, v in value.items() if k != "certificate_sha256"})
    if stored and stored != recomputed:
        raise P3DataLayerError(f"certificate hash mismatch: stored {stored}, recomputed {recomputed}")
    return dict(value)

from __future__ import annotations

"""R2 - reconnect the rich Moroccan population to the named 2026 pipeline.

The audit's most frustrating finding: a 158-field RGPH/ENCDM population exists,
is certified PASS, and its builders are in the repository, while the named 2026
pipeline feeds the model seven columns per voter. The data was not missing. It
was disconnected.

This module is the bridge. It joins a rich population to the named territories
by real territorial identifier and emits a `voter_population` block in which
each voter carries four clearly separated layers:

    individual        RGPH-observed person-level attributes
    household_context RGPH-observed dwelling-level attributes
    survey_stratum    Afrobarometer stratum means with their dispersion
    territory_context labour-market and territorial context

Three guards, all fail-closed:

* the prior-election anchor is dropped. In a current-vintage 2026 environment a
  `prior_vote_or_abstention` derived from a past result would import a sealed
  historical outcome into a snapshot that must not know it.
* forbidden identity fields are rejected outright, not filtered quietly.
* stratum means never enter the individual layer, so V9.1 can label them
  correctly instead of the bridge turning averages into biography.
"""

import hashlib
import json
import pathlib
from typing import Any, Iterable, Mapping, Sequence

BRIDGE_SCHEMA = "ATLAS_P3_RICH_NAMED_BRIDGE_V1"
BRIDGE_CERTIFICATE_SCHEMA = "ATLAS_P3_RICH_NAMED_BRIDGE_CERTIFICATE_V1"

STRATUM_PREFIX = "latent_attitude_"
STRATUM_METADATA_FIELDS = (
    "attitude_posterior_match_level",
    "attitude_posterior_stratum_n",
    "attitude_source",
)

# Dwelling-level attributes. Everything RGPH records about the household rather
# than about the person.
HOUSEHOLD_FIELDS = frozenset(
    {
        "household_size",
        "dwelling_type",
        "wall_material",
        "roof_material",
        "floor_material",
        "dwelling_age",
        "rooms",
        "tenure_status",
        "kitchen_available",
        "toilet_available",
        "bath_shower_available",
        "local_bath_available",
        "lighting_mode",
        "water_supply_mode",
        "wastewater_mode",
        "waste_disposal_mode",
        "gas_cooking",
        "electric_cooking",
        "charcoal_cooking",
        "wood_cooking",
        "livestock_status",
        "tv_owned",
        "radio_owned",
        "mobile_phone_owned",
        "fixed_phone_owned",
        "internet_owned",
        "computer_owned",
        "satellite_owned",
        "refrigerator_owned",
        "cars_count",
        "motorcycles_count",
        "trucks_count",
        "tractors_count",
        "paved_road_distance_km",
        "household_type",
        "household_children_count",
        "household_adult_count",
        "household_elderly_count",
        "household_worker_count",
        "household_unemployed_count",
        "household_student_count",
        "dependency_ratio",
        "persons_per_room",
        "asset_index",
        "basic_services_index",
        "head_sex",
        "head_age_band",
        "head_education_band",
    }
)

# Labour-market and territorial context. Not personal attributes.
CONTEXT_FIELD_PREFIXES = ("target_year_",)
CONTEXT_FIELDS = frozenset({"geography_confidence", "constituency_id", "parent_unit"})

# Sampling and identity plumbing, never a human dimension.
TECHNICAL_FIELDS = frozenset({"weight", "archetype_id", "population_weight"})

# Present in a rich record but forbidden in a current-vintage 2026 environment.
PRIOR_ELECTION_ANCHOR_FIELDS = frozenset({"prior_vote_or_abstention"})

FORBIDDEN_FIELDS = frozenset(
    {
        "religion",
        "ethnicity",
        "tribe",
        "nationality",
        "party_closeness",
        "vote_intention",
        "named_future_vote_preference",
        "target_outcome",
    }
)


class RichNamedBridgeError(ValueError):
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
        raise RichNamedBridgeError(f"cannot read JSON {path}: {exc}") from exc


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(
        pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RichNamedBridgeError(f"invalid JSONL {path}:{number}: {exc}") from exc
        if not isinstance(value, Mapping):
            raise RichNamedBridgeError(f"JSONL row {number} is not an object")
        rows.append(dict(value))
    return rows


def _is_stratum_field(field: str) -> bool:
    return str(field).startswith(STRATUM_PREFIX) or str(field) in STRATUM_METADATA_FIELDS


def _is_context_field(field: str) -> bool:
    name = str(field)
    return name in CONTEXT_FIELDS or name.startswith(CONTEXT_FIELD_PREFIXES)


def partition_fields(record: Mapping[str, Any]) -> dict[str, list[str]]:
    individual, household, stratum, context, technical, anchors, forbidden = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    for field in sorted(map(str, record)):
        if field in FORBIDDEN_FIELDS:
            forbidden.append(field)
        elif field in PRIOR_ELECTION_ANCHOR_FIELDS:
            anchors.append(field)
        elif field in TECHNICAL_FIELDS:
            technical.append(field)
        elif _is_stratum_field(field):
            stratum.append(field)
        elif field in HOUSEHOLD_FIELDS:
            household.append(field)
        elif _is_context_field(field):
            context.append(field)
        else:
            individual.append(field)
    return {
        "individual": individual,
        "household": household,
        "survey_stratum": stratum,
        "territory_context": context,
        "technical": technical,
        "prior_election_anchor": anchors,
        "forbidden": forbidden,
    }


def _stable_fraction(*parts: Any) -> float:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def select_archetypes(
    archetypes: Sequence[Mapping[str, Any]],
    *,
    count: int,
    territory_id: str,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    """Deterministic weight-proportional systematic selection.

    Systematic sampling on the cumulative weight axis keeps the selected subset
    close to the population marginals, and the start offset is a hash of
    (snapshot, territory) so the same environment always yields the same people.
    """
    rows = [dict(row) for row in archetypes]
    if not rows:
        raise RichNamedBridgeError(f"territory {territory_id} has no rich archetype")
    if count <= 0:
        raise RichNamedBridgeError("voters per territory must be positive")
    if count >= len(rows):
        return rows
    weights = []
    for row in rows:
        try:
            weight = float(row.get("weight") or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        weights.append(max(weight, 0.0))
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(rows)
        total = float(len(rows))
    step = total / count
    start = _stable_fraction(snapshot_id, territory_id) * step
    chosen: list[int] = []
    seen: set[int] = set()
    cumulative = 0.0
    index = 0
    for position in range(count):
        target = start + position * step
        while index < len(rows) - 1 and cumulative + weights[index] <= target:
            cumulative += weights[index]
            index += 1
        if index not in seen:
            seen.add(index)
            chosen.append(index)
    # A unit heavier than one sampling step can be hit twice. Fill the remaining
    # slots with the heaviest unselected units so the subset stays distinct and
    # the choice stays deterministic.
    if len(chosen) < count:
        remainder = sorted(
            (position for position in range(len(rows)) if position not in seen),
            key=lambda position: (-weights[position], position),
        )
        for position in remainder[: count - len(chosen)]:
            seen.add(position)
            chosen.append(position)
    return [rows[position] for position in sorted(chosen)]


def build_voter_row(
    record: Mapping[str, Any],
    *,
    archetype_label: str,
    overlay: Mapping[str, Any] | None,
    territory_context: Mapping[str, Any],
    allow_prior_election_anchor: bool,
) -> dict[str, Any]:
    partition = partition_fields(record)
    if partition["forbidden"]:
        raise RichNamedBridgeError(
            f"rich record carries forbidden identity fields: {partition['forbidden']}"
        )
    row: dict[str, Any] = {"weighted_archetype_id": archetype_label}
    rich_id = record.get("archetype_id")
    if rich_id is not None:
        row["rich_archetype_id"] = str(rich_id)
    for field in partition["individual"]:
        row[field] = record[field]
    household = {field: record[field] for field in partition["household"]}
    if household:
        row["household_context"] = household
    stratum: dict[str, Any] = {field: record[field] for field in partition["survey_stratum"]}
    if overlay:
        for field, value in overlay.items():
            if _is_stratum_field(field):
                stratum[field] = value
    if stratum:
        row["survey_stratum"] = stratum
    context = dict(territory_context)
    for field in partition["territory_context"]:
        context.setdefault(field, record[field])
    if context:
        row["territory_context"] = context
    row["prior_vote_or_abstention"] = (
        record.get("prior_vote_or_abstention") if allow_prior_election_anchor else None
    )
    if not allow_prior_election_anchor:
        row["prior_election_anchor_withheld"] = "CURRENT_VINTAGE_2026_SEALED_HISTORICAL_OUTCOME"
    weight = record.get("weight")
    if weight is not None:
        row["weight"] = weight
    return row


def _territory_lookup(
    rich_population: Mapping[str, Any], crosswalk: Mapping[str, str] | None
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for territory in rich_population.get("territories") or []:
        key = str(territory.get("constituency_id") or territory.get("territory_id") or "")
        if key:
            index[key] = dict(territory)
    if not crosswalk:
        return index
    resolved: dict[str, dict[str, Any]] = {}
    for named_id, rich_id in crosswalk.items():
        if str(rich_id) in index:
            resolved[str(named_id)] = index[str(rich_id)]
    return resolved


def _overlay_index(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("constituency_id") or ""), str(row.get("archetype_id") or ""))
        index[key] = dict(row)
    return index


def bridge_rich_population(
    *,
    named_input: Mapping[str, Any],
    rich_population: Mapping[str, Any],
    attitude_overlay_rows: Sequence[Mapping[str, Any]] = (),
    crosswalk: Mapping[str, str] | None = None,
    voters_per_territory: int = 32,
    allow_prior_election_anchor: bool = False,
    snapshot_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (named_input_with_rich_voters, bridge_certificate)."""
    snapshot_id = snapshot_id or str(named_input.get("vintage_snapshot_sha256") or "")
    territory_index = _territory_lookup(rich_population, crosswalk)

    # The identity guard scans the whole population, not the sampled subset: a
    # forbidden field must fail the build whether or not sampling happened to
    # pick the record that carries it.
    for territory in rich_population.get("territories") or []:
        for record in territory.get("archetypes") or []:
            offending = sorted(FORBIDDEN_FIELDS.intersection(map(str, record)))
            if offending:
                raise RichNamedBridgeError(
                    f"rich record {record.get('archetype_id')!r} carries forbidden identity "
                    f"fields: {offending}"
                )

    overlay_index = _overlay_index(attitude_overlay_rows)
    named_territories = [str(item.get("territory_id")) for item in named_input.get("territories") or []]
    if not named_territories:
        raise RichNamedBridgeError("named input declares no territory")

    batches: list[dict[str, Any]] = []
    matched: list[str] = []
    unmatched: list[str] = []
    partition_report: dict[str, list[str]] = {}
    overlay_hits = 0
    anchors_dropped = 0
    for territory_id in named_territories:
        territory = territory_index.get(territory_id)
        if territory is None:
            unmatched.append(territory_id)
            continue
        matched.append(territory_id)
        rich_constituency = str(territory.get("constituency_id") or territory_id)
        territory_context: dict[str, Any] = {}
        for key in ("geography_confidence", "parent_unit", "urban_share"):
            if territory.get(key) is not None:
                territory_context[key] = territory[key]
        for key, value in (rich_population.get("target_year_update") or {}).items():
            if not isinstance(value, (dict, list)):
                territory_context[f"target_year_{key}"] = value
        archetypes = territory.get("archetypes") or []
        selected = select_archetypes(
            archetypes,
            count=voters_per_territory,
            territory_id=territory_id,
            snapshot_id=snapshot_id,
        )
        voters = []
        for position, record in enumerate(selected, 1):
            label = f"A{position:03d}"
            overlay = overlay_index.get((rich_constituency, str(record.get("archetype_id") or "")))
            if overlay:
                overlay_hits += 1
            row = build_voter_row(
                record,
                archetype_label=label,
                overlay=overlay,
                territory_context=territory_context,
                allow_prior_election_anchor=allow_prior_election_anchor,
            )
            if not allow_prior_election_anchor and record.get("prior_vote_or_abstention") is not None:
                anchors_dropped += 1
            voters.append(row)
            if not partition_report:
                partition_report = partition_fields(record)
        batches.append(
            {
                "batch_id": "B01",
                "territory_id": territory_id,
                "rich_constituency_id": rich_constituency,
                "voters": voters,
            }
        )

    if not batches:
        raise RichNamedBridgeError(
            "no named territory could be matched to a rich constituency; supply a crosswalk"
        )

    result = json.loads(json.dumps(named_input, ensure_ascii=False))
    result["voter_population"] = {
        "known_as_of": (named_input.get("voter_population") or {}).get("known_as_of")
        or named_input.get("snapshot_known_as_of"),
        "batches": batches,
        "population_source": "ASV2_RICH_POPULATION_V2",
        "population_id": rich_population.get("population_id"),
        "rich_population_sha256": sha256_json(rich_population),
    }
    result["territories"] = [
        item for item in result.get("territories") or [] if str(item.get("territory_id")) in set(matched)
    ]
    result["candidacies"] = [
        item for item in result.get("candidacies") or [] if str(item.get("territory_id")) in set(matched)
    ]

    voters_total = sum(len(batch["voters"]) for batch in batches)
    sample_row = batches[0]["voters"][0]
    individual_width = len(
        [
            key
            for key in sample_row
            if key not in {"household_context", "survey_stratum", "territory_context", "weight"}
        ]
    )
    certificate = {
        "schema_version": BRIDGE_CERTIFICATE_SCHEMA,
        "certificate_id": "M26-P3-RICH-NAMED-BRIDGE-CERTIFICATE-V1",
        "status": "PASS_RICH_NAMED_BRIDGE" if not unmatched else "PASS_RICH_NAMED_BRIDGE_PARTIAL",
        "bridge_schema": BRIDGE_SCHEMA,
        "join_key": "real territorial identifier (named territory_id <-> rich constituency_id)",
        "sealed_mapping_opened": False,
        "target_outcomes_opened": False,
        "named_territories": len(named_territories),
        "matched_territories": sorted(matched),
        "unmatched_territories": sorted(unmatched),
        "voters_per_territory": voters_per_territory,
        "voter_rows": voters_total,
        "selection_rule": "deterministic weight-proportional systematic sampling seeded by (snapshot_id, territory_id)",
        "archetype_identity_note": (
            "The named A001..ANNN labels are re-issued from the rich population. They are NOT "
            "the archetypes of the 2026-08-23 pilot: no traceable mapping exists between the "
            "seven-column named rows and the rich population, so any comparison with that pilot "
            "is between populations, not paired."
        ),
        "field_partition": partition_report,
        "individual_fields_per_voter": individual_width,
        "household_fields_per_voter": len(sample_row.get("household_context") or {}),
        "survey_stratum_fields_per_voter": len(sample_row.get("survey_stratum") or {}),
        "territory_context_fields_per_voter": len(sample_row.get("territory_context") or {}),
        "attitude_overlay_rows_matched": overlay_hits,
        "prior_election_anchor_allowed": allow_prior_election_anchor,
        "prior_election_anchors_dropped": anchors_dropped,
        "prior_election_anchor_policy": (
            "A prior_vote_or_abstention derived from a past result is a historical outcome. "
            "It stays out of a current-vintage 2026 environment unless explicitly authorised."
        ),
        "stratum_fields_kept_out_of_individual_layer": True,
        "forbidden_fields_present": False,
        "rich_population_sha256": sha256_json(rich_population),
        "named_input_sha256": sha256_json(named_input),
    }
    certificate["output_named_input_sha256"] = sha256_json(result)
    certificate["certificate_sha256"] = sha256_json(certificate)
    return result, certificate

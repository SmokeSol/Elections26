from __future__ import annotations

"""R4/R5 - the two electoral surfaces that were never collected.

The 2026 "programmes" in the named input are the same alphabetical list of
eighteen axes rotated per party, every cell saying only that a position exists.
The regional ballot does not exist at all: V8 has the slot, the pipeline never
fills it, and the fallback quietly rebuilt the local ballot with the candidate
erased.

This module defines what real collection has to deliver, validates it, and
ingests it. It contains no positions and no regional lists: collecting those is
field work, and the canonical datasets ship empty and honest until it happens.

Two rules govern both datasets:

    NO SOURCE -> UNKNOWN, never NO SOURCE -> a synthetic value
    a pre-2026 position is labelled PRE_2026_PARTY_POSITION and is never
    presented as the 2026 programme
"""

import copy
import hashlib
import json
import pathlib
from datetime import date
from typing import Any, Mapping, Sequence

PROGRAMME_DATASET_SCHEMA = "ATLAS_PARTY_PROGRAMME_2026_V1"
REGIONAL_DATASET_SCHEMA = "ATLAS_REGIONAL_BALLOT_2026_V1"

PROGRAMME_COLLECTED_STATUS = "PASS_PARTY_PROGRAMME_2026_COLLECTED"
PROGRAMME_NOT_COLLECTED_STATUS = "NOT_COLLECTED_PARTY_PROGRAMME_2026"
REGIONAL_COLLECTED_STATUS = "PASS_REGIONAL_BALLOT_2026_COLLECTED"
REGIONAL_MISSING_STATUS = "MISSING_REGIONAL_BALLOT_2026"

PROGRAMME_ROW_STATES = frozenset(
    {
        "PUBLISHED_2026_PROGRAMME",
        "PARTIALLY_PUBLISHED_2026_PROGRAMME",
        "NOT_YET_PUBLISHED_AS_OF_SNAPSHOT",
        "NOT_COLLECTED",
        "UNKNOWN",
    }
)
PROGRAMME_ROW_STATES_WITH_CONTENT = frozenset(
    {"PUBLISHED_2026_PROGRAMME", "PARTIALLY_PUBLISHED_2026_PROGRAMME"}
)

REGIONAL_ROW_STATES = frozenset(
    {"OFFICIAL_CONFIRMED", "DECLARED_BY_PARTY", "REPORTED_UNCONFIRMED", "UNKNOWN_AS_OF_SNAPSHOT", "NO_LIST_EVIDENCED"}
)
REGIONAL_ROW_STATES_WITH_CONTENT = frozenset(
    {"OFFICIAL_CONFIRMED", "DECLARED_BY_PARTY", "REPORTED_UNCONFIRMED"}
)

PRE_2026_LABEL = "PRE_2026_PARTY_POSITION"

# Rejected local rows from the medias24 snapshot. They are a rejection label,
# not a regional candidacy, and must never become a regional list head.
FORBIDDEN_REGIONAL_PROVENANCE = frozenset({"REGIONAL_OR_MISSING", "UNRESOLVED_NO_CERTIFIED_ALIAS"})


class ElectoralOfferError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ElectoralOfferError(f"cannot read JSON {path}: {exc}") from exc


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ElectoralOfferError(f"{field} must be an ISO date, got {value!r}") from exc


def validate_programme_dataset(
    dataset: Mapping[str, Any], *, snapshot_date: str | None = None
) -> dict[str, Any]:
    if dataset.get("schema_version") != PROGRAMME_DATASET_SCHEMA:
        raise ElectoralOfferError("unexpected party programme dataset schema")
    status = str(dataset.get("status") or "")
    if status not in {PROGRAMME_COLLECTED_STATUS, PROGRAMME_NOT_COLLECTED_STATUS}:
        raise ElectoralOfferError(f"invalid programme dataset status {status!r}")
    rows = dataset.get("rows")
    if not isinstance(rows, list):
        raise ElectoralOfferError("programme dataset rows must be a list")
    cutoff = _parse_date(snapshot_date, "snapshot_date") if snapshot_date else None
    seen: set[str] = set()
    axis_cells = 0
    substantive_cells = 0
    parties_with_content: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ElectoralOfferError("programme row is not an object")
        party_id = str(row.get("party_id") or "")
        if not party_id or party_id in seen:
            raise ElectoralOfferError(f"invalid/duplicate party_id {party_id!r}")
        seen.add(party_id)
        row_state = str(row.get("programme_2026_status") or "")
        if row_state not in PROGRAMME_ROW_STATES:
            raise ElectoralOfferError(f"{party_id}: invalid programme_2026_status {row_state!r}")
        known = row.get("known_as_of")
        if known:
            parsed = _parse_date(known, f"{party_id}.known_as_of")
            if cutoff and parsed > cutoff:
                raise ElectoralOfferError(f"{party_id}: known_as_of after the snapshot")
        axes = row.get("axes") or {}
        if not isinstance(axes, Mapping):
            raise ElectoralOfferError(f"{party_id}: axes must be an object")
        if row_state in PROGRAMME_ROW_STATES_WITH_CONTENT:
            for field in ("source_document", "source_url", "document_sha256", "publication_date"):
                if not row.get(field):
                    raise ElectoralOfferError(
                        f"{party_id}: {row_state} requires {field}; NO SOURCE means UNKNOWN"
                    )
            _parse_date(row["publication_date"], f"{party_id}.publication_date")
        elif axes:
            raise ElectoralOfferError(
                f"{party_id}: axes present while status is {row_state}; an uncollected programme has no positions"
            )
        party_content = 0
        for axis_id, cell in axes.items():
            axis_cells += 1
            if not isinstance(cell, Mapping):
                raise ElectoralOfferError(f"{party_id}/{axis_id}: cell must be an object")
            label = str(cell.get("temporal_label") or "PROGRAMME_2026")
            if label not in {"PROGRAMME_2026", PRE_2026_LABEL}:
                raise ElectoralOfferError(f"{party_id}/{axis_id}: invalid temporal_label {label!r}")
            summary = str(cell.get("actual_position_summary") or "").strip()
            if not summary:
                raise ElectoralOfferError(
                    f"{party_id}/{axis_id}: an axis cell must carry the position itself, "
                    "not the statement that a position exists"
                )
            if not (cell.get("evidence_ids") or cell.get("source_url")):
                raise ElectoralOfferError(f"{party_id}/{axis_id}: position without evidence")
            if label == "PROGRAMME_2026":
                substantive_cells += 1
                party_content += 1
        if party_content:
            parties_with_content.append(party_id)
    return {
        "status": "PASS_PARTY_PROGRAMME_2026_DATASET_VALID",
        "dataset_status": status,
        "parties": len(rows),
        "axis_cells": axis_cells,
        "substantive_2026_position_cells": substantive_cells,
        "parties_with_2026_positions": sorted(parties_with_content),
        "dataset_sha256": sha256_json(dataset),
    }


def validate_regional_dataset(
    dataset: Mapping[str, Any], *, snapshot_date: str | None = None
) -> dict[str, Any]:
    if dataset.get("schema_version") != REGIONAL_DATASET_SCHEMA:
        raise ElectoralOfferError("unexpected regional ballot dataset schema")
    status = str(dataset.get("status") or "")
    if status not in {REGIONAL_COLLECTED_STATUS, REGIONAL_MISSING_STATUS}:
        raise ElectoralOfferError(f"invalid regional dataset status {status!r}")
    rows = dataset.get("rows")
    if not isinstance(rows, list):
        raise ElectoralOfferError("regional dataset rows must be a list")
    if status == REGIONAL_MISSING_STATUS and rows:
        raise ElectoralOfferError("a MISSING regional dataset may not carry rows")
    cutoff = _parse_date(snapshot_date, "snapshot_date") if snapshot_date else None
    regions: set[str] = set()
    seen: set[tuple[str, str]] = set()
    with_head = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ElectoralOfferError("regional row is not an object")
        region_id = str(row.get("region_id") or "")
        party_id = str(row.get("party_id") or "")
        if not region_id or not party_id:
            raise ElectoralOfferError("regional row needs region_id and party_id")
        key = (region_id, party_id)
        if key in seen:
            raise ElectoralOfferError(f"duplicate regional cell {key}")
        seen.add(key)
        regions.add(region_id)
        row_state = str(row.get("verification_state") or "")
        if row_state not in REGIONAL_ROW_STATES:
            raise ElectoralOfferError(f"{key}: invalid verification_state {row_state!r}")
        provenance = str(row.get("provenance_label") or "")
        if provenance in FORBIDDEN_REGIONAL_PROVENANCE:
            raise ElectoralOfferError(
                f"{key}: {provenance} is a local-matching rejection label, not a regional candidacy"
            )
        known = row.get("known_as_of")
        if known:
            parsed = _parse_date(known, f"{key}.known_as_of")
            if cutoff and parsed > cutoff:
                raise ElectoralOfferError(f"{key}: known_as_of after the snapshot")
        if row_state in REGIONAL_ROW_STATES_WITH_CONTENT:
            if not row.get("sources"):
                raise ElectoralOfferError(f"{key}: verified regional cell without a source")
            if row.get("list_head_name"):
                with_head += 1
        elif row.get("list_head_name"):
            raise ElectoralOfferError(f"{key}: named list head declared under {row_state}")
    return {
        "status": "PASS_REGIONAL_BALLOT_2026_DATASET_VALID",
        "dataset_status": status,
        "rows": len(rows),
        "regions": len(regions),
        "rows_with_named_list_head": with_head,
        "dataset_sha256": sha256_json(dataset),
    }


def ingest_programmes(
    named_input: Mapping[str, Any], dataset: Mapping[str, Any], *, snapshot_date: str | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replace the synthetic scaffold with measured positions.

    A party without a collected 2026 programme ends with an empty axes object and
    an explicit status, never with a rotation.
    """
    report = validate_programme_dataset(dataset, snapshot_date=snapshot_date)
    by_party = {str(row.get("party_id")): dict(row) for row in dataset.get("rows") or []}
    result = json.loads(json.dumps(named_input, ensure_ascii=False))
    programmes = []
    replaced = 0
    emptied = 0
    for programme in result.get("programmes") or []:
        party_id = str(programme.get("party_id") or "")
        row = by_party.get(party_id)
        new_axes: dict[str, Any] = {}
        if row and str(row.get("programme_2026_status")) in PROGRAMME_ROW_STATES_WITH_CONTENT:
            for axis_id, cell in (row.get("axes") or {}).items():
                if str(cell.get("temporal_label") or "PROGRAMME_2026") != "PROGRAMME_2026":
                    continue
                new_axes[str(axis_id)] = {
                    "verification_state": "PUBLISHED_PARTY_PROGRAMME",
                    "national_salience_rank": cell.get("national_salience_rank", 9999),
                    "actual_position_summary": cell.get("actual_position_summary"),
                    "commitments": list(cell.get("commitments") or []),
                    "confidence": cell.get("confidence"),
                }
            replaced += 1
        else:
            emptied += 1
        programmes.append(
            {
                **{k: v for k, v in programme.items() if k != "axes"},
                "axes": new_axes,
                "programme_2026_status": (row or {}).get("programme_2026_status", "NOT_COLLECTED"),
                "source_document": (row or {}).get("source_document"),
                "source_url": (row or {}).get("source_url"),
                "document_sha256": (row or {}).get("document_sha256"),
                "publication_date": (row or {}).get("publication_date"),
            }
        )
    result["programmes"] = programmes
    result["party_programme_2026_dataset_sha256"] = report["dataset_sha256"]
    report = {
        **report,
        "parties_with_positions_injected": replaced,
        "parties_left_without_positions": emptied,
        "synthetic_rotation_removed": True,
    }
    return result, report


def regional_cards_for_region(
    dataset: Mapping[str, Any], *, region_id: str, ballot_party_ids: Sequence[str]
) -> list[dict[str, Any]]:
    rows = {
        str(row.get("party_id")): dict(row)
        for row in dataset.get("rows") or []
        if str(row.get("region_id")) == str(region_id)
    }
    cards = []
    for party_id in ballot_party_ids:
        row = rows.get(str(party_id))
        if row is None:
            cards.append(
                {
                    "party_id": str(party_id),
                    "regional_candidate": None,
                    "region_specific_candidate_information_present": False,
                    "regional_list_state": "UNKNOWN_AS_OF_SNAPSHOT",
                }
            )
            continue
        state = str(row.get("verification_state") or "UNKNOWN_AS_OF_SNAPSHOT")
        has_head = state in REGIONAL_ROW_STATES_WITH_CONTENT and bool(row.get("list_head_name"))
        cards.append(
            {
                "party_id": str(party_id),
                "regional_list_state": state,
                "regional_candidate": (
                    {
                        "candidate_name": row.get("list_head_name"),
                        "verification_state": state,
                        "known_as_of": row.get("known_as_of"),
                    }
                    if has_head
                    else None
                ),
                "region_specific_candidate_information_present": has_head,
                "regional_list_name": row.get("list_name"),
            }
        )
    return cards


def attach_regional_ballot_cards(
    environment_root: pathlib.Path,
    dataset: Mapping[str, Any],
    *,
    territory_region: Mapping[str, str],
    snapshot_date: str | None = None,
) -> dict[str, Any]:
    """Attach a real regional surface to a built named environment.

    Additive: `voter_named_surface` in the frozen three_regime_core is not
    touched. The cards land on each voter's `known_electoral_surface`, which is
    exactly the slot `build_subjective_electoral_world` already reads.
    """
    report = validate_regional_dataset(dataset, snapshot_date=snapshot_date)
    if report["dataset_status"] != REGIONAL_COLLECTED_STATUS:
        raise ElectoralOfferError(
            "regional ballot dataset is not collected; the regional surface stays MISSING"
        )
    root = pathlib.Path(environment_root).expanduser().resolve()
    touched = 0
    voters = 0
    for path in sorted((root / "voter_batches").rglob("*.json")):
        batch = json.loads(path.read_text(encoding="utf-8"))
        territory_id = str(batch.get("anonymous_territory_id") or batch.get("territory_id") or "")
        region_id = str(territory_region.get(territory_id) or "")
        if not region_id:
            continue
        parties = [str(item) for item in batch.get("available_party_ids") or []]
        cards = regional_cards_for_region(dataset, region_id=region_id, ballot_party_ids=parties)
        if len(cards) < 2:
            continue
        for key in ("voter_archetypes", "archetypes", "voters"):
            rows = batch.get(key)
            if not isinstance(rows, list):
                continue
            for voter in rows:
                surface = voter.get("known_electoral_surface")
                if isinstance(surface, Mapping):
                    surface = dict(surface)
                    surface["regional_ballot_cards"] = copy.deepcopy(cards)
                    surface["regional_surface_source"] = "EXPLICIT_REGION_SPECIFIC_SURFACE"
                    voter["known_electoral_surface"] = surface
                    voters += 1
            batch[key] = rows
        path.write_text(
            json.dumps(batch, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        touched += 1
    return {
        **report,
        "batches_updated": touched,
        "voters_updated": voters,
        "regional_surface_source": "EXPLICIT_REGION_SPECIFIC_SURFACE",
    }

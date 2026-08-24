from __future__ import annotations

"""Overlay Empirical Moroccan Mind V9.1 onto a Behavioral Mind V8/V8.1 environment.

Three wiring defects of the V9 overlay are fixed here, none of which invents data:

* `household_context` was read from the voter *batch*, a key the named batch
  schema never emits, so the 15 household dimensions could not fire. V9.1 reads
  it per voter first, then per batch.
* `territory_context` had the same problem, while the territory record was
  sitting unread in `contexts/`. V9.1 builds the ecological map from the
  environment's own context files.
* `population_prior_relabelled_as_individual_fact` was written as a hard-coded
  `False`. V9.1 measures it over every mind it builds and refuses to write a
  manifest that certifies an absence it did not verify.
"""

import copy
import pathlib
import shutil
from typing import Any, Mapping

from .empirical_environment_v9 import (
    EmpiricalEnvironmentError,
    _set_voters,
    _voters,
    locate_v8_root,
    read_json,
    sha256_file,
    write_json,
)
from .empirical_mind_v9_1 import (
    ALLOWED_EPISTEMIC_STATUSES_V9_1,
    apply_registry_amendment,
    empiricalize_behavioral_voter_v9_1,
    sha256_json,
)
from .empirical_priors_v9 import (
    CALIBRATED_STATUS,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)
from .empirical_validation_v9_1 import audit_empirical_mind_v9_1

EMPIRICAL_ENV_V9_1_SCHEMA = "ATLAS_NAMED_2026_EMPIRICAL_MIND_ENVIRONMENT_V9_1"
EMPIRICAL_ENV_V9_1_STATUS_OBSERVED = "PASS_EMPIRICAL_MIND_V9_1_OBSERVED_AND_STRATUM_DIAGNOSTIC_READY"
EMPIRICAL_ENV_V9_1_STATUS_CALIBRATED = "PASS_EMPIRICAL_MIND_V9_1_CALIBRATED_PILOT_READY"
ACCEPTED_BASE_STATUSES = {
    "PASS_BEHAVIORAL_MIND_V8_ENVIRONMENT_READY",
    "PASS_BEHAVIORAL_MIND_V8_1_ENVIRONMENT_READY",
}


class EmpiricalEnvironmentV91Error(EmpiricalEnvironmentError):
    pass


def build_territory_context_map(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Read the ecological context the environment already carries.

    `contexts/<condition>/<territory>.json` holds the verified territory record.
    V9 never looked here, so ECOLOGICAL_CONTEXT_ONLY could never fire.
    """
    result: dict[str, dict[str, Any]] = {}
    context_root = root / "contexts"
    if not context_root.is_dir():
        return result
    for path in sorted(context_root.rglob("*.json")):
        context = read_json(path)
        if not isinstance(context, Mapping):
            continue
        territory_id = str(
            context.get("anonymous_territory_id") or context.get("territory_id") or ""
        )
        if not territory_id:
            continue
        territory = context.get("territory")
        flat: dict[str, Any] = {}
        if isinstance(territory, Mapping):
            for key, value in territory.items():
                if key == "verified_context" and isinstance(value, Mapping):
                    flat.update({str(k): v for k, v in value.items()})
                elif not isinstance(value, (dict, list)):
                    flat[str(key)] = value
        result.setdefault(territory_id, {}).update(flat)
    return result


def build_empirical_environment_v9_1(
    *,
    v8_root: pathlib.Path,
    output_root: pathlib.Path,
    base_dimension_registry: Mapping[str, Any],
    amendment: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_date: str,
    replicate_id: str = "R00",
    prompt_addendum_text: str | None = None,
    stratum_visibility: str = "context",
) -> dict[str, Any]:
    v8_root = locate_v8_root(v8_root)
    output_root = pathlib.Path(output_root).expanduser().resolve()
    base_manifest_path = v8_root / "behavioral_mind_environment_manifest.json"
    base_manifest = read_json(base_manifest_path)
    if base_manifest.get("status") not in ACCEPTED_BASE_STATUSES:
        raise EmpiricalEnvironmentV91Error(
            f"base environment status {base_manifest.get('status')!r} is not a valid V8/V8.1 base"
        )
    if base_manifest.get("target_outcomes_present") is not False:
        raise EmpiricalEnvironmentV91Error("target outcomes present in base environment")

    dimension_registry = apply_registry_amendment(base_dimension_registry, amendment)
    validate_dimension_registry(dimension_registry)
    validate_source_registry(source_registry, snapshot_date=snapshot_date)
    if prior_pack is not None:
        validate_prior_pack(
            prior_pack,
            source_registry=source_registry,
            dimension_registry=dimension_registry,
            snapshot_date=snapshot_date,
            require_calibrated=False,
        )
    if output_root == v8_root:
        raise EmpiricalEnvironmentV91Error("V9.1 overlay must not overwrite its base")
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(v8_root, output_root)

    territory_context_map = build_territory_context_map(output_root)
    snapshot_id = str(
        base_manifest.get("base_named_environment_manifest_sha256") or sha256_file(base_manifest_path)
    )

    audits: list[dict[str, Any]] = []
    batch_index: dict[tuple[str, str], dict[str, Any]] = {}
    voter_files = sorted((output_root / "voter_batches").rglob("*.json"))
    if not voter_files:
        raise EmpiricalEnvironmentV91Error("base environment contains no voter batches")
    for path in voter_files:
        batch = read_json(path)
        territory_id = str(batch.get("anonymous_territory_id") or batch.get("territory_id") or "")
        batch_household = (
            dict(batch["household_context"])
            if isinstance(batch.get("household_context"), Mapping)
            else {}
        )
        batch_territory = (
            dict(batch["territory_context"])
            if isinstance(batch.get("territory_context"), Mapping)
            else {}
        )
        ecological = {**territory_context_map.get(territory_id, {}), **batch_territory}
        rows = []
        for voter in _voters(batch):
            household = (
                dict(voter["household_context"])
                if isinstance(voter.get("household_context"), Mapping)
                else batch_household
            )
            voter_ecological = (
                {**ecological, **dict(voter["territory_context"])}
                if isinstance(voter.get("territory_context"), Mapping)
                else ecological
            )
            visible, audit = empiricalize_behavioral_voter_v9_1(
                voter,
                dimension_registry=dimension_registry,
                source_registry=source_registry,
                prior_pack=prior_pack,
                snapshot_id=snapshot_id,
                snapshot_date=snapshot_date,
                replicate_id=replicate_id,
                household=household,
                ecological_context=voter_ecological,
                stratum_visibility=stratum_visibility,
            )
            rows.append(visible)
            full_mind = audit.get("full_empirical_mind")
            if not isinstance(full_mind, Mapping):
                raise EmpiricalEnvironmentV91Error("full empirical mind missing from audit")
            gate = audit_empirical_mind_v9_1(
                full_mind,
                dimension_registry=dimension_registry,
                source_registry=source_registry,
                prior_pack=prior_pack,
                snapshot_date=snapshot_date,
                forecast_lambda=0.0,
                paired_tests={},
            )
            audits.append(
                {
                    "territory_id": territory_id,
                    "batch_id": batch.get("batch_id"),
                    "weighted_archetype_id": visible.get("weighted_archetype_id")
                    or visible.get("archetype_id"),
                    "mind_audit": {k: v for k, v in audit.items() if k != "full_empirical_mind"},
                    "gate_report": gate,
                }
            )
        _set_voters(batch, rows)
        batch["schema_version"] = "ATLAS_NAMED_2026_VOTER_BATCH_EMPIRICAL_MIND_V9_1"
        batch["empirical_moroccan_mind_present"] = True
        batch["population_priors_are_individual_facts"] = False
        write_json(path, batch)
        batch_index[(territory_id, str(batch.get("batch_id") or ""))] = batch

    packet_root = output_root / "packets"
    if packet_root.is_dir():
        for path in sorted(packet_root.rglob("*.json")):
            packet = read_json(path)
            key = (
                str(packet.get("anonymous_territory_id") or packet.get("territory_id") or ""),
                str(packet.get("batch_id") or ""),
            )
            if key in batch_index:
                packet["voter_batch"] = copy.deepcopy(batch_index[key])
                packet["schema_version"] = "ATLAS_NAMED_2026_PACKET_EMPIRICAL_MIND_V9_1"
                packet["empirical_moroccan_mind_present"] = True
                write_json(path, packet)

    prompt_path = output_root / "as2_full_environment_prompt_v2.md"
    if prompt_addendum_text:
        original_prompt = prompt_path.read_text(encoding="utf-8")
        marker = "# Empirical Moroccan Mind V9.1 addendum"
        if marker not in original_prompt:
            prompt_path.write_text(
                original_prompt.rstrip() + "\n\n" + prompt_addendum_text.strip() + "\n",
                encoding="utf-8",
            )

    # Measured, not asserted.
    relabelled = [
        record["weighted_archetype_id"]
        for record in audits
        if record["mind_audit"]["epistemic_audit"]["population_prior_relabelled_as_individual_fact"]
    ]
    em2_failures = [
        record["weighted_archetype_id"]
        for record in audits
        if not record["gate_report"]["gates"]["EM2_NO_POPULATION_OR_ECOLOGICAL_TO_INDIVIDUAL_OVERCLAIM"]
    ]
    if relabelled or em2_failures:
        raise EmpiricalEnvironmentV91Error(
            f"EM2 measured as violated for {sorted(set(relabelled) | set(em2_failures))[:5]}"
        )

    dimension_total = sum(int(record["mind_audit"]["dimensions"]) for record in audits)
    populated_total = sum(int(record["mind_audit"]["populated_dimensions"]) for record in audits)
    epistemic_totals = {
        status: sum(
            int(record["mind_audit"]["epistemic_counts"].get(status, 0)) for record in audits
        )
        for status in sorted(ALLOWED_EPISTEMIC_STATUSES_V9_1)
    }
    unknown_total = epistemic_totals["UNKNOWN"]

    audit_index = {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_V9_1_AUDIT_INDEX_V1",
        "voters": audits,
        "audit_index_sha256": sha256_json(audits),
    }
    write_json(output_root / "empirical_mind_audit_index.json", audit_index)
    write_json(output_root / "empirical_mind_dimensions_v9_1_effective.json", dimension_registry)

    calibrated = bool(prior_pack and prior_pack.get("status") == CALIBRATED_STATUS)
    voters = max(1, len(audits))
    manifest = {
        "schema_version": EMPIRICAL_ENV_V9_1_SCHEMA,
        "status": EMPIRICAL_ENV_V9_1_STATUS_CALIBRATED
        if calibrated
        else EMPIRICAL_ENV_V9_1_STATUS_OBSERVED,
        "amendment_id": amendment.get("amendment_id"),
        "base_manifest_sha256": sha256_file(base_manifest_path),
        "base_environment_status": base_manifest.get("status"),
        "ballots_simulated": base_manifest.get("ballots_simulated"),
        "regional_surface_status": base_manifest.get("regional_surface_status"),
        "target_outcomes_present": False,
        "snapshot_date": snapshot_date,
        "replicate_id": replicate_id,
        "empirical_moroccan_mind_present": True,
        "calibrated_prior_pack_present": calibrated,
        "population_prior_relabelled_as_individual_fact": bool(relabelled),
        "population_prior_relabelled_assertion_is_measured": True,
        "raw_microdata_embedded": False,
        "base_dimension_registry_sha256": sha256_json(base_dimension_registry),
        "effective_dimension_registry_sha256": sha256_json(dimension_registry),
        "amendment_sha256": sha256_json(amendment),
        "source_registry_sha256": sha256_json(source_registry),
        "prior_pack_sha256": sha256_json(prior_pack) if prior_pack else None,
        "dimensions_per_voter": dimension_total // voters,
        "voter_rows": len(audits),
        "mean_populated_dimensions_per_voter": round(populated_total / voters, 6),
        "mean_unknown_dimension_share": round(unknown_total / max(1, dimension_total), 6),
        "epistemic_totals": epistemic_totals,
        "survey_stratum_model_visibility": str(stratum_visibility).lower(),
        "territory_context_wired": bool(territory_context_map),
        "territory_context_territories": len(territory_context_map),
        "startup_work_item_cap": 1,
        "scale_allowed": False,
        "scale_blockers": [
            "EM3 calibrated Moroccan prior pack",
            "EM4 marginal/subgroup/correlation validation",
            "EM6-EM8 paired behavioral and POV tests",
            "historical out-of-sample validation before lambda may differ from zero",
        ],
        "prompt_addendum_present": bool(prompt_addendum_text),
        "prompt_sha256": sha256_file(prompt_path),
        "audit_index_sha256": sha256_file(output_root / "empirical_mind_audit_index.json"),
    }
    write_json(output_root / "empirical_mind_environment_manifest.json", manifest)
    write_json(output_root / "empirical_mind_v9_1_manifest.json", manifest)
    return manifest

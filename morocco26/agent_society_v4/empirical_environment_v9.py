from __future__ import annotations

"""Overlay Empirical Moroccan Mind V9 onto a Behavioral Mind V8 environment."""

import copy
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
from typing import Any, Mapping

from .empirical_mind_v9 import empiricalize_behavioral_voter, sha256_json
from .empirical_priors_v9 import (
    CALIBRATED_STATUS,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)
from .empirical_validation_v9 import audit_empirical_mind

EMPIRICAL_ENV_SCHEMA = "ATLAS_NAMED_2026_EMPIRICAL_MIND_ENVIRONMENT_V9"
EMPIRICAL_ENV_STATUS_OBSERVED = "PASS_EMPIRICAL_MIND_V9_OBSERVED_ONLY_DIAGNOSTIC_READY"
EMPIRICAL_ENV_STATUS_CALIBRATED = "PASS_EMPIRICAL_MIND_V9_CALIBRATED_PILOT_READY"
BASE_V8_STATUS = "PASS_BEHAVIORAL_MIND_V8_ENVIRONMENT_READY"


class EmpiricalEnvironmentError(ValueError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmpiricalEnvironmentError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def locate_v8_root(root: pathlib.Path) -> pathlib.Path:
    root = root.expanduser().resolve()
    if (root / "behavioral_mind_environment_manifest.json").is_file():
        return root
    hits = sorted(root.rglob("behavioral_mind_environment_manifest.json"), key=lambda p: len(p.parts))
    if len(hits) != 1:
        raise EmpiricalEnvironmentError(
            f"expected exactly one V8 manifest; found {len(hits)}"
        )
    return hits[0].parent


def _voters(batch: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("voter_archetypes", "archetypes", "voters"):
        if isinstance(batch.get(key), list):
            return [dict(row) for row in batch[key]]
    raise EmpiricalEnvironmentError("voter batch has no voter array")


def _set_voters(batch: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for key in ("voter_archetypes", "archetypes", "voters"):
        if isinstance(batch.get(key), list):
            batch[key] = rows
            return
    raise EmpiricalEnvironmentError("cannot replace voter rows")


def build_empirical_environment(
    *,
    v8_root: pathlib.Path,
    output_root: pathlib.Path,
    dimension_registry: Mapping[str, Any],
    source_registry: Mapping[str, Any],
    prior_pack: Mapping[str, Any] | None,
    snapshot_date: str,
    replicate_id: str = "R00",
    prompt_addendum_text: str | None = None,
) -> dict[str, Any]:
    v8_root = locate_v8_root(v8_root)
    output_root = output_root.expanduser().resolve()
    base_manifest_path = v8_root / "behavioral_mind_environment_manifest.json"
    base_manifest = read_json(base_manifest_path)
    if base_manifest.get("status") != BASE_V8_STATUS:
        raise EmpiricalEnvironmentError("base V8 environment status is not valid")
    if base_manifest.get("target_outcomes_present") is not False:
        raise EmpiricalEnvironmentError("target outcomes present in base environment")
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
        raise EmpiricalEnvironmentError("V9 overlay must not overwrite V8")
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(v8_root, output_root)
    snapshot_id = str(base_manifest.get("base_named_environment_manifest_sha256") or sha256_file(base_manifest_path))
    audits: list[dict[str, Any]] = []
    batch_index: dict[tuple[str, str], dict[str, Any]] = {}
    voter_files = sorted((output_root / "voter_batches").rglob("*.json"))
    if not voter_files:
        raise EmpiricalEnvironmentError("V8 environment contains no voter batches")
    for path in voter_files:
        batch = read_json(path)
        household = batch.get("household_context") if isinstance(batch.get("household_context"), Mapping) else {}
        ecological = batch.get("territory_context") if isinstance(batch.get("territory_context"), Mapping) else {}
        rows = []
        for voter in _voters(batch):
            visible, audit = empiricalize_behavioral_voter(
                voter,
                dimension_registry=dimension_registry,
                source_registry=source_registry,
                prior_pack=prior_pack,
                snapshot_id=snapshot_id,
                snapshot_date=snapshot_date,
                replicate_id=replicate_id,
                household=household,
                ecological_context=ecological,
            )
            rows.append(visible)
            full_mind = audit.get("full_empirical_mind")
            if not isinstance(full_mind, Mapping):
                raise EmpiricalEnvironmentError("full empirical mind missing from audit")
            gate = audit_empirical_mind(
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
                    "territory_id": batch.get("territory_id") or batch.get("anonymous_territory_id"),
                    "batch_id": batch.get("batch_id"),
                    "weighted_archetype_id": visible.get("weighted_archetype_id") or visible.get("archetype_id"),
                    "mind_audit": audit,
                    "gate_report": gate,
                }
            )
        _set_voters(batch, rows)
        batch["schema_version"] = "ATLAS_NAMED_2026_VOTER_BATCH_EMPIRICAL_MIND_V9"
        batch["empirical_moroccan_mind_present"] = True
        batch["population_priors_are_individual_facts"] = False
        write_json(path, batch)
        key = (
            str(batch.get("territory_id") or batch.get("anonymous_territory_id") or ""),
            str(batch.get("batch_id") or ""),
        )
        batch_index[key] = batch
    packet_root = output_root / "packets"
    if packet_root.is_dir():
        for path in sorted(packet_root.rglob("*.json")):
            packet = read_json(path)
            key = (
                str(packet.get("territory_id") or packet.get("anonymous_territory_id") or ""),
                str(packet.get("batch_id") or ""),
            )
            if key in batch_index:
                packet["voter_batch"] = copy.deepcopy(batch_index[key])
                packet["schema_version"] = "ATLAS_NAMED_2026_PACKET_EMPIRICAL_MIND_V9"
                packet["empirical_moroccan_mind_present"] = True
                write_json(path, packet)
    prompt_path = output_root / "as2_full_environment_prompt_v2.md"
    if prompt_addendum_text:
        original_prompt = prompt_path.read_text(encoding="utf-8")
        marker = "# Empirical Moroccan Mind V9 addendum"
        if marker not in original_prompt:
            prompt_path.write_text(
                original_prompt.rstrip() + "\n\n" + prompt_addendum_text.strip() + "\n",
                encoding="utf-8",
            )
    calibrated = bool(prior_pack and prior_pack.get("status") == CALIBRATED_STATUS)
    status = EMPIRICAL_ENV_STATUS_CALIBRATED if calibrated else EMPIRICAL_ENV_STATUS_OBSERVED
    unknown_total = sum(
        int(record["mind_audit"]["epistemic_counts"].get("UNKNOWN", 0))
        for record in audits
    )
    dimension_total = sum(int(record["mind_audit"]["dimensions"]) for record in audits)
    audit_index = {
        "schema_version": "AGENT_SOCIETY_EMPIRICAL_MIND_AUDIT_INDEX_V1",
        "voters": audits,
        "audit_index_sha256": sha256_json(audits),
    }
    write_json(output_root / "empirical_mind_audit_index.json", audit_index)
    manifest = {
        "schema_version": EMPIRICAL_ENV_SCHEMA,
        "status": status,
        "base_v8_manifest_sha256": sha256_file(base_manifest_path),
        "target_outcomes_present": False,
        "snapshot_date": snapshot_date,
        "replicate_id": replicate_id,
        "empirical_moroccan_mind_present": True,
        "calibrated_prior_pack_present": calibrated,
        "population_prior_relabelled_as_individual_fact": False,
        "raw_microdata_embedded": False,
        "dimension_registry_sha256": sha256_json(dimension_registry),
        "source_registry_sha256": sha256_json(source_registry),
        "prior_pack_sha256": sha256_json(prior_pack) if prior_pack else None,
        "voter_rows": len(audits),
        "mean_unknown_dimension_share": round(unknown_total / max(1, dimension_total), 6),
        "startup_work_item_cap": 1,
        "scale_allowed": False,
        "scale_blockers": [
            "EM3 calibrated Moroccan prior pack",
            "EM4 marginal/subgroup/correlation validation",
            "EM6-EM8 paired behavioral and POV tests",
            "historical out-of-sample validation before lambda may differ from zero",
        ],
        "prompt_addendum_present": bool(prompt_addendum_text),
        "prompt_sha256": sha256_file(output_root / "as2_full_environment_prompt_v2.md"),
        "audit_index_sha256": sha256_file(output_root / "empirical_mind_audit_index.json"),
    }
    write_json(output_root / "empirical_mind_environment_manifest.json", manifest)
    return manifest

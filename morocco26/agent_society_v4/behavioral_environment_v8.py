from __future__ import annotations

"""Versioned Behavioral Mind V8 overlay for an existing named 2026 environment."""

import copy
import hashlib
import json
import os
import pathlib
import shutil
import tempfile
import zipfile
from typing import Any, Mapping

from .behavioral_mind_v8 import behavioralize_voter, sha256_json

BEHAVIORAL_ENV_SCHEMA = "ATLAS_NAMED_2026_BEHAVIORAL_ENVIRONMENT_V8"
BEHAVIORAL_ENV_STATUS = "PASS_BEHAVIORAL_MIND_V8_ENVIRONMENT_READY"
BASE_ENV_STATUS = "PASS_REALISTIC_2026_NAMED_ENVIRONMENT_READY"


class BehavioralEnvironmentError(ValueError):
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
        raise BehavioralEnvironmentError(f"cannot read JSON {path}: {exc}") from exc


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def _safe_extract(bundle: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
    if bundle.is_dir():
        return locate_base_root(bundle)
    if not bundle.is_file() or bundle.suffix.lower() != ".zip":
        raise BehavioralEnvironmentError("input environment must be a directory or ZIP")
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            member = pathlib.PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts:
                raise BehavioralEnvironmentError(f"unsafe ZIP member: {info.filename}")
        archive.extractall(target)
    return locate_base_root(target)


def locate_base_root(root: pathlib.Path) -> pathlib.Path:
    root = root.expanduser().resolve()
    if (root / "named_2026_environment_manifest.json").is_file():
        return root
    hits = sorted(root.rglob("named_2026_environment_manifest.json"), key=lambda p: len(p.parts))
    if len(hits) != 1:
        raise BehavioralEnvironmentError(f"expected exactly one named environment manifest; found {len(hits)}")
    return hits[0].parent


def _voters(batch: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in ("voter_archetypes", "archetypes", "voters"):
        if isinstance(batch.get(key), list):
            return [dict(row) for row in batch[key]]
    raise BehavioralEnvironmentError("voter batch has no voter array")


def _set_voters(batch: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    for key in ("voter_archetypes", "archetypes", "voters"):
        if isinstance(batch.get(key), list):
            batch[key] = rows; return
    raise BehavioralEnvironmentError("cannot replace voter rows")


def build_behavioral_environment(base_root: pathlib.Path, output_root: pathlib.Path, *, prompt_text: str, output_schema: Mapping[str, Any]) -> dict[str, Any]:
    base_root = locate_base_root(base_root)
    output_root = output_root.expanduser().resolve()
    base_manifest_path = base_root / "named_2026_environment_manifest.json"
    base_manifest = read_json(base_manifest_path)
    checks = {
        "base_status": base_manifest.get("status") == BASE_ENV_STATUS,
        "outcomes_absent": base_manifest.get("target_outcomes_present") is False,
        "candidate_fabrication_absent": base_manifest.get("candidate_fabrication_used") is False,
        "information_diets_present": base_manifest.get("per_voter_information_diets_present") is True,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise BehavioralEnvironmentError(f"base named environment failed gates: {failed}")
    if output_root == base_root:
        raise BehavioralEnvironmentError("behavioral overlay must not overwrite base environment")
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(base_root, output_root)

    snapshot_id = str(base_manifest.get("source_input_sha256") or "") or sha256_file(base_manifest_path)
    audit_records, batch_index = [], {}
    voter_files = sorted((output_root / "voter_batches").rglob("*.json"))
    if not voter_files:
        raise BehavioralEnvironmentError("base environment contains no voter batch files")
    for path in voter_files:
        batch = read_json(path)
        parties = [str(x) for x in batch.get("available_party_ids") or []]
        if len(parties) < 2:
            raise BehavioralEnvironmentError(f"voter batch lacks ballot parties: {path}")
        rows = []
        for voter in _voters(batch):
            visible, audit = behavioralize_voter(voter, snapshot_id=snapshot_id, party_ids=parties)
            rows.append(visible)
            audit_records.append({"territory_id": batch.get("anonymous_territory_id") or batch.get("territory_id"), "batch_id": batch.get("batch_id"), **audit})
        _set_voters(batch, rows)
        batch.update({"schema_version": "ATLAS_NAMED_2026_VOTER_BATCH_BEHAVIORAL_V8", "behavioral_mind_present": True, "research_ontology_removed_from_voter_voice": True})
        write_json(path, batch)
        batch_index[(str(batch.get("anonymous_territory_id") or batch.get("territory_id")), str(batch.get("batch_id")))] = batch

    packet_root = output_root / "packets"
    if packet_root.is_dir():
        for path in sorted(packet_root.rglob("*.json")):
            packet = read_json(path)
            key = (str(packet.get("anonymous_territory_id")), str(packet.get("batch_id")))
            if key in batch_index:
                packet["voter_batch"] = copy.deepcopy(batch_index[key])
                packet["schema_version"] = "ATLAS_NAMED_2026_PACKET_BEHAVIORAL_V8"
                packet["behavioral_mind_present"] = True
                write_json(path, packet)

    context_root = output_root / "contexts"
    if context_root.is_dir():
        for path in sorted(context_root.rglob("*.json")):
            context = read_json(path)
            context["schema_version"] = "ATLAS_NAMED_2026_CONTEXT_BEHAVIORAL_V8"
            context["instruction"] = (
                "Incarne chaque votant depuis son voter_mind_state et son electoral_world_as_seen. "
                "Le monde d'un autre votant est inaccessible. N'invente aucun lien personnel, réputation, "
                "clientélisme, recommandation ou fait politique absent."
            )
            context["behavioral_mind_present"] = True
            write_json(path, context)

    prompt_path = output_root / "as2_full_environment_prompt_v2.md"
    prompt_path.write_text(prompt_text.rstrip() + "\n", encoding="utf-8")
    schema_path = output_root / "as2_full_environment_output_schema_v2.json"
    write_json(schema_path, dict(output_schema))
    work_manifest = read_json(output_root / "work_manifest.json")
    work_items = work_manifest.get("work_items") if isinstance(work_manifest, Mapping) else None
    if not isinstance(work_items, list) or not work_items:
        raise BehavioralEnvironmentError("behavioral environment has no work items")

    rows_across_work_items = 0
    for item in work_items:
        key = (str(item.get("anonymous_territory_id") or item.get("territory_id") or ""), str(item.get("batch_id") or ""))
        if key not in batch_index:
            raise BehavioralEnvironmentError(f"work item references unknown voter batch: {key}")
        rows_across_work_items += len(_voters(batch_index[key]))

    model_hash_index = {f"{r.get('territory_id')}|{r.get('batch_id')}|{r.get('weighted_archetype_id')}": r["model_visible_voter_sha256"] for r in audit_records}
    mind_hash_index = {f"{r.get('territory_id')}|{r.get('batch_id')}|{r.get('weighted_archetype_id')}": r["mind"]["mind_state_sha256"] for r in audit_records}
    unknown_total = sum(int(r["mind"]["unknown_anchor_count"]) for r in audit_records)
    audit_index = {
        "schema_version": "AGENT_SOCIETY_BEHAVIORAL_MIND_AUDIT_INDEX_V1",
        "model_visible_voter_hash_index_sha256": sha256_json(model_hash_index),
        "mind_state_hash_index_sha256": sha256_json(mind_hash_index),
        "voters": audit_records,
    }
    write_json(output_root / "behavioral_mind_audit_index.json", audit_index)
    manifest = {
        "schema_version": BEHAVIORAL_ENV_SCHEMA, "status": BEHAVIORAL_ENV_STATUS,
        "base_named_environment_manifest_sha256": sha256_file(base_manifest_path),
        "base_named_environment_status": base_manifest.get("status"), "base_regime": base_manifest.get("regime"),
        "main_commit_sha": base_manifest.get("main_commit_sha"), "target_outcomes_present": False,
        "candidate_fabrication_used": False, "current_vintage_unknowns_allowed": True,
        "behavioral_mind_present": True, "subjective_world_present": True,
        "analyst_factor_taxonomy_required_from_voter": False, "free_first_person_pov_required": True,
        "local_candidate_evidence_forbidden_on_regional_by_default": True,
        "technical_information_diet_removed_from_model_view": True,
        "work_items": len(work_items), "voter_rows_per_condition_or_unique_batches": len(audit_records),
        "rows_across_work_items": rows_across_work_items,
        "mean_unknown_mind_anchors_per_voter": round(unknown_total / max(1, len(audit_records)), 6),
        "prompt_sha256": sha256_file(prompt_path), "output_schema_sha256": sha256_file(schema_path),
        "audit_index_sha256": sha256_file(output_root / "behavioral_mind_audit_index.json"),
        "startup_work_item_cap": 1, "scale_allowed": False,
        "scale_blocker": "Run one 32-voter behavioral pilot and pass BR0/BR1/BR6/BR8; BR2-BR5/BR7 paired tests remain required before broad scale.",
    }
    write_json(output_root / "behavioral_mind_environment_manifest.json", manifest)
    return manifest


def validate_behavioral_environment(root: pathlib.Path) -> dict[str, Any]:
    root = locate_base_root(root)
    path = root / "behavioral_mind_environment_manifest.json"
    if not path.is_file():
        raise BehavioralEnvironmentError("behavioral mind manifest missing")
    manifest = read_json(path)
    checks = {
        "status": manifest.get("status") == BEHAVIORAL_ENV_STATUS,
        "outcomes": manifest.get("target_outcomes_present") is False,
        "mind": manifest.get("behavioral_mind_present") is True,
        "subjective_world": manifest.get("subjective_world_present") is True,
        "analyst_taxonomy": manifest.get("analyst_factor_taxonomy_required_from_voter") is False,
        "pov": manifest.get("free_first_person_pov_required") is True,
        "cap": int(manifest.get("startup_work_item_cap") or 0) == 1,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise BehavioralEnvironmentError(f"behavioral manifest failed: {failed}")
    prompt, schema = root / "as2_full_environment_prompt_v2.md", root / "as2_full_environment_output_schema_v2.json"
    if sha256_file(prompt) != manifest.get("prompt_sha256") or sha256_file(schema) != manifest.get("output_schema_sha256"):
        raise BehavioralEnvironmentError("behavioral prompt/schema hash mismatch")
    text = prompt.read_text(encoding="utf-8").lower()
    forbidden = ("factor_importance", "cited_factors", "policy_program_fit", "local_candidate_context")
    leaked = [token for token in forbidden if token in text]
    if leaked:
        raise BehavioralEnvironmentError(f"research ontology leaked into voter prompt: {leaked}")
    return dict(manifest)

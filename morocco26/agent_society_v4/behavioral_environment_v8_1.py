from __future__ import annotations

"""Behavioral Mind V8.1 overlay - certificate-driven, no fabricated ballot.

Additive to `behavioral_environment_v8`, which is left untouched. The V8.1
builder refuses to emit a ballot the data layers cannot support: if the P3
data-layer certificate reports REGIONAL_BALLOT as anything other than REAL or
PARTIAL_REAL, the environment is LOCAL-only and says so in its manifest, its
prompt and its output schema.
"""

import copy
import pathlib
import shutil
from typing import Any, Mapping

from .behavioral_environment_v8 import (
    BASE_ENV_STATUS,
    BehavioralEnvironmentError,
    _set_voters,
    _voters,
    locate_base_root,
    read_json,
    sha256_file,
    write_json,
)
from .behavioral_mind_v8_1 import behavioralize_voter_strict, sha256_json
from .p3_data_layers_v1 import USABLE_LAYER_STATES

BEHAVIORAL_ENV_V8_1_SCHEMA = "ATLAS_NAMED_2026_BEHAVIORAL_ENVIRONMENT_V8_1"
BEHAVIORAL_ENV_V8_1_STATUS = "PASS_BEHAVIORAL_MIND_V8_1_ENVIRONMENT_READY"


class BehavioralEnvironmentV81Error(BehavioralEnvironmentError):
    pass


def _regional_allowed(certificate: Mapping[str, Any] | None) -> bool:
    if certificate is None:
        return False
    return str((certificate.get("layer_states") or {}).get("REGIONAL_BALLOT")) in USABLE_LAYER_STATES


def build_behavioral_environment_v8_1(
    base_root: pathlib.Path,
    output_root: pathlib.Path,
    *,
    prompt_text: str,
    output_schema: Mapping[str, Any],
    certificate: Mapping[str, Any],
) -> dict[str, Any]:
    base_root = locate_base_root(base_root)
    output_root = pathlib.Path(output_root).expanduser().resolve()
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
        raise BehavioralEnvironmentV81Error(f"base named environment failed gates: {failed}")
    if str(certificate.get("schema_version") or "") != "ATLAS_P3_DATA_LAYER_CERTIFICATE_V1":
        raise BehavioralEnvironmentV81Error("V8.1 requires a P3 data-layer certificate")
    if str(certificate.get("status") or "").startswith("BLOCKED"):
        raise BehavioralEnvironmentV81Error(
            f"data-layer certificate is blocking: {certificate.get('blocking_findings')}"
        )
    if output_root == base_root:
        raise BehavioralEnvironmentV81Error("behavioral overlay must not overwrite base environment")
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(base_root, output_root)

    regional_allowed = _regional_allowed(certificate)
    ballots = ["LOCAL"] + (["REGIONAL"] if regional_allowed else [])
    snapshot_id = str(base_manifest.get("source_input_sha256") or "") or sha256_file(base_manifest_path)

    audit_records: list[dict[str, Any]] = []
    batch_index: dict[tuple[str, str], dict[str, Any]] = {}
    voter_files = sorted((output_root / "voter_batches").rglob("*.json"))
    if not voter_files:
        raise BehavioralEnvironmentV81Error("base environment contains no voter batch files")
    for path in voter_files:
        batch = read_json(path)
        parties = [str(item) for item in batch.get("available_party_ids") or []]
        if len(parties) < 2:
            raise BehavioralEnvironmentV81Error(f"voter batch lacks ballot parties: {path}")
        rows = []
        for voter in _voters(batch):
            visible, audit = behavioralize_voter_strict(
                voter, snapshot_id=snapshot_id, party_ids=parties, certificate=certificate
            )
            rows.append(visible)
            audit_records.append(
                {
                    "territory_id": batch.get("anonymous_territory_id") or batch.get("territory_id"),
                    "batch_id": batch.get("batch_id"),
                    **audit,
                }
            )
        _set_voters(batch, rows)
        batch.update(
            {
                "schema_version": "ATLAS_NAMED_2026_VOTER_BATCH_BEHAVIORAL_V8_1",
                "behavioral_mind_present": True,
                "research_ontology_removed_from_voter_voice": True,
                "ballots_simulated": list(ballots),
                "regional_surface_status": "EXPLICIT_REGION_SPECIFIC_SURFACE" if regional_allowed else "MISSING",
            }
        )
        write_json(path, batch)
        batch_index[
            (str(batch.get("anonymous_territory_id") or batch.get("territory_id")), str(batch.get("batch_id")))
        ] = batch

    packet_root = output_root / "packets"
    if packet_root.is_dir():
        for path in sorted(packet_root.rglob("*.json")):
            packet = read_json(path)
            key = (str(packet.get("anonymous_territory_id")), str(packet.get("batch_id")))
            if key in batch_index:
                packet["voter_batch"] = copy.deepcopy(batch_index[key])
                packet["schema_version"] = "ATLAS_NAMED_2026_PACKET_BEHAVIORAL_V8_1"
                packet["behavioral_mind_present"] = True
                packet["ballots_simulated"] = list(ballots)
                write_json(path, packet)

    context_root = output_root / "contexts"
    if context_root.is_dir():
        for path in sorted(context_root.rglob("*.json")):
            context = read_json(path)
            context["schema_version"] = "ATLAS_NAMED_2026_CONTEXT_BEHAVIORAL_V8_1"
            context["instruction"] = (
                "Incarne chaque votant depuis son voter_mind_state et son electoral_world_as_seen. "
                "Le monde d'un autre votant est inaccessible. N'invente aucun lien personnel, "
                "reputation, clientelisme, recommandation ou fait politique absent."
            )
            context["behavioral_mind_present"] = True
            context["ballots_simulated"] = list(ballots)
            context["regional_surface_status"] = (
                "EXPLICIT_REGION_SPECIFIC_SURFACE" if regional_allowed else "MISSING"
            )
            write_json(path, context)

    prompt_path = output_root / "as2_full_environment_prompt_v2.md"
    prompt_path.write_text(prompt_text.rstrip() + "\n", encoding="utf-8")
    schema_path = output_root / "as2_full_environment_output_schema_v2.json"
    write_json(schema_path, dict(output_schema))
    certificate_path = output_root / "p3_data_layer_certificate.json"
    write_json(certificate_path, dict(certificate))

    work_manifest = read_json(output_root / "work_manifest.json")
    work_items = work_manifest.get("work_items") if isinstance(work_manifest, Mapping) else None
    if not isinstance(work_items, list) or not work_items:
        raise BehavioralEnvironmentV81Error("behavioral environment has no work items")
    rows_across_work_items = 0
    for item in work_items:
        key = (
            str(item.get("anonymous_territory_id") or item.get("territory_id") or ""),
            str(item.get("batch_id") or ""),
        )
        if key not in batch_index:
            raise BehavioralEnvironmentV81Error(f"work item references unknown voter batch: {key}")
        rows_across_work_items += len(_voters(batch_index[key]))

    fallback_used = sum(1 for record in audit_records if record["world"]["regional_fallback_used"])
    if fallback_used:
        raise BehavioralEnvironmentV81Error("V8.1 must never use a regional fallback")
    model_hash_index = {
        f"{r.get('territory_id')}|{r.get('batch_id')}|{r.get('weighted_archetype_id')}": r[
            "model_visible_voter_sha256"
        ]
        for r in audit_records
    }
    audit_index = {
        "schema_version": "AGENT_SOCIETY_BEHAVIORAL_MIND_V8_1_AUDIT_INDEX_V1",
        "model_visible_voter_hash_index_sha256": sha256_json(model_hash_index),
        "voters": audit_records,
    }
    write_json(output_root / "behavioral_mind_audit_index.json", audit_index)

    unknown_total = sum(int(r["mind"]["unknown_anchor_count"]) for r in audit_records)
    programme_cards = sum(int(r["world"]["local_cards_with_programme_content"]) for r in audit_records)
    manifest = {
        "schema_version": BEHAVIORAL_ENV_V8_1_SCHEMA,
        "status": BEHAVIORAL_ENV_V8_1_STATUS,
        "base_named_environment_manifest_sha256": sha256_file(base_manifest_path),
        "base_named_environment_status": base_manifest.get("status"),
        "base_regime": base_manifest.get("regime"),
        "main_commit_sha": base_manifest.get("main_commit_sha"),
        "target_outcomes_present": False,
        "candidate_fabrication_used": False,
        "current_vintage_unknowns_allowed": True,
        "behavioral_mind_present": True,
        "subjective_world_present": True,
        "analyst_factor_taxonomy_required_from_voter": False,
        "free_first_person_pov_required": True,
        "local_candidate_evidence_forbidden_on_regional_by_default": True,
        "technical_information_diet_removed_from_model_view": True,
        "ballots_simulated": list(ballots),
        "regional_surface_status": "EXPLICIT_REGION_SPECIFIC_SURFACE" if regional_allowed else "MISSING",
        "regional_simulation_allowed": regional_allowed,
        "regional_fallback_allowed": False,
        "regional_fallback_used": False,
        "programme_layer_state": (certificate.get("layer_states") or {}).get("PARTY_PROGRAMMES"),
        "local_cards_with_programme_content": programme_cards,
        "data_layer_certificate_sha256": certificate.get("certificate_sha256"),
        "data_layer_states": certificate.get("layer_states"),
        "gate_testability": certificate.get("gate_testability"),
        "work_items": len(work_items),
        "voter_rows_per_condition_or_unique_batches": len(audit_records),
        "rows_across_work_items": rows_across_work_items,
        "mean_unknown_mind_anchors_per_voter": round(unknown_total / max(1, len(audit_records)), 6),
        "prompt_sha256": sha256_file(prompt_path),
        "output_schema_sha256": sha256_file(schema_path),
        "data_layer_certificate_file_sha256": sha256_file(certificate_path),
        "audit_index_sha256": sha256_file(output_root / "behavioral_mind_audit_index.json"),
        "startup_work_item_cap": 1,
        "scale_allowed": False,
        "scale_blocker": (
            "R3 LOCAL-only pilot must pass BR0/BR1-LOCAL/BR6/BR8 before anything else; "
            "BR1-REGIONAL and BR4 stay NOT_TESTABLE until R4/R5 collect the missing layers."
        ),
    }
    write_json(output_root / "behavioral_mind_environment_manifest.json", manifest)
    write_json(output_root / "behavioral_mind_v8_1_manifest.json", manifest)
    return manifest


def validate_behavioral_environment_v8_1(root: pathlib.Path) -> dict[str, Any]:
    root = locate_base_root(root)
    path = root / "behavioral_mind_v8_1_manifest.json"
    if not path.is_file():
        raise BehavioralEnvironmentV81Error("behavioral mind V8.1 manifest missing")
    manifest = read_json(path)
    checks = {
        "status": manifest.get("status") == BEHAVIORAL_ENV_V8_1_STATUS,
        "outcomes": manifest.get("target_outcomes_present") is False,
        "mind": manifest.get("behavioral_mind_present") is True,
        "fallback": manifest.get("regional_fallback_used") is False,
        "fallback_policy": manifest.get("regional_fallback_allowed") is False,
        "cap": int(manifest.get("startup_work_item_cap") or 0) == 1,
        "certificate": bool(manifest.get("data_layer_certificate_sha256")),
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise BehavioralEnvironmentV81Error(f"V8.1 manifest failed: {failed}")
    prompt = root / "as2_full_environment_prompt_v2.md"
    schema = root / "as2_full_environment_output_schema_v2.json"
    if sha256_file(prompt) != manifest.get("prompt_sha256") or sha256_file(schema) != manifest.get(
        "output_schema_sha256"
    ):
        raise BehavioralEnvironmentV81Error("V8.1 prompt/schema hash mismatch")
    text = prompt.read_text(encoding="utf-8").lower()
    leaked = [
        token
        for token in ("factor_importance", "cited_factors", "policy_program_fit", "local_candidate_context")
        if token in text
    ]
    if leaked:
        raise BehavioralEnvironmentV81Error(f"research ontology leaked into voter prompt: {leaked}")
    if "REGIONAL" not in (manifest.get("ballots_simulated") or []):
        schema_value = read_json(schema)
        required = schema_value.get("required") or []
        if "regional_party_probabilities" in required:
            raise BehavioralEnvironmentV81Error(
                "LOCAL-only environment must not require a regional simplex"
            )
    return dict(manifest)

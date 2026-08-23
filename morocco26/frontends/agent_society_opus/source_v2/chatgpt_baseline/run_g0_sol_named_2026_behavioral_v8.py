#!/usr/bin/env python3
from __future__ import annotations

"""Canonical GPT-5.6 Sol launcher for the Behavioral Mind V8 current-vintage pilot.

The runner delegates transport/model isolation to run_chatgpt_baseline.py but
uses a behavioral row validator that does not force factor_importance,
reason_codes, or analyst rationales into the voter's response.
"""

import json
import pathlib
import sys
from typing import Any, Mapping, Sequence

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
PKG_ROOT = REPO_ROOT
for path in (HERE, SCRIPTS, PKG_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_chatgpt_baseline as runner  # noqa: E402
from morocco26.agent_society_v4.behavioral_environment_v8 import (  # noqa: E402
    BEHAVIORAL_ENV_STATUS,
    read_json,
    sha256_file,
)
from morocco26.agent_society_v4.behavioral_mind_v8 import (  # noqa: E402
    assert_no_analyst_ontology_in_pov,
)

FROZEN_MODEL = "gpt-5.6-sol"
FROZEN_REASONING = "medium"
PROTOCOL_ID = "ATLAS_CHATGPT_ACCOUNT_BEHAVIORAL_MIND_V8"


def option(args: list[str], name: str) -> str | None:
    for index, value in enumerate(args):
        if value == name:
            if index + 1 >= len(args):
                raise runner.RunnerError(f"{name} requires a value")
            return args[index + 1]
        if value.startswith(name + "="):
            return value.split("=", 1)[1]
    return None


def locate_behavioral_manifest(bundle: pathlib.Path) -> pathlib.Path:
    bundle = bundle.expanduser().resolve()
    cache = bundle.parent / (bundle.name + ".behavioral_v8_manifest_cache")
    extracted, _ = runner.extract_bundle(bundle, cache)
    hits = sorted(extracted.rglob("behavioral_mind_environment_manifest.json"))
    if len(hits) != 1:
        raise runner.RunnerError(
            f"behavioral bundle must contain exactly one behavioral_mind_environment_manifest.json; found {len(hits)}"
        )
    return hits[0]


def validate_manifest(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    value = read_json(path)
    checks = {
        "status": value.get("status") == BEHAVIORAL_ENV_STATUS,
        "outcomes": value.get("target_outcomes_present") is False,
        "candidate_fabrication": value.get("candidate_fabrication_used") is False,
        "mind": value.get("behavioral_mind_present") is True,
        "subjective_world": value.get("subjective_world_present") is True,
        "analyst_taxonomy": value.get("analyst_factor_taxonomy_required_from_voter") is False,
        "free_pov": value.get("free_first_person_pov_required") is True,
        "cap": int(value.get("startup_work_item_cap") or 0) >= 1,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise runner.RunnerError(f"behavioral V8 environment gate failed: {failed}")
    return dict(value), sha256_file(path)


def _simplex(value: Any, label: str, expected_parties: set[str]) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(map(str, value)) != expected_parties:
        raise runner.ValidationError(f"{label}: party universe mismatch")
    parsed: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise runner.ValidationError(f"{label}.{key}: not numeric")
        number = float(raw)
        if not 0.0 <= number <= 1.0:
            raise runner.ValidationError(f"{label}.{key}: outside [0,1]")
        parsed[str(key)] = number
    if abs(sum(parsed.values()) - 1.0) > 1e-9:
        raise runner.ValidationError(f"{label}: does not sum to one")
    return parsed


def validate_behavioral_rows(value: Any, task, row_schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {"rows"}:
        raise runner.ValidationError('final output must be exactly {"rows":[...]}')
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) != len(task.expected_rows):
        raise runner.ValidationError("behavioral V8 row count mismatch")
    properties = set((row_schema.get("properties") or {}).keys())
    required = set(row_schema.get("required") or ())
    expected_archetypes = [
        str(row.get("weighted_archetype_id") or row.get("archetype_id") or "")
        for row in task.expected_rows
    ]
    expected_parties = set(task.available_party_ids)
    identities = {
        "anonymous_election_id": task.election_id,
        "anonymous_territory_id": task.territory_id,
        "condition_id": task.condition_id,
        "batch_id": task.batch_id,
    }
    validated = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            raise runner.ValidationError(f"row {index}: not an object")
        row = dict(raw)
        missing = required - set(row)
        if missing:
            raise runner.ValidationError(f"row {index}: missing {sorted(missing)}")
        if row_schema.get("additionalProperties") is False:
            extras = set(row) - properties
            if extras:
                raise runner.ValidationError(f"row {index}: extra keys {sorted(extras)}")
        for key, expected in identities.items():
            if str(row.get(key)) != expected:
                raise runner.ValidationError(f"row {index}: {key} mismatch")
        if str(row.get("weighted_archetype_id") or "") != expected_archetypes[index]:
            raise runner.ValidationError(f"row {index}: archetype order mismatch")
        turnout = row.get("turnout_probability")
        if isinstance(turnout, bool) or not isinstance(turnout, (int, float)) or not 0.0 <= float(turnout) <= 1.0:
            raise runner.ValidationError(f"row {index}: invalid turnout_probability")
        row["local_party_probabilities"] = _simplex(
            row.get("local_party_probabilities"), f"row {index}.LOCAL", expected_parties
        )
        row["regional_party_probabilities"] = _simplex(
            row.get("regional_party_probabilities"), f"row {index}.REGIONAL", expected_parties
        )
        pov = row.get("pov_fr")
        if not isinstance(pov, str) or not pov.strip():
            raise runner.ValidationError(f"row {index}: pov_fr missing")
        try:
            assert_no_analyst_ontology_in_pov(pov)
        except ValueError as exc:
            raise runner.ValidationError(f"row {index}: {exc}") from exc
        validated.append(row)
    return validated


def patch_state(manifest: Mapping[str, Any], digest: str, manifest_path: pathlib.Path) -> None:
    original = runner.write_run_state

    def write_state(**kwargs):
        original(**kwargs)
        output_root = pathlib.Path(kwargs["output_root"])
        metadata = {
            "protocol_id": PROTOCOL_ID,
            "behavioral_mind_schema": manifest.get("schema_version"),
            "behavioral_environment_manifest": str(manifest_path),
            "behavioral_environment_manifest_sha256": digest,
            "raw_output_is_forecast": False,
            "pre_validation_agentic_lambda": 0.0,
            "factor_importance_requested": False,
            "reason_codes_requested": False,
            "observable_rationale_requested": False,
            "free_first_person_pov_requested": True,
            "startup_work_item_cap": int(manifest["startup_work_item_cap"]),
            "scale_allowed": bool(manifest.get("scale_allowed")),
            "target_outcomes_present": False,
        }
        for name in ("run_state.json", "output_manifest.json", "preflight.json"):
            target = output_root / name
            if not target.is_file():
                continue
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["behavioral_mind_v8"] = metadata
            runner.atomic_write_json(target, payload)

    runner.write_run_state = write_state
    runner.validate_rows = validate_behavioral_rows
    runner.PROTOCOL_ID = PROTOCOL_ID


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    for forbidden in ("--model", "--reasoning", "--allow-noncanonical-counts"):
        if forbidden in args or any(value.startswith(forbidden + "=") for value in args):
            raise runner.RunnerError(f"{forbidden} is forbidden by Behavioral Mind V8 freeze")
    bundle_raw = option(args, "--bundle")
    if not bundle_raw:
        raise runner.RunnerError("--bundle is mandatory")
    manifest_path = locate_behavioral_manifest(pathlib.Path(bundle_raw))
    manifest, digest = validate_manifest(manifest_path)

    cap = int(manifest["startup_work_item_cap"])
    scale_allowed = bool(manifest.get("scale_allowed"))
    limit_raw = option(args, "--limit")
    if limit_raw is None:
        args += ["--limit", str(cap)]
    else:
        try:
            limit = int(limit_raw)
        except ValueError as exc:
            raise runner.RunnerError("--limit must be an integer") from exc
        if limit < 1:
            raise runner.RunnerError("--limit must be >= 1")
        if not scale_allowed and limit > cap:
            raise runner.RunnerError(
                f"behavioral V8 is pilot-only: --limit {limit} exceeds startup cap {cap}; no override is permitted"
            )

    patch_state(manifest, digest, manifest_path)
    runner.CANONICAL_WORK_ITEMS = int(manifest["work_items"])
    runner.CANONICAL_ROWS = int(manifest["rows_across_work_items"])
    return runner.main(args + ["--model", FROZEN_MODEL, "--reasoning", FROZEN_REASONING])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (runner.RunnerError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

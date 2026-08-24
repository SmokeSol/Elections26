#!/usr/bin/env python3
from __future__ import annotations

"""Canonical GPT-5.6 Sol launcher for a calibrated Empirical Mind V9 pilot.

Observed-only V9 environments are intentionally non-runnable. A model call is
allowed only after a calibrated Moroccan prior pack is present and the pilot
remains capped at one work item.
"""

import json
import pathlib
import sys
from typing import Any, Mapping, Sequence

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[4]
for path in (HERE, REPO_ROOT, REPO_ROOT / "morocco26" / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_g0_sol_named_2026_behavioral_v8 as v8  # noqa: E402
import run_chatgpt_baseline as runner  # noqa: E402
from morocco26.agent_society_v4.empirical_environment_v9 import (  # noqa: E402
    EMPIRICAL_ENV_STATUS_CALIBRATED,
    read_json,
    sha256_file,
)

PROTOCOL_ID = "ATLAS_CHATGPT_ACCOUNT_EMPIRICAL_MOROCCAN_MIND_V9"


def locate_empirical_manifest(bundle: pathlib.Path) -> pathlib.Path:
    bundle = bundle.expanduser().resolve()
    cache = bundle.parent / (bundle.name + ".empirical_v9_manifest_cache")
    extracted, _ = runner.extract_bundle(bundle, cache)
    hits = sorted(extracted.rglob("empirical_mind_environment_manifest.json"))
    if len(hits) != 1:
        raise runner.RunnerError(
            "empirical V9 bundle must contain exactly one empirical_mind_environment_manifest.json; "
            f"found {len(hits)}"
        )
    return hits[0]


def validate_empirical_manifest(path: pathlib.Path) -> tuple[dict[str, Any], str]:
    value = read_json(path)
    checks = {
        "status": value.get("status") == EMPIRICAL_ENV_STATUS_CALIBRATED,
        "outcomes": value.get("target_outcomes_present") is False,
        "mind": value.get("empirical_moroccan_mind_present") is True,
        "prior_pack": value.get("calibrated_prior_pack_present") is True,
        "no_individual_overclaim": value.get("population_prior_relabelled_as_individual_fact") is False,
        "raw_microdata": value.get("raw_microdata_embedded") is False,
        "cap": int(value.get("startup_work_item_cap") or 0) == 1,
        "scale": value.get("scale_allowed") is False,
        "prompt_addendum": value.get("prompt_addendum_present") is True,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise runner.RunnerError(f"empirical V9 environment gate failed: {failed}")
    return dict(value), sha256_file(path)


def patch_v8_state(empirical: Mapping[str, Any], digest: str, path: pathlib.Path) -> None:
    original_patch = v8.patch_state

    def patched(manifest, v8_digest, v8_path):
        original_patch(manifest, v8_digest, v8_path)
        previous_write = runner.write_run_state

        def write_state(**kwargs):
            previous_write(**kwargs)
            output_root = pathlib.Path(kwargs["output_root"])
            metadata = {
                "protocol_id": PROTOCOL_ID,
                "empirical_environment_manifest": str(path),
                "empirical_environment_manifest_sha256": digest,
                "calibrated_prior_pack_present": True,
                "population_prior_relabelled_as_individual_fact": False,
                "raw_microdata_in_model_context": False,
                "startup_work_item_cap": 1,
                "scale_allowed": False,
                "raw_output_is_forecast": False,
                "pre_validation_agentic_lambda": 0.0,
                "target_outcomes_present": False,
            }
            for name in ("run_state.json", "output_manifest.json", "preflight.json"):
                target = output_root / name
                if not target.is_file():
                    continue
                payload = json.loads(target.read_text(encoding="utf-8"))
                payload["empirical_moroccan_mind_v9"] = metadata
                runner.atomic_write_json(target, payload)

        runner.write_run_state = write_state

    v8.patch_state = patched
    v8.PROTOCOL_ID = PROTOCOL_ID


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    bundle_raw = v8.option(args, "--bundle")
    if not bundle_raw:
        raise runner.RunnerError("--bundle is mandatory")
    for forbidden in ("--allow-noncanonical-counts", "--model", "--reasoning"):
        if forbidden in args or any(value.startswith(forbidden + "=") for value in args):
            raise runner.RunnerError(f"{forbidden} is forbidden by Empirical Mind V9")
    manifest_path = locate_empirical_manifest(pathlib.Path(bundle_raw))
    empirical, digest = validate_empirical_manifest(manifest_path)
    limit = v8.option(args, "--limit")
    if limit is not None and int(limit) > 1:
        raise runner.RunnerError("Empirical Mind V9 is capped at one work item; no override exists")
    patch_v8_state(empirical, digest, manifest_path)
    return v8.main(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (runner.RunnerError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

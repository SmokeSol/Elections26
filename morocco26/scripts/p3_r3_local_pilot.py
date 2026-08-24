#!/usr/bin/env python3
from __future__ import annotations

"""R3 - build and measure the LOCAL-only pilot, 2x2 with replication. No model call here.

    build-arms   build A_batch / B_batch / A_solo / B_solo (+ optional A0) and a run plan
    measure      audit every cell and compute the 2x2 contrasts, the interaction and the null

The four cells share one rich population, so every contrast is paired on
archetype identity. Same-condition replicates give the null: two calls on
identical inputs already differ, so an effect smaller than that difference is
not an effect.
"""

import argparse
import copy
import itertools
import json
import pathlib
import shutil
import statistics
import subprocess
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.behavioral_environment_v8_1 import (  # noqa: E402
    build_behavioral_environment_v8_1,
)
from morocco26.agent_society_v4.behavioral_realism import discover_run_rows  # noqa: E402
from morocco26.agent_society_v4.behavioral_realism_v8_1 import audit_rows_v8_1  # noqa: E402
from morocco26.agent_society_v4.empirical_environment_v9_1 import (  # noqa: E402
    build_empirical_environment_v9_1,
)
from morocco26.agent_society_v4.p3_data_layers_v1 import (  # noqa: E402
    P3DataLayerError,
    load_certificate,
    sha256_file,
    sha256_json,
)

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
LOCAL_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1_1_LOCAL_ONLY.md"
LOCAL_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1_1_LOCAL_ONLY.json"
DIMENSIONS = BASE / "EMPIRICAL_MIND_DIMENSIONS_V1.json"
AMENDMENT = BASE / "EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json"
SOURCES = BASE / "EMPIRICAL_SOURCE_REGISTRY_V1.json"
ADDENDUM = BASE / "EMPIRICAL_MIND_PROMPT_ADDENDUM_V1_1.md"
FREEZE_MANIFEST = BASE / "FREEZE_MANIFEST_V9_1_P3_REMEDIATION.json"
DATA = REPO_ROOT / "morocco26" / "data" / "goal100" / "agent_society_v2"
PROTOCOL = DATA / "P3_R3_LOCAL_ONLY_PILOT_PROTOCOL_V1.json"

PROMOTION_THRESHOLD = 0.20
NOISE_MULTIPLE = 2.0


def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def provenance(ci_conclusion: str | None) -> dict[str, Any]:
    """What has to be true, and recorded, before the first model call."""
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    clean = status == "" if status is not None else None
    return {
        "git_head_sha": head,
        "working_tree_clean": clean,
        "uncommitted_paths": [line[3:] for line in (status or "").splitlines()][:20],
        "freeze_manifest": str(FREEZE_MANIFEST.relative_to(REPO_ROOT)).replace("\\", "/"),
        "freeze_manifest_sha256": sha256_file(FREEZE_MANIFEST) if FREEZE_MANIFEST.is_file() else None,
        "freeze_manifest_revision": (
            read_json(FREEZE_MANIFEST).get("freeze_revision") if FREEZE_MANIFEST.is_file() else None
        ),
        "ci_freeze_gate_conclusion": ci_conclusion,
        "ci_recorded_by": "operator, via --ci-conclusion",
        "requirement": (
            "git_head_sha pinned, working_tree_clean true, ci_freeze_gate_conclusion success. "
            "Any other state makes the run unreproducible."
        ),
    }


def build_named_environment(named_input_path: pathlib.Path, output: pathlib.Path) -> dict[str, Any]:
    scripts = REPO_ROOT / "morocco26" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import three_regime_core as trc  # noqa: E402

    return trc.build_named_environment(read_json(named_input_path), pathlib.Path(output))


def split_into_single_voter_work_items(
    source: pathlib.Path, output: pathlib.Path, *, limit: int | None = None
) -> dict[str, Any]:
    """One voter per work item, so no voter can read another's answer."""
    source = pathlib.Path(source).expanduser().resolve()
    output = pathlib.Path(output).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    work_items: list[dict[str, Any]] = []
    for path in sorted((output / "voter_batches").rglob("*.json")):
        batch = read_json(path)
        key = next(
            (k for k in ("voter_archetypes", "archetypes", "voters") if isinstance(batch.get(k), list)),
            None,
        )
        if key is None:
            continue
        territory_id = str(batch.get("anonymous_territory_id") or batch.get("territory_id") or "")
        original_batch_id = str(batch.get("batch_id") or "B01")
        voters = list(batch[key])
        if limit is not None:
            voters = voters[:limit]
        for index, voter in enumerate(voters, 1):
            solo_id = f"{original_batch_id}_V{index:03d}"
            solo = copy.deepcopy(batch)
            solo[key] = [voter]
            solo["batch_id"] = solo_id
            solo["single_voter_work_item"] = True
            solo_path = path.parent / f"{solo_id}.json"
            write_json(solo_path, solo)
            work_items.append(
                {
                    "anonymous_election_id": "MOROCCO_2026_CURRENT",
                    "anonymous_territory_id": territory_id,
                    "condition_id": "C_TRUE",
                    "batch_id": solo_id,
                    "voter_batch_path": str(solo_path.relative_to(output)).replace("\\", "/"),
                    "output_path": f"outputs/MOROCCO_2026_CURRENT/C_TRUE/{territory_id}/{solo_id}.jsonl",
                    "voters": 1,
                }
            )
        path.unlink()
    write_json(
        output / "work_manifest.json",
        {
            "work_items": work_items,
            "single_voter_work_items": True,
            "note": "One voter per model context. No voter can condition on another's answer.",
        },
    )
    return {"work_items": len(work_items), "voters_per_replicate": len(work_items)}


def command_build_arms(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate)
    if str(certificate.get("status") or "").startswith("BLOCKED"):
        raise P3DataLayerError(f"certificate is blocking: {certificate.get('blocking_findings')}")
    root = pathlib.Path(args.output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    prompt_text = LOCAL_PROMPT.read_text(encoding="utf-8")
    schema = read_json(LOCAL_SCHEMA)
    manifests: dict[str, Any] = {}

    if args.minimal_named_input:
        base = root / "A0_named"
        build_named_environment(args.minimal_named_input, base)
        manifests["A0_MINIMAL_V8_1"] = build_behavioral_environment_v8_1(
            base,
            root / "A0_MINIMAL_V8_1",
            prompt_text=prompt_text,
            output_schema=schema,
            certificate=certificate,
        )

    rich_base = root / "rich_named"
    build_named_environment(args.rich_named_input, rich_base)
    manifests["A_batch"] = build_behavioral_environment_v8_1(
        rich_base,
        root / "A_batch",
        prompt_text=prompt_text,
        output_schema=schema,
        certificate=certificate,
    )
    manifests["B_batch"] = build_empirical_environment_v9_1(
        v8_root=root / "A_batch",
        output_root=root / "B_batch",
        base_dimension_registry=read_json(DIMENSIONS),
        amendment=read_json(AMENDMENT),
        source_registry=read_json(SOURCES),
        prior_pack=None,
        snapshot_date=args.snapshot_date,
        stratum_visibility=args.stratum_visibility,
        prompt_addendum_text=ADDENDUM.read_text(encoding="utf-8"),
    )
    manifests["A_solo"] = split_into_single_voter_work_items(
        root / "A_batch", root / "A_solo", limit=args.solo_voters
    )
    manifests["B_solo"] = split_into_single_voter_work_items(
        root / "B_batch", root / "B_solo", limit=args.solo_voters
    )

    solo_calls = int(manifests["A_solo"]["work_items"])
    run_plan = []
    for arm in ("A_batch", "B_batch"):
        for replicate in range(1, args.batch_replicates + 1):
            run_plan.append(
                {
                    "arm": arm,
                    "replicate": f"r{replicate}",
                    "environment": f"{arm}",
                    "model_calls": 1,
                    "output_root": f"runs/{arm}/r{replicate}",
                }
            )
    for arm in ("A_solo", "B_solo"):
        for replicate in range(1, args.solo_replicates + 1):
            run_plan.append(
                {
                    "arm": arm,
                    "replicate": f"r{replicate}",
                    "environment": f"{arm}",
                    "model_calls": solo_calls,
                    "output_root": f"runs/{arm}/r{replicate}",
                }
            )
    total_calls = sum(item["model_calls"] for item in run_plan)

    plan = {
        "schema_version": "ATLAS_P3_R3_ARM_PLAN_V2",
        "protocol": str(PROTOCOL.relative_to(REPO_ROOT)).replace("\\", "/"),
        "protocol_sha256": sha256_json(read_json(PROTOCOL)),
        "protocol_revision": read_json(PROTOCOL).get("protocol_revision"),
        "design": "2x2 mind_layer x context, paired on archetype identity, with same-condition replication",
        "snapshot_date": args.snapshot_date,
        "provenance": provenance(args.ci_conclusion),
        "data_layer_certificate_sha256": certificate.get("certificate_sha256"),
        "layer_states": certificate.get("layer_states"),
        "gate_testability": certificate.get("gate_testability"),
        "ballots_simulated": ["LOCAL"],
        "regional_simulation_allowed": False,
        "cells": {name: manifest for name, manifest in manifests.items()},
        "run_plan": run_plan,
        "model_call_budget": {
            "batch_replicates": args.batch_replicates,
            "solo_replicates": args.solo_replicates,
            "calls_per_solo_replicate": solo_calls,
            "total_model_calls": total_calls,
        },
        "randomisation_note": "Randomise the order of the (arm, replicate) units and use a fresh context for each.",
        "promotion_rule": {
            "R3_PROMOTION_THRESHOLD": PROMOTION_THRESHOLD,
            "R3_NOISE_MULTIPLE": NOISE_MULTIPLE,
        },
        "model_calls_made_by_this_script": 0,
    }
    write_json(root / "r3_arm_plan.json", plan)

    blockers = []
    if plan["provenance"]["working_tree_clean"] is False:
        blockers.append("working tree is dirty")
    if (args.ci_conclusion or "").lower() != "success":
        blockers.append("CI freeze gate conclusion is not recorded as success")
    print(
        json.dumps(
            {
                "cells_built": sorted(manifests),
                "output_root": str(root),
                "plan": str(root / "r3_arm_plan.json"),
                "total_model_calls_planned": total_calls,
                "model_calls_made": 0,
                "preflight_blockers": blockers,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not blockers or args.allow_preflight_blockers else 3


def _local_vector(row: dict[str, Any]) -> dict[str, float]:
    value = row.get("local_party_probabilities") or {}
    return {str(k): float(v) for k, v in value.items()}


def _l1(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    return sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in keys)


def _index(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return {str(row.get("weighted_archetype_id")): _local_vector(row) for row in rows}


def paired_l1(
    base: Sequence[Sequence[dict[str, Any]]], treatment: Sequence[Sequence[dict[str, Any]]]
) -> dict[str, Any]:
    """Mean paired L1 over every (base replicate, treatment replicate) pairing."""
    values: list[float] = []
    archetypes: set[str] = set()
    for left, right in itertools.product(base, treatment):
        a, b = _index(left), _index(right)
        shared = sorted(set(a) & set(b))
        if not shared:
            continue
        archetypes |= set(shared)
        values.extend(_l1(a[key], b[key]) for key in shared)
    if not values:
        return {"status": "NOT_PAIRABLE", "reason": "no shared archetype identity"}
    return {
        "status": "MEASURED",
        "mean_paired_local_l1": round(statistics.fmean(values), 6),
        "max_paired_local_l1": round(max(values), 6),
        "paired_archetypes": len(archetypes),
        "pairings": len(base) * len(treatment),
    }


def same_condition_noise(replicates: Sequence[Sequence[dict[str, Any]]]) -> dict[str, Any]:
    if len(replicates) < 2:
        return {
            "status": "NOT_ESTIMATED",
            "reason": "a single replicate cannot estimate same-condition noise",
        }
    values: list[float] = []
    for left, right in itertools.combinations(replicates, 2):
        a, b = _index(left), _index(right)
        values.extend(_l1(a[key], b[key]) for key in sorted(set(a) & set(b)))
    if not values:
        return {"status": "NOT_ESTIMATED", "reason": "replicates share no archetype identity"}
    return {
        "status": "MEASURED",
        "mean_replicate_local_l1": round(statistics.fmean(values), 6),
        "replicate_pairs": len(list(itertools.combinations(replicates, 2))),
    }


def between_voter_dispersion(replicates: Sequence[Sequence[dict[str, Any]]]) -> float:
    values: list[float] = []
    for rows in replicates:
        vectors = list(_index(rows).values())
        for i in range(len(vectors)):
            for j in range(i + 1, len(vectors)):
                values.append(_l1(vectors[i], vectors[j]))
    return statistics.fmean(values) if values else 0.0


def command_measure(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate) if args.certificate else None
    cells: dict[str, list[list[dict[str, Any]]]] = {}
    for spec in args.arm:
        if "=" not in spec:
            raise ValueError(f"--arm expects NAME=path, got {spec!r}")
        name, path = spec.split("=", 1)
        cells.setdefault(name, []).append(
            [dict(row) for row in discover_run_rows(pathlib.Path(path))]
        )
    if not cells:
        raise ValueError("at least one --arm is required")

    report: dict[str, Any] = {
        "schema_version": "ATLAS_P3_R3_MEASUREMENT_V2",
        "design": "2x2 mind_layer x context with same-condition replication",
        "data_layer_certificate_sha256": (certificate or {}).get("certificate_sha256"),
        "gate_testability": (certificate or {}).get("gate_testability"),
        "cells": {},
        "same_condition_noise": {},
        "contrasts": {},
    }
    for name, replicates in cells.items():
        flat = replicates[0]
        report["cells"][name] = {
            "replicates": len(replicates),
            "rows_per_replicate": [len(rows) for rows in replicates],
            "audit_first_replicate": audit_rows_v8_1(
                flat, expected_rows=len(flat), certificate=certificate
            ),
        }
        report["same_condition_noise"][name] = same_condition_noise(replicates)

    for label, base_name, treatment_name in (
        ("D_mind_batch", "A_batch", "B_batch"),
        ("D_mind_solo", "A_solo", "B_solo"),
        ("D_batching_v8_1", "A_batch", "A_solo"),
        ("D_batching_v9_1", "B_batch", "B_solo"),
    ):
        if base_name in cells and treatment_name in cells:
            report["contrasts"][label] = paired_l1(cells[base_name], cells[treatment_name])

    batch = report["contrasts"].get("D_mind_batch") or {}
    solo = report["contrasts"].get("D_mind_solo") or {}
    if batch.get("status") == "MEASURED" and solo.get("status") == "MEASURED":
        interaction = batch["mean_paired_local_l1"] - solo["mean_paired_local_l1"]
        report["interaction"] = {
            "definition": "D_mind_batch - D_mind_solo",
            "value": round(interaction, 6),
            "reads_as": (
                "V9.1 moves behaviour more when the 32 voters share a context"
                if interaction > 0
                else "V9.1 moves behaviour more with fresh per-voter contexts"
                if interaction < 0
                else "no detectable dependence on the context regime"
            ),
            "caution": "Compare the magnitude against same_condition_noise before reading anything into the sign.",
        }

    if solo.get("status") == "MEASURED" and "A_solo" in cells:
        dispersion = between_voter_dispersion(cells["A_solo"])
        effect = solo["mean_paired_local_l1"]
        noises = [
            report["same_condition_noise"].get(name, {}).get("mean_replicate_local_l1")
            for name in ("A_solo", "B_solo")
        ]
        noises = [value for value in noises if value is not None]
        noise = max(noises) if noises else None
        share = effect / dispersion if dispersion > 0 else None
        report["promotion"] = {
            "R3_PROMOTION_THRESHOLD": PROMOTION_THRESHOLD,
            "R3_NOISE_MULTIPLE": NOISE_MULTIPLE,
            "between_voter_dispersion_in_A_solo": round(dispersion, 6),
            "effect_as_share_of_between_voter_dispersion": (
                round(share, 6) if share is not None else None
            ),
            "same_condition_noise_used": noise,
            "effect_over_noise": (
                round(effect / noise, 6) if noise not in (None, 0) else None
            ),
            "passes_threshold": bool(share is not None and share >= PROMOTION_THRESHOLD),
            "passes_noise_rule": bool(
                noise not in (None, 0) and effect >= NOISE_MULTIPLE * noise
            ),
            "noise_estimated": noise is not None,
            "verdict": None,
        }
        promotion = report["promotion"]
        if not promotion["noise_estimated"]:
            promotion["verdict"] = "INCONCLUSIVE_NO_NULL_ESTIMATED"
        elif promotion["passes_threshold"] and promotion["passes_noise_rule"]:
            promotion["verdict"] = "PROMOTE_CURRENT_V9_1_MECHANISM"
        else:
            promotion["verdict"] = "BLOCK_PROMOTION_UNDER_CURRENT_LOCAL_SURFACE"
        promotion["interpretation_boundary"] = (
            "BLOCK_PROMOTION_UNDER_CURRENT_LOCAL_SURFACE is not proof that V9.1 cannot interact "
            "with a richer electoral offer. R3 runs without real programmes, without party memory "
            "and without a regional ballot."
        )

    if "A0_MINIMAL_V8_1" in cells:
        report["A0_comparison_note"] = (
            "A0 uses the seven-column named population. It shares no archetype identity with the "
            "rich cells, so it is reported as a reference, never as a paired control."
        )
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    failed = [
        name
        for name, cell in report["cells"].items()
        if not cell["audit_first_replicate"]["pilot_pass_over_testable_gates"]
    ]
    return 0 if not failed else 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-arms")
    build.add_argument("--rich-named-input", type=pathlib.Path, required=True)
    build.add_argument("--minimal-named-input", type=pathlib.Path)
    build.add_argument("--certificate", type=pathlib.Path, required=True)
    build.add_argument("--snapshot-date", required=True)
    build.add_argument("--stratum-visibility", choices=("context", "hidden"), default="context")
    build.add_argument("--batch-replicates", type=int, default=3)
    build.add_argument("--solo-replicates", type=int, default=2)
    build.add_argument(
        "--solo-voters",
        type=int,
        help="cap the number of single-voter work items per solo replicate; omit to use every voter",
    )
    build.add_argument(
        "--ci-conclusion",
        help="conclusion of the freeze-gate CI run on the exact HEAD sha, e.g. success",
    )
    build.add_argument("--allow-preflight-blockers", action="store_true")
    build.add_argument("--output-root", type=pathlib.Path, required=True)
    build.set_defaults(func=command_build_arms)

    measure = sub.add_parser("measure")
    measure.add_argument(
        "--arm",
        action="append",
        default=[],
        help="NAME=path/to/run/root; repeat the same NAME once per replicate",
    )
    measure.add_argument("--certificate", type=pathlib.Path)
    measure.add_argument("--output", type=pathlib.Path)
    measure.set_defaults(func=command_measure)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (P3DataLayerError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

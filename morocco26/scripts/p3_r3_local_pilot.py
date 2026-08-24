#!/usr/bin/env python3
from __future__ import annotations

"""R3 - build and measure the LOCAL-only pilot arms. No model is called here.

    build-arms   build A0 / A / B / C environments from named inputs
    measure      audit each arm's outputs and compute the paired contrasts

Arm A and arm B share the same population and differ only by the mind layer, so
their contrast is paired. Arm C is arm B split into one voter per work item,
which is how intra-batch conditioning gets measured instead of assumed.
"""

import argparse
import copy
import json
import pathlib
import shutil
import statistics
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
    sha256_json,
)

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
LOCAL_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1_1_LOCAL_ONLY.md"
LOCAL_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1_1_LOCAL_ONLY.json"
DIMENSIONS = BASE / "EMPIRICAL_MIND_DIMENSIONS_V1.json"
AMENDMENT = BASE / "EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json"
SOURCES = BASE / "EMPIRICAL_SOURCE_REGISTRY_V1.json"
ADDENDUM = BASE / "EMPIRICAL_MIND_PROMPT_ADDENDUM_V1_1.md"
PROTOCOL = (
    REPO_ROOT
    / "morocco26"
    / "data"
    / "goal100"
    / "agent_society_v2"
    / "P3_R3_LOCAL_ONLY_PILOT_PROTOCOL_V1.json"
)


def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def build_named_environment(named_input_path: pathlib.Path, output: pathlib.Path) -> dict[str, Any]:
    scripts = REPO_ROOT / "morocco26" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import three_regime_core as trc  # noqa: E402

    return trc.build_named_environment(read_json(named_input_path), pathlib.Path(output))


def split_into_single_voter_work_items(source: pathlib.Path, output: pathlib.Path) -> dict[str, Any]:
    """Arm C: one voter per work item, so no voter can read another's answer."""
    source = pathlib.Path(source).expanduser().resolve()
    output = pathlib.Path(output).expanduser().resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    work_items: list[dict[str, Any]] = []
    created = 0
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
        for index, voter in enumerate(voters, 1):
            solo_id = f"{original_batch_id}_V{index:03d}"
            solo = copy.deepcopy(batch)
            solo[key] = [voter]
            solo["batch_id"] = solo_id
            solo["single_voter_work_item"] = True
            solo_path = path.parent / f"{solo_id}.json"
            write_json(solo_path, solo)
            created += 1
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
            "note": "Arm C: one voter per model context. No voter can condition on another's answer.",
        },
    )
    return {"work_items": len(work_items), "voter_batches_created": created}


def command_build_arms(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate)
    if str(certificate.get("status") or "").startswith("BLOCKED"):
        raise P3DataLayerError(f"certificate is blocking: {certificate.get('blocking_findings')}")
    if certificate.get("dual_ballot_simulation_allowed"):
        print(
            "note: the certificate allows a regional ballot; R3 is LOCAL-only by design and ignores it",
            file=sys.stderr,
        )
    root = pathlib.Path(args.output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    prompt_text = LOCAL_PROMPT.read_text(encoding="utf-8")
    schema = read_json(LOCAL_SCHEMA)
    built: dict[str, Any] = {}

    if args.minimal_named_input:
        base = root / "A0_named"
        build_named_environment(args.minimal_named_input, base)
        built["A0_MINIMAL_V8_1"] = build_behavioral_environment_v8_1(
            base,
            root / "A0_MINIMAL_V8_1",
            prompt_text=prompt_text,
            output_schema=schema,
            certificate=certificate,
        )

    rich_base = root / "rich_named"
    build_named_environment(args.rich_named_input, rich_base)
    built["A_RICH_V8_1"] = build_behavioral_environment_v8_1(
        rich_base,
        root / "A_RICH_V8_1",
        prompt_text=prompt_text,
        output_schema=schema,
        certificate=certificate,
    )
    built["B_RICH_V9_1"] = build_empirical_environment_v9_1(
        v8_root=root / "A_RICH_V8_1",
        output_root=root / "B_RICH_V9_1",
        base_dimension_registry=read_json(DIMENSIONS),
        amendment=read_json(AMENDMENT),
        source_registry=read_json(SOURCES),
        prior_pack=None,
        snapshot_date=args.snapshot_date,
        stratum_visibility=args.stratum_visibility,
        prompt_addendum_text=ADDENDUM.read_text(encoding="utf-8"),
    )
    built["C_RICH_V9_1_SOLO"] = split_into_single_voter_work_items(
        root / "B_RICH_V9_1", root / "C_RICH_V9_1_SOLO"
    )

    plan = {
        "schema_version": "ATLAS_P3_R3_ARM_PLAN_V1",
        "protocol": str(PROTOCOL.relative_to(REPO_ROOT)).replace("\\", "/"),
        "protocol_sha256": sha256_json(read_json(PROTOCOL)),
        "snapshot_date": args.snapshot_date,
        "data_layer_certificate_sha256": certificate.get("certificate_sha256"),
        "layer_states": certificate.get("layer_states"),
        "gate_testability": certificate.get("gate_testability"),
        "ballots_simulated": ["LOCAL"],
        "regional_simulation_allowed": False,
        "arms": {name: manifest for name, manifest in built.items()},
        "arm_order_note": "Randomise arm order at run time and use a fresh context per arm.",
        "model_calls_made_by_this_script": 0,
    }
    write_json(root / "r3_arm_plan.json", plan)
    print(
        json.dumps(
            {
                "arms_built": sorted(built),
                "output_root": str(root),
                "plan": str(root / "r3_arm_plan.json"),
                "model_calls_made": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _local_vector(row: dict[str, Any]) -> dict[str, float]:
    value = row.get("local_party_probabilities") or {}
    return {str(k): float(v) for k, v in value.items()}


def _l1(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    return sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in keys)


def _top_set(vector: dict[str, float]) -> frozenset[str]:
    if not vector:
        return frozenset()
    best = max(vector.values())
    return frozenset(key for key, value in vector.items() if abs(value - best) <= 1e-12)


def paired_contrast(base_rows: Sequence[dict[str, Any]], treatment_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    base = {str(row.get("weighted_archetype_id")): row for row in base_rows}
    treatment = {str(row.get("weighted_archetype_id")): row for row in treatment_rows}
    shared = sorted(set(base) & set(treatment))
    if not shared:
        return {"status": "NOT_PAIRABLE", "reason": "no shared archetype identity between the arms"}
    l1 = []
    turnout_delta = []
    identical_top = 0
    for archetype in shared:
        a = _local_vector(base[archetype])
        b = _local_vector(treatment[archetype])
        l1.append(_l1(a, b))
        try:
            turnout_delta.append(
                float(treatment[archetype].get("turnout_probability"))
                - float(base[archetype].get("turnout_probability"))
            )
        except (TypeError, ValueError):
            pass
        identical_top += int(_top_set(a) == _top_set(b))
    between = []
    vectors = [_local_vector(base[archetype]) for archetype in shared]
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            between.append(_l1(vectors[i], vectors[j]))
    mean_between = statistics.fmean(between) if between else 0.0
    mean_paired = statistics.fmean(l1)
    return {
        "status": "MEASURED",
        "paired_archetypes": len(shared),
        "mean_paired_local_l1": round(mean_paired, 6),
        "max_paired_local_l1": round(max(l1), 6),
        "rows_changed": sum(1 for value in l1 if value > 1e-9),
        "mean_between_voter_local_l1_in_base": round(mean_between, 6),
        "effect_as_share_of_between_voter_dispersion": (
            round(mean_paired / mean_between, 6) if mean_between > 0 else None
        ),
        "mechanism_threshold": 0.20,
        "reads_as_mechanism": bool(mean_between > 0 and (mean_paired / mean_between) >= 0.20),
        "mean_turnout_delta": round(statistics.fmean(turnout_delta), 6) if turnout_delta else None,
        "identical_top_option_sets": identical_top,
    }


def command_measure(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate) if args.certificate else None
    arms: dict[str, list[dict[str, Any]]] = {}
    for spec in args.arm:
        if "=" not in spec:
            raise ValueError(f"--arm expects NAME=path, got {spec!r}")
        name, path = spec.split("=", 1)
        arms[name] = [dict(row) for row in discover_run_rows(pathlib.Path(path))]
    if not arms:
        raise ValueError("at least one --arm is required")
    report: dict[str, Any] = {
        "schema_version": "ATLAS_P3_R3_MEASUREMENT_V1",
        "data_layer_certificate_sha256": (certificate or {}).get("certificate_sha256"),
        "gate_testability": (certificate or {}).get("gate_testability"),
        "arms": {},
        "paired_contrasts": {},
    }
    for name, rows in arms.items():
        report["arms"][name] = audit_rows_v8_1(
            rows, expected_rows=len(rows), certificate=certificate
        )
    names = list(arms)
    for base_name, treatment_name in (
        ("A_RICH_V8_1", "B_RICH_V9_1"),
        ("B_RICH_V9_1", "C_RICH_V9_1_SOLO"),
    ):
        if base_name in arms and treatment_name in arms:
            report["paired_contrasts"][f"{base_name}__vs__{treatment_name}"] = paired_contrast(
                arms[base_name], arms[treatment_name]
            )
    if "A0_MINIMAL_V8_1" in names:
        report["A0_comparison_note"] = (
            "A0 uses the seven-column named population. It shares no archetype identity with the "
            "rich arms, so it is reported as a reference, never as a paired control."
        )
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    failed = [
        name for name, audit in report["arms"].items() if not audit["pilot_pass_over_testable_gates"]
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
    build.add_argument("--output-root", type=pathlib.Path, required=True)
    build.set_defaults(func=command_build_arms)

    measure = sub.add_parser("measure")
    measure.add_argument("--arm", action="append", default=[], help="NAME=path/to/run/root")
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

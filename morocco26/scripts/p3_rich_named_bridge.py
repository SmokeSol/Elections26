#!/usr/bin/env python3
from __future__ import annotations

"""R2 CLI - wire the rich Moroccan population into the named 2026 pipeline.

    bridge      join a rich population onto a named input and emit both the new
                named input and the bridge certificate
    inspect     report how a rich record partitions into individual / household /
                survey-stratum / territory layers, without building anything

The rich population artifact is produced by the existing CI builders
(agent_society_v2_build_rich_populations_v2.py and
agent_society_v2_build_attitude_overlay.py). This CLI never synthesises one.
"""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.rich_named_bridge_v1 import (  # noqa: E402
    RichNamedBridgeError,
    bridge_rich_population,
    partition_fields,
    read_json,
    read_jsonl,
)


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def command_bridge(args: argparse.Namespace) -> int:
    named_input = read_json(args.named_input)
    rich_population = read_json(args.rich_population)
    overlay_rows = read_jsonl(args.attitude_overlay) if args.attitude_overlay else []
    crosswalk = read_json(args.crosswalk) if args.crosswalk else None
    if crosswalk is not None and not isinstance(crosswalk, dict):
        raise RichNamedBridgeError("crosswalk must be a JSON object named_territory_id -> constituency_id")
    result, certificate = bridge_rich_population(
        named_input=named_input,
        rich_population=rich_population,
        attitude_overlay_rows=overlay_rows,
        crosswalk=crosswalk,
        voters_per_territory=args.voters_per_territory,
        allow_prior_election_anchor=args.allow_prior_election_anchor,
        snapshot_id=args.snapshot_id,
        only_territories=args.only_territory,
    )
    write_json(args.output, result)
    write_json(args.certificate_output, certificate)
    print(json.dumps(certificate, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def command_inspect(args: argparse.Namespace) -> int:
    rich_population = read_json(args.rich_population)
    territories = rich_population.get("territories") or []
    if not territories:
        raise RichNamedBridgeError("rich population declares no territory")
    archetypes = territories[0].get("archetypes") or []
    if not archetypes:
        raise RichNamedBridgeError("rich population territory declares no archetype")
    partition = partition_fields(archetypes[0])
    summary = {
        "population_id": rich_population.get("population_id"),
        "territories": len(territories),
        "archetypes_per_territory": len(archetypes),
        "fields_per_record": len(archetypes[0]),
        "partition_counts": {key: len(value) for key, value in partition.items()},
        "partition": partition,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    bridge = sub.add_parser("bridge")
    bridge.add_argument("--named-input", type=pathlib.Path, required=True)
    bridge.add_argument("--rich-population", type=pathlib.Path, required=True)
    bridge.add_argument("--attitude-overlay", type=pathlib.Path)
    bridge.add_argument(
        "--crosswalk",
        type=pathlib.Path,
        help="JSON object mapping named territory_id to rich constituency_id",
    )
    bridge.add_argument("--voters-per-territory", type=int, default=32)
    bridge.add_argument(
        "--only-territory",
        action="append",
        default=[],
        help="restrict the bridge to these territory ids; repeat for several",
    )
    bridge.add_argument("--snapshot-id")
    bridge.add_argument(
        "--allow-prior-election-anchor",
        action="store_true",
        help="opt in to importing prior_vote_or_abstention; forbidden by default in a current-vintage environment",
    )
    bridge.add_argument("--output", type=pathlib.Path, required=True)
    bridge.add_argument("--certificate-output", type=pathlib.Path, required=True)
    bridge.set_defaults(func=command_bridge)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--rich-population", type=pathlib.Path, required=True)
    inspect.set_defaults(func=command_inspect)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RichNamedBridgeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

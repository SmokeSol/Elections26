#!/usr/bin/env python3
from __future__ import annotations

"""R4/R5 CLI - validate and ingest the two electoral surfaces still to collect.

    validate-programmes   check party_programme_2026.json against its contract
    validate-regional     check regional_ballot_2026.json against its contract
    ingest-programmes     replace the synthetic scaffold in a named input
    attach-regional       attach a real regional surface to a built environment

Both datasets ship empty on purpose. Validation of an empty dataset passes: the
absence is the honest state, and R0 reports it as PLACEHOLDER / MISSING rather
than letting the environment invent a substitute.
"""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.electoral_offer_2026_v1 import (  # noqa: E402
    ElectoralOfferError,
    attach_regional_ballot_cards,
    ingest_programmes,
    read_json,
    validate_programme_dataset,
    validate_regional_dataset,
)

AS2_ROOT = REPO_ROOT / "morocco26" / "data" / "goal100" / "agent_society_v2"
DEFAULT_PROGRAMMES = AS2_ROOT / "party_programme_2026.json"
DEFAULT_REGIONAL = AS2_ROOT / "regional_ballot_2026.json"


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def command_validate_programmes(args: argparse.Namespace) -> int:
    report = validate_programme_dataset(read_json(args.dataset), snapshot_date=args.snapshot_date)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if args.require_collected and report["dataset_status"] != "PASS_PARTY_PROGRAMME_2026_COLLECTED":
        return 2
    return 0


def command_validate_regional(args: argparse.Namespace) -> int:
    report = validate_regional_dataset(read_json(args.dataset), snapshot_date=args.snapshot_date)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if args.require_collected and report["dataset_status"] != "PASS_REGIONAL_BALLOT_2026_COLLECTED":
        return 2
    return 0


def command_ingest_programmes(args: argparse.Namespace) -> int:
    result, report = ingest_programmes(
        read_json(args.named_input), read_json(args.dataset), snapshot_date=args.snapshot_date
    )
    write_json(args.output, result)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def command_attach_regional(args: argparse.Namespace) -> int:
    territory_region = read_json(args.territory_region_map)
    if not isinstance(territory_region, dict):
        raise ElectoralOfferError("territory-region map must be a JSON object territory_id -> region_id")
    report = attach_regional_ballot_cards(
        args.environment,
        read_json(args.dataset),
        territory_region=territory_region,
        snapshot_date=args.snapshot_date,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    vp = sub.add_parser("validate-programmes")
    vp.add_argument("--dataset", type=pathlib.Path, default=DEFAULT_PROGRAMMES)
    vp.add_argument("--snapshot-date")
    vp.add_argument("--require-collected", action="store_true")
    vp.set_defaults(func=command_validate_programmes)

    vr = sub.add_parser("validate-regional")
    vr.add_argument("--dataset", type=pathlib.Path, default=DEFAULT_REGIONAL)
    vr.add_argument("--snapshot-date")
    vr.add_argument("--require-collected", action="store_true")
    vr.set_defaults(func=command_validate_regional)

    ip = sub.add_parser("ingest-programmes")
    ip.add_argument("--named-input", type=pathlib.Path, required=True)
    ip.add_argument("--dataset", type=pathlib.Path, default=DEFAULT_PROGRAMMES)
    ip.add_argument("--snapshot-date")
    ip.add_argument("--output", type=pathlib.Path, required=True)
    ip.set_defaults(func=command_ingest_programmes)

    ar = sub.add_parser("attach-regional")
    ar.add_argument("--environment", type=pathlib.Path, required=True)
    ar.add_argument("--dataset", type=pathlib.Path, default=DEFAULT_REGIONAL)
    ar.add_argument("--territory-region-map", type=pathlib.Path, required=True)
    ar.add_argument("--snapshot-date")
    ar.set_defaults(func=command_attach_regional)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ElectoralOfferError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

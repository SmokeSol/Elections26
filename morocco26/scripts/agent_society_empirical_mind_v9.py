#!/usr/bin/env python3
from __future__ import annotations

"""CLI for Empirical Moroccan Mind V9 registries, priors and voter overlays."""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.empirical_environment_v9 import build_empirical_environment
from morocco26.agent_society_v4.empirical_mind_v9 import build_empirical_mind
from morocco26.agent_society_v4.empirical_priors_v9 import (
    EmpiricalPriorError,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)
from morocco26.agent_society_v4.empirical_validation_v9 import audit_empirical_mind


class CliError(RuntimeError):
    pass


def load(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read JSON {path}: {exc}") from exc


def write(path: pathlib.Path, value: Any) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def common_registry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dimensions", required=True, type=pathlib.Path)
    parser.add_argument("--sources", required=True, type=pathlib.Path)
    parser.add_argument("--snapshot-date", required=True)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Agent Society Empirical Moroccan Mind V9")
    sub = ap.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("validate-registry")
    common_registry_args(reg)

    prior = sub.add_parser("validate-prior-pack")
    common_registry_args(prior)
    prior.add_argument("--prior-pack", required=True, type=pathlib.Path)
    prior.add_argument("--allow-blocked-template", action="store_true")

    voter = sub.add_parser("build-voter")
    common_registry_args(voter)
    voter.add_argument("--voter", required=True, type=pathlib.Path)
    voter.add_argument("--household", type=pathlib.Path)
    voter.add_argument("--context", type=pathlib.Path)
    voter.add_argument("--prior-pack", type=pathlib.Path)
    voter.add_argument("--snapshot-id", required=True)
    voter.add_argument("--replicate-id", default="R00")
    voter.add_argument("--output", required=True, type=pathlib.Path)
    voter.add_argument("--audit-output", type=pathlib.Path)

    env = sub.add_parser("build-environment")
    common_registry_args(env)
    env.add_argument("--v8-environment", required=True, type=pathlib.Path)
    env.add_argument("--output", required=True, type=pathlib.Path)
    env.add_argument("--prior-pack", type=pathlib.Path)
    env.add_argument("--replicate-id", default="R00")
    env.add_argument("--prompt-addendum", type=pathlib.Path)

    audit = sub.add_parser("audit-voter")
    common_registry_args(audit)
    audit.add_argument("--mind", required=True, type=pathlib.Path)
    audit.add_argument("--prior-pack", type=pathlib.Path)
    audit.add_argument("--forecast-lambda", type=float, default=0.0)
    audit.add_argument("--output", type=pathlib.Path)

    args = ap.parse_args(argv)
    dimensions = load(args.dimensions)
    sources = load(args.sources)
    if args.command == "validate-registry":
        result = {
            "dimensions": validate_dimension_registry(dimensions),
            "sources": validate_source_registry(sources, snapshot_date=args.snapshot_date),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.command == "validate-prior-pack":
        result = validate_prior_pack(
            load(args.prior_pack),
            source_registry=sources,
            dimension_registry=dimensions,
            snapshot_date=args.snapshot_date,
            require_calibrated=not args.allow_blocked_template,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.command == "build-voter":
        prior_pack = load(args.prior_pack) if args.prior_pack else None
        mind, audit_result = build_empirical_mind(
            voter=load(args.voter),
            household=load(args.household) if args.household else None,
            ecological_context=load(args.context) if args.context else None,
            dimension_registry=dimensions,
            source_registry=sources,
            prior_pack=prior_pack,
            snapshot_id=args.snapshot_id,
            snapshot_date=args.snapshot_date,
            replicate_id=args.replicate_id,
        )
        write(args.output, mind)
        if args.audit_output:
            write(args.audit_output, audit_result)
        print("PASS_EMPIRICAL_MIND_V9_VOTER_BUILT")
        return 0
    if args.command == "build-environment":
        manifest = build_empirical_environment(
            v8_root=args.v8_environment,
            output_root=args.output,
            dimension_registry=dimensions,
            source_registry=sources,
            prior_pack=load(args.prior_pack) if args.prior_pack else None,
            snapshot_date=args.snapshot_date,
            replicate_id=args.replicate_id,
            prompt_addendum_text=(
                args.prompt_addendum.expanduser().read_text(encoding="utf-8")
                if args.prompt_addendum
                else None
            ),
        )
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.command == "audit-voter":
        result = audit_empirical_mind(
            load(args.mind),
            dimension_registry=dimensions,
            source_registry=sources,
            prior_pack=load(args.prior_pack) if args.prior_pack else None,
            snapshot_date=args.snapshot_date,
            forecast_lambda=args.forecast_lambda,
        )
        if args.output:
            write(args.output, result)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    raise CliError("unreachable command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CliError, EmpiricalPriorError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

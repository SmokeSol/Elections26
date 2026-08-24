#!/usr/bin/env python3
from __future__ import annotations

"""CLI for Empirical Moroccan Mind V9.1 (amendment 01).

    validate-amendment   apply the amendment to the frozen registry and validate it
    build-voter          build one V9.1 mind
    build-environment    overlay V9.1 onto a V8/V8.1 environment
    audit-voter          run EM0-EM12 on a stored mind

The frozen V9 payload is never modified; the amendment is applied at load time.
"""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.empirical_environment_v9_1 import (  # noqa: E402
    build_empirical_environment_v9_1,
)
from morocco26.agent_society_v4.empirical_mind_v9_1 import (  # noqa: E402
    EmpiricalMindV91Error,
    apply_registry_amendment,
    build_empirical_mind_v9_1,
)
from morocco26.agent_society_v4.empirical_priors_v9 import (  # noqa: E402
    EmpiricalPriorError,
    validate_dimension_registry,
    validate_source_registry,
)
from morocco26.agent_society_v4.empirical_validation_v9_1 import (  # noqa: E402
    audit_empirical_mind_v9_1,
)

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
DEFAULT_DIMENSIONS = BASE / "EMPIRICAL_MIND_DIMENSIONS_V1.json"
DEFAULT_AMENDMENT = BASE / "EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json"
DEFAULT_SOURCES = BASE / "EMPIRICAL_SOURCE_REGISTRY_V1.json"
DEFAULT_ADDENDUM = BASE / "EMPIRICAL_MIND_PROMPT_ADDENDUM_V1_1.md"


class CliError(RuntimeError):
    pass


def load(path: pathlib.Path) -> Any:
    try:
        return json.loads(pathlib.Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read JSON {path}: {exc}") from exc


def write(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def common_registry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dimensions", type=pathlib.Path, default=DEFAULT_DIMENSIONS)
    parser.add_argument("--amendment", type=pathlib.Path, default=DEFAULT_AMENDMENT)
    parser.add_argument("--sources", type=pathlib.Path, default=DEFAULT_SOURCES)
    parser.add_argument("--snapshot-date", required=True)


def effective_registry(args: argparse.Namespace) -> dict[str, Any]:
    return apply_registry_amendment(load(args.dimensions), load(args.amendment))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("validate-amendment")
    common_registry_args(reg)
    reg.add_argument("--output", type=pathlib.Path)

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
    env.add_argument("--base-environment", required=True, type=pathlib.Path)
    env.add_argument("--output", required=True, type=pathlib.Path)
    env.add_argument("--prior-pack", type=pathlib.Path)
    env.add_argument("--replicate-id", default="R00")
    env.add_argument("--prompt-addendum", type=pathlib.Path, default=DEFAULT_ADDENDUM)
    env.add_argument(
        "--stratum-visibility",
        choices=("context", "hidden"),
        default="context",
        help="context: stratum priors are shown as a labelled group description; "
        "hidden: they stay in the audit only",
    )

    audit = sub.add_parser("audit-voter")
    common_registry_args(audit)
    audit.add_argument("--mind", required=True, type=pathlib.Path)
    audit.add_argument("--prior-pack", type=pathlib.Path)
    audit.add_argument("--forecast-lambda", type=float, default=0.0)
    audit.add_argument("--output", type=pathlib.Path)

    args = ap.parse_args(argv)
    registry = effective_registry(args)
    sources = load(args.sources)

    if args.command == "validate-amendment":
        result = {
            "dimensions": validate_dimension_registry(registry),
            "sources": validate_source_registry(sources, snapshot_date=args.snapshot_date),
            "version": registry.get("version"),
            "amendment_id": registry.get("amendment_id"),
            "new_dimensions": sorted(
                str(row["dimension_id"]) for row in load(args.amendment).get("new_dimensions") or []
            ),
        }
        if args.output:
            write(args.output, registry)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    if args.command == "build-voter":
        mind, audit_result = build_empirical_mind_v9_1(
            voter=load(args.voter),
            household=load(args.household) if args.household else None,
            ecological_context=load(args.context) if args.context else None,
            dimension_registry=registry,
            source_registry=sources,
            prior_pack=load(args.prior_pack) if args.prior_pack else None,
            snapshot_id=args.snapshot_id,
            snapshot_date=args.snapshot_date,
            replicate_id=args.replicate_id,
        )
        write(args.output, mind)
        if args.audit_output:
            write(args.audit_output, audit_result)
        print("PASS_EMPIRICAL_MIND_V9_1_VOTER_BUILT")
        return 0

    if args.command == "build-environment":
        addendum = args.prompt_addendum
        manifest = build_empirical_environment_v9_1(
            v8_root=args.base_environment,
            output_root=args.output,
            base_dimension_registry=load(args.dimensions),
            amendment=load(args.amendment),
            source_registry=sources,
            prior_pack=load(args.prior_pack) if args.prior_pack else None,
            snapshot_date=args.snapshot_date,
            replicate_id=args.replicate_id,
            stratum_visibility=args.stratum_visibility,
            prompt_addendum_text=(
                pathlib.Path(addendum).expanduser().read_text(encoding="utf-8")
                if addendum and pathlib.Path(addendum).expanduser().is_file()
                else None
            ),
        )
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        return 0

    if args.command == "audit-voter":
        result = audit_empirical_mind_v9_1(
            load(args.mind),
            dimension_registry=registry,
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
    except (CliError, EmpiricalMindV91Error, EmpiricalPriorError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

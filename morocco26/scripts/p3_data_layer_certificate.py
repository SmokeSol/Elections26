#!/usr/bin/env python3
from __future__ import annotations

"""R0 CLI - certify the four P3 data layers of a named 2026 input.

    publish-cell-census   write the canonical ballot-cell snapshot of a named input
    certify               measure the layers and write P3_DATA_LAYER_CERTIFICATE_V1.json
    verify                re-check a stored certificate (hash, placeholder visibility)

The certificate and the canonical ballot-cell census are published together on
purpose: a P3 environment may not embed a data layer whose canonical snapshot
and certificate do not travel in the same lineage.
"""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.p3_data_layers_v1 import (  # noqa: E402
    P3DataLayerError,
    assert_no_placeholder_is_model_visible,
    build_cell_census,
    build_certificate,
    load_certificate,
    read_json,
    sha256_file,
)

DATA_ROOT = REPO_ROOT / "morocco26" / "data"
AS2_ROOT = DATA_ROOT / "goal100" / "agent_society_v2"
DEFAULT_COVERAGE = DATA_ROOT / "candidate_coverage_2026.json"
DEFAULT_CELL_CENSUS = DATA_ROOT / "candidate_ballot_cells_2026.json"
DEFAULT_RICH_CERTIFICATE = AS2_ROOT / "population_certificate_v1.json"
DEFAULT_OUTPUT = AS2_ROOT / "P3_DATA_LAYER_CERTIFICATE_V1.json"
DEFAULT_PROGRAMME_DATASET = AS2_ROOT / "party_programme_2026.json"
DEFAULT_REGIONAL_DATASET = AS2_ROOT / "regional_ballot_2026.json"


def write_json(path: pathlib.Path, value: Any) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def relative(path: pathlib.Path | None) -> str | None:
    if path is None:
        return None
    resolved = pathlib.Path(path).expanduser().resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def optional_json(path: pathlib.Path | None):
    if path is None:
        return None
    path = pathlib.Path(path).expanduser()
    if not path.is_file():
        return None
    return read_json(path)


def command_publish_cell_census(args: argparse.Namespace) -> int:
    named_path = args.named_input.expanduser().resolve()
    census = build_cell_census(
        named_input=read_json(named_path), named_input_sha256=sha256_file(named_path)
    )
    write_json(args.output, census)
    print(json.dumps(census, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


def command_certify(args: argparse.Namespace) -> int:
    named_path = args.named_input.expanduser().resolve()
    named_input = read_json(named_path)
    certificate = build_certificate(
        named_input=named_input,
        named_input_sha256=sha256_file(named_path),
        coverage_snapshot=optional_json(args.candidate_coverage),
        coverage_path=relative(args.candidate_coverage),
        cell_census=optional_json(args.cell_census),
        cell_census_path=relative(args.cell_census),
        rich_population_certificate=optional_json(args.rich_certificate),
        rich_population_certificate_path=relative(args.rich_certificate),
        regional_dataset=optional_json(args.regional_dataset),
        programme_dataset=optional_json(args.programme_dataset),
        environment_id=args.environment_id,
    )
    assert_no_placeholder_is_model_visible(certificate)
    if args.output:
        write_json(args.output, certificate)
    print(json.dumps(certificate, ensure_ascii=False, sort_keys=True, indent=2))
    return _exit_code(certificate, args)


def command_verify(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate.expanduser())
    assert_no_placeholder_is_model_visible(certificate)
    summary = {
        "status": certificate["status"],
        "layer_states": certificate["layer_states"],
        "gate_testability": certificate["gate_testability"],
        "dual_ballot_simulation_allowed": certificate["dual_ballot_simulation_allowed"],
        "blocking_findings": certificate.get("blocking_findings") or [],
        "advisory_findings": certificate.get("advisory_findings") or [],
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return _exit_code(certificate, args)


def _exit_code(certificate: dict, args: argparse.Namespace) -> int:
    status = str(certificate.get("status") or "")
    if args.fail_on_block and status.startswith("BLOCKED"):
        return 2
    if args.fail_on_advisory and (certificate.get("advisory_findings") or []):
        return 3
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    census = sub.add_parser("publish-cell-census")
    census.add_argument("--named-input", type=pathlib.Path, required=True)
    census.add_argument("--output", type=pathlib.Path, default=DEFAULT_CELL_CENSUS)
    census.set_defaults(func=command_publish_cell_census)

    certify = sub.add_parser("certify")
    certify.add_argument("--named-input", type=pathlib.Path, required=True)
    certify.add_argument("--candidate-coverage", type=pathlib.Path, default=DEFAULT_COVERAGE)
    certify.add_argument("--cell-census", type=pathlib.Path, default=DEFAULT_CELL_CENSUS)
    certify.add_argument("--rich-certificate", type=pathlib.Path, default=DEFAULT_RICH_CERTIFICATE)
    certify.add_argument("--regional-dataset", type=pathlib.Path, default=DEFAULT_REGIONAL_DATASET)
    certify.add_argument("--programme-dataset", type=pathlib.Path, default=DEFAULT_PROGRAMME_DATASET)
    certify.add_argument("--environment-id")
    certify.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    certify.add_argument("--fail-on-block", action="store_true")
    certify.add_argument("--fail-on-advisory", action="store_true")
    certify.set_defaults(func=command_certify)

    verify = sub.add_parser("verify")
    verify.add_argument("--certificate", type=pathlib.Path, default=DEFAULT_OUTPUT)
    verify.add_argument("--fail-on-block", action="store_true")
    verify.add_argument("--fail-on-advisory", action="store_true")
    verify.set_defaults(func=command_verify)
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

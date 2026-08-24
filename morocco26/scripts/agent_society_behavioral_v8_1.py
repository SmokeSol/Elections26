#!/usr/bin/env python3
from __future__ import annotations

"""Build, validate and audit Behavioral Mind V8.1 artifacts without calling a model.

V8.1 is certificate-driven: the P3 data-layer certificate decides which ballots
exist. When REGIONAL_BALLOT is not REAL/PARTIAL_REAL the environment is built
LOCAL-only, with the LOCAL-only prompt and output schema, and the regional
fallback is refused rather than silently exercised.
"""

import argparse
import json
import pathlib
import sys
import tempfile
from typing import Sequence

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.behavioral_environment_v8 import (  # noqa: E402
    BehavioralEnvironmentError,
    _safe_extract,
    locate_base_root,
    read_json,
    write_json,
)
from morocco26.agent_society_v4.behavioral_environment_v8_1 import (  # noqa: E402
    build_behavioral_environment_v8_1,
    validate_behavioral_environment_v8_1,
)
from morocco26.agent_society_v4.behavioral_realism_v8_1 import audit_run_v8_1  # noqa: E402
from morocco26.agent_society_v4.p3_data_layers_v1 import (  # noqa: E402
    USABLE_LAYER_STATES,
    P3DataLayerError,
    load_certificate,
)

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
DUAL_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1.md"
DUAL_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1.json"
LOCAL_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1_1_LOCAL_ONLY.md"
LOCAL_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1_1_LOCAL_ONLY.json"
DEFAULT_CERTIFICATE = (
    REPO_ROOT
    / "morocco26"
    / "data"
    / "goal100"
    / "agent_society_v2"
    / "P3_DATA_LAYER_CERTIFICATE_V1.json"
)


def resolve_environment(path: pathlib.Path):
    path = path.expanduser().resolve()
    if path.is_dir():
        return locate_base_root(path), None
    holder = tempfile.TemporaryDirectory(prefix="m26-behavioral-v8-1-")
    try:
        root = _safe_extract(path, pathlib.Path(holder.name))
    except Exception:
        holder.cleanup()
        raise
    return root, holder


def command_build(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate.expanduser())
    regional_ok = str((certificate.get("layer_states") or {}).get("REGIONAL_BALLOT")) in USABLE_LAYER_STATES
    prompt_path = args.prompt or (DUAL_PROMPT if regional_ok else LOCAL_PROMPT)
    schema_path = args.schema or (DUAL_SCHEMA if regional_ok else LOCAL_SCHEMA)
    root, holder = resolve_environment(args.input_env)
    try:
        manifest = build_behavioral_environment_v8_1(
            root,
            args.output_env,
            prompt_text=prompt_path.read_text(encoding="utf-8"),
            output_schema=read_json(schema_path),
            certificate=certificate,
        )
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "ballots_simulated": manifest["ballots_simulated"],
                    "regional_surface_status": manifest["regional_surface_status"],
                    "prompt": str(prompt_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "schema": str(schema_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                    "output": str(pathlib.Path(args.output_env).resolve()),
                    "manifest": manifest,
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        if holder is not None:
            holder.cleanup()


def command_validate(args: argparse.Namespace) -> int:
    root, holder = resolve_environment(args.environment)
    try:
        manifest = validate_behavioral_environment_v8_1(root)
        print(
            json.dumps(
                {"status": "PASS_BEHAVIORAL_MIND_V8_1_VALIDATED", "manifest": manifest},
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        if holder is not None:
            holder.cleanup()


def command_audit(args: argparse.Namespace) -> int:
    certificate = load_certificate(args.certificate.expanduser()) if args.certificate else None
    report = audit_run_v8_1(args.run, expected_rows=args.expected_rows, certificate=certificate)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["pilot_pass_over_testable_gates"] else 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--input-env", type=pathlib.Path, required=True)
    build.add_argument("--output-env", type=pathlib.Path, required=True)
    build.add_argument("--certificate", type=pathlib.Path, default=DEFAULT_CERTIFICATE)
    build.add_argument("--prompt", type=pathlib.Path)
    build.add_argument("--schema", type=pathlib.Path)
    build.set_defaults(func=command_build)

    validate = sub.add_parser("validate")
    validate.add_argument("--environment", type=pathlib.Path, required=True)
    validate.set_defaults(func=command_validate)

    audit = sub.add_parser("audit")
    audit.add_argument("--run", type=pathlib.Path, required=True)
    audit.add_argument("--certificate", type=pathlib.Path, default=DEFAULT_CERTIFICATE)
    audit.add_argument("--expected-rows", type=int, default=32)
    audit.add_argument("--output", type=pathlib.Path)
    audit.set_defaults(func=command_audit)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BehavioralEnvironmentError, P3DataLayerError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

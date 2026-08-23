#!/usr/bin/env python3
from __future__ import annotations

"""Build, validate, and audit Behavioral Mind V8 artifacts without calling a model."""

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
    build_behavioral_environment,
    locate_base_root,
    read_json,
    validate_behavioral_environment,
    write_json,
)
from morocco26.agent_society_v4.behavioral_realism import (  # noqa: E402
    BehavioralRealismError,
    audit_run,
)

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
DEFAULT_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1.md"
DEFAULT_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1.json"


def resolve_environment(path: pathlib.Path) -> tuple[pathlib.Path, tempfile.TemporaryDirectory[str] | None]:
    path = path.expanduser().resolve()
    if path.is_dir():
        return locate_base_root(path), None
    holder = tempfile.TemporaryDirectory(prefix="m26-behavioral-v8-")
    try:
        root = _safe_extract(path, pathlib.Path(holder.name))
    except Exception:
        holder.cleanup()
        raise
    return root, holder


def command_build(args: argparse.Namespace) -> int:
    root, holder = resolve_environment(args.input_env)
    try:
        prompt = args.prompt.read_text(encoding="utf-8")
        schema = read_json(args.schema)
        manifest = build_behavioral_environment(
            root,
            args.output_env,
            prompt_text=prompt,
            output_schema=schema,
        )
        print(json.dumps({"status": manifest["status"], "output": str(args.output_env.resolve()), "manifest": manifest}, ensure_ascii=False))
        return 0
    finally:
        if holder is not None:
            holder.cleanup()


def command_validate(args: argparse.Namespace) -> int:
    root, holder = resolve_environment(args.environment)
    try:
        manifest = validate_behavioral_environment(root)
        print(json.dumps({"status": "PASS_BEHAVIORAL_MIND_V8_VALIDATED", "manifest": manifest}, ensure_ascii=False))
        return 0
    finally:
        if holder is not None:
            holder.cleanup()


def command_audit(args: argparse.Namespace) -> int:
    report = audit_run(args.run, expected_rows=args.expected_rows)
    if args.output:
        write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["pilot_pass"] else 2


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="create a Behavioral Mind V8 overlay from an existing named environment")
    build.add_argument("--input-env", type=pathlib.Path, required=True)
    build.add_argument("--output-env", type=pathlib.Path, required=True)
    build.add_argument("--prompt", type=pathlib.Path, default=DEFAULT_PROMPT)
    build.add_argument("--schema", type=pathlib.Path, default=DEFAULT_SCHEMA)
    build.set_defaults(func=command_build)

    validate = sub.add_parser("validate", help="validate an extracted Behavioral Mind V8 environment")
    validate.add_argument("--environment", type=pathlib.Path, required=True)
    validate.set_defaults(func=command_validate)

    audit = sub.add_parser("audit", help="run Behavioral Realism gates on a small model run")
    audit.add_argument("--run", type=pathlib.Path, required=True)
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
    except (BehavioralEnvironmentError, BehavioralRealismError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

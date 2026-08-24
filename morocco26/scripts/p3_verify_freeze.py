#!/usr/bin/env python3
from __future__ import annotations

"""Freeze verification for the P3 remediation.

    --manifest v9                 the seventeen frozen V9 payload files are byte-identical
    --manifest v9_1               the V9.1 remediation files match their manifest
    --labour-template-must-fail   the shipped 2026 labour context is a template, not a source
    --rehash v9_1                 recompute the V9.1 manifest hashes after an intentional change

A freeze manifest that nobody re-checks is a comment. This runs on every push to
the branch, with no path filter.
"""

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
MANIFESTS = {
    "v9": BASE / "FREEZE_MANIFEST_V9_EMPIRICAL_MIND.json",
    "v9_1": BASE / "FREEZE_MANIFEST_V9_1_P3_REMEDIATION.json",
}
LABOUR_TEMPLATE = (
    REPO_ROOT
    / "morocco26"
    / "data"
    / "goal100"
    / "agent_society_v2"
    / "LABOUR_CONTEXT_2026_TEMPLATE.json"
)
PASS_LABEL = {"v9": "PASS_V9_FROZEN_FILES_UNCHANGED", "v9_1": "PASS_V9_1_REMEDIATION_FILES_UNCHANGED"}


def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return list(manifest.get("frozen_files_excluding_this_manifest") or [])


def verify(name: str) -> int:
    manifest = read_json(MANIFESTS[name])
    failures = []
    for row in rows(manifest):
        path = REPO_ROOT / row["path"]
        if not path.is_file():
            failures.append({"path": row["path"], "reason": "MISSING"})
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            failures.append({"path": row["path"], "expected": row["sha256"], "actual": digest})
    if failures:
        print(json.dumps({"status": "FROZEN_FILES_CHANGED", "failures": failures}, indent=2))
        return 1
    print(f"{PASS_LABEL[name]} files={len(rows(manifest))}")
    return 0


def rehash(name: str) -> int:
    path = MANIFESTS[name]
    manifest = read_json(path)
    manifest["frozen_files_excluding_this_manifest"] = [
        {
            "path": row["path"],
            "bytes": len((REPO_ROOT / row["path"]).read_bytes()),
            "sha256": hashlib.sha256((REPO_ROOT / row["path"]).read_bytes()).hexdigest(),
        }
        for row in rows(manifest)
    ]
    path.write_bytes(
        (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    )
    print(f"rehashed {len(rows(manifest))} files in {path.name}")
    return 0


def labour_template_must_fail() -> int:
    from morocco26.agent_society_v4.current_population_2026_v1 import (  # noqa: E402
        CurrentPopulationError,
        validate_labour_context,
    )

    try:
        validate_labour_context(read_json(LABOUR_TEMPLATE), snapshot_date="2026-08-24")
    except CurrentPopulationError as exc:
        print(f"PASS_LABOUR_CONTEXT_TEMPLATE_IS_NOT_A_SOURCE ({exc})")
        return 0
    print("the shipped labour template validated; a template must never pass for a source")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", choices=sorted(MANIFESTS))
    ap.add_argument("--rehash", choices=sorted(MANIFESTS))
    ap.add_argument("--labour-template-must-fail", action="store_true")
    args = ap.parse_args(argv)
    if args.rehash:
        return rehash(args.rehash)
    if args.manifest:
        return verify(args.manifest)
    if args.labour_template_must_fail:
        return labour_template_must_fail()
    ap.error("choose --manifest, --rehash or --labour-template-must-fail")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

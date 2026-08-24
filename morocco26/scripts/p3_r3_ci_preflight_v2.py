#!/usr/bin/env python3
from __future__ import annotations

"""Fail-closed R3 execution authorization bound to an actual GitHub Actions run.

`p3_r3_local_pilot.py build-arms` makes zero model calls and records an
operator-supplied CI conclusion. That is adequate for preparing arms, but not
for authorizing the first model output on an unprotected branch. This preflight
fetches the GitHub Actions run by numeric run_id and verifies the run itself:

* exact repository
* exact branch
* exact local git HEAD
* remediation-freeze workflow path
* completed + success
* clean local working tree

The resulting JSON is the execution evidence to freeze beside R3 outputs.
"""

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Mapping, Sequence

DEFAULT_REPO = "SmokeSol/Elections26"
DEFAULT_BRANCH = "morocco26-agent-society-v2-front-vote-llm"
EXPECTED_WORKFLOW_PATH = ".github/workflows/morocco26-p3-remediation-gates.yml"
ALLOWED_EVENTS = {"push", "workflow_dispatch"}


class R3CIPreflightError(RuntimeError):
    pass


def git(repo_root: pathlib.Path, *args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise R3CIPreflightError(process.stderr.strip() or f"git {' '.join(args)} failed")
    return process.stdout.strip()


def local_state(repo_root: pathlib.Path) -> tuple[str, bool]:
    head = git(repo_root, "rev-parse", "HEAD").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise R3CIPreflightError("local HEAD is not an exact 40-character SHA")
    clean = not bool(git(repo_root, "status", "--porcelain"))
    return head, clean


def fetch_run(repository: str, run_id: int) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/actions/runs/{int(run_id)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Morocco26-Agent-Society-R3-Preflight/2.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise R3CIPreflightError(f"cannot fetch GitHub Actions run {run_id}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise R3CIPreflightError("GitHub Actions response is not an object")
    return dict(value)


def validate_run(
    run: Mapping[str, Any],
    *,
    repository: str,
    branch: str,
    expected_head: str,
) -> dict[str, Any]:
    repo_full_name = str((run.get("repository") or {}).get("full_name") or "")
    observed = {
        "run_id": int(run.get("id") or 0),
        "repository": repo_full_name,
        "head_branch": str(run.get("head_branch") or ""),
        "head_sha": str(run.get("head_sha") or "").lower(),
        "workflow_path": str(run.get("path") or ""),
        "workflow_name": str(run.get("name") or ""),
        "event": str(run.get("event") or ""),
        "status": str(run.get("status") or ""),
        "conclusion": str(run.get("conclusion") or ""),
        "html_url": str(run.get("html_url") or ""),
        "run_attempt": int(run.get("run_attempt") or 0),
    }
    checks = {
        "repository_exact": observed["repository"] == repository,
        "branch_exact": observed["head_branch"] == branch,
        "head_sha_exact": observed["head_sha"] == expected_head,
        "workflow_exact": observed["workflow_path"] == EXPECTED_WORKFLOW_PATH,
        "event_allowed": observed["event"] in ALLOWED_EVENTS,
        "completed": observed["status"] == "completed",
        "success": observed["conclusion"] == "success",
        "run_id_present": observed["run_id"] > 0,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        raise R3CIPreflightError(f"CI run does not authorize R3: {failed}; observed={observed}")
    return {"observed": observed, "checks": checks}


def write_json(path: pathlib.Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--run-id", required=True, type=int)
    result.add_argument("--repo", default=DEFAULT_REPO)
    result.add_argument("--branch", default=DEFAULT_BRANCH)
    result.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path.cwd())
    result.add_argument("--expected-head")
    result.add_argument("--output", required=True, type=pathlib.Path)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    repo_root = args.repo_root.expanduser().resolve()
    local_head, clean = local_state(repo_root)
    if not clean:
        raise R3CIPreflightError("working tree is dirty; R3 execution is forbidden")
    expected_head = str(args.expected_head or local_head).lower()
    if expected_head != local_head:
        raise R3CIPreflightError(
            f"--expected-head {expected_head} differs from local HEAD {local_head}"
        )
    run = fetch_run(args.repo, args.run_id)
    result = validate_run(
        run,
        repository=args.repo,
        branch=args.branch,
        expected_head=expected_head,
    )
    authorization = {
        "schema_version": "ATLAS_P3_R3_CI_EXECUTION_AUTHORIZATION_V2",
        "status": "PASS_EXACT_HEAD_CI_BOUND",
        "local_git_head": local_head,
        "working_tree_clean": True,
        "repository": args.repo,
        "branch": args.branch,
        "expected_workflow_path": EXPECTED_WORKFLOW_PATH,
        **result,
    }
    write_json(args.output, authorization)
    print(json.dumps(authorization, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (R3CIPreflightError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

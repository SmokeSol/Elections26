#!/usr/bin/env python3
from __future__ import annotations

"""Fetch the HCP source microdata, completely, and prove it.

The inline shell fetch could not tell a truncated download from upstream data
that had genuinely changed: both surfaced later as a sha256 mismatch, and an
arbitrary size floor let a partial 200 MB file through. This fetcher checks the
two things separately, per file:

    received bytes == Content-Length      the transfer finished
    sha256 == the recorded digest         the bytes are the expected ones

A short read is retried, because that is a network problem. A complete file with
the wrong digest is not retried, because that is upstream having republished the
data, and the recorded digest is what the whole build lineage rests on.
"""

import argparse
import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
for candidate in (str(REPO_ROOT), str(SCRIPTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

SOURCES = {
    "ind": ("rgph_individual.dta", "https://www.rgph2014.hcp.ma/file/210749/"),
    "hh": ("rgph_household.dta", "https://www.rgph2014.hcp.ma/file/210748/"),
    "encdm": ("encdm_household.sav", "https://www.hcp.ma/file/231078/"),
}
USER_AGENT = "Mozilla/5.0 (ASV2 academic build)"
CHUNK = 1 << 20


class FetchError(RuntimeError):
    pass


BUILDER = SCRIPTS / "agent_society_v2_build_rich_populations.py"


def expected_digests() -> dict[str, str]:
    """The digests the historical builder already records.

    Read out of the builder's source rather than imported, so the fetcher does
    not drag in pyreadstat and stays runnable anywhere, while the builder file
    remains the single place those digests are declared.
    """
    import ast

    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EXPECTED" for target in node.targets
        ):
            declared = ast.literal_eval(node.value)
            missing = sorted(set(SOURCES) - set(declared))
            if missing:
                raise FetchError(f"{BUILDER.name} declares no digest for {missing}")
            return {key: str(declared[key]) for key in SOURCES}
    raise FetchError(f"no EXPECTED digest table found in {BUILDER.name}")


def fetch_one(url: str, destination: pathlib.Path, *, timeout: int) -> tuple[int, int | None, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(request, timeout=timeout) as response:
        declared = response.headers.get("Content-Length")
        declared_int = int(declared) if declared and declared.isdigit() else None
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                received += len(chunk)
    return received, declared_int, digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True, type=pathlib.Path)
    ap.add_argument("--attempts", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--report", type=pathlib.Path)
    args = ap.parse_args(argv)

    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    expected = expected_digests()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for key, (name, url) in SOURCES.items():
        destination = outdir / name
        row: dict[str, Any] = {"key": key, "file": name, "url": url, "expected_sha256": expected[key]}
        for attempt in range(1, args.attempts + 1):
            try:
                received, declared, digest = fetch_one(url, destination, timeout=args.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                row.update({"attempt": attempt, "error": f"{type(exc).__name__}: {exc}"})
                if attempt == args.attempts:
                    failures.append({**row, "reason": "TRANSFER_FAILED"})
                time.sleep(3 * attempt)
                continue
            complete = declared is None or received == declared
            row.update(
                {
                    "attempt": attempt,
                    "bytes": received,
                    "content_length": declared,
                    "complete": complete,
                    "sha256": digest,
                    "digest_match": digest == expected[key],
                }
            )
            if not complete:
                # A short read is a network problem: retry.
                print(f"{name}: {received} of {declared} bytes on attempt {attempt}", file=sys.stderr)
                if attempt == args.attempts:
                    failures.append({**row, "reason": "TRUNCATED_TRANSFER"})
                time.sleep(3 * attempt)
                continue
            if not row["digest_match"]:
                # A complete file with the wrong digest is upstream having
                # republished. Retrying cannot help and would hide it.
                failures.append({**row, "reason": "UPSTREAM_DIGEST_CHANGED"})
            break
        rows.append(row)
        print(
            f"{name}: {row.get('bytes')} bytes, complete={row.get('complete')}, "
            f"digest_match={row.get('digest_match')}"
        )

    report = {
        "status": "PASS_SOURCE_MICRODATA_FETCHED" if not failures else "FAIL_SOURCE_MICRODATA_FETCH",
        "outdir": str(outdir),
        "files": rows,
        "failures": failures,
        "interpretation": {
            "TRUNCATED_TRANSFER": "the network stopped short; safe to re-run",
            "UPSTREAM_DIGEST_CHANGED": (
                "the file downloaded completely but is not the one the build lineage records. "
                "Do not silently adopt the new bytes: decide explicitly whether the population "
                "may be rebuilt on a different source vintage, and record that decision."
            ),
        },
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FetchError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

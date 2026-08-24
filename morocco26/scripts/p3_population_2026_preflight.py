#!/usr/bin/env python3
from __future__ import annotations

"""Cheap preflight for the 2026 population build.

The full build reads three microdata files, then fits 92 raking problems with up
to 48 attempts each. When it dies on the ninetieth territory, the diagnosis has
cost half an hour and the log says `INSUFFICIENT_PARENT_POOL` once.

This runs first and answers the two questions that actually decide the build:

1. are the three source files the ones their sha256 says they are?
2. does every certified `prefecture_or_province` exist in the RGPH parent space,
   and with how many eligible rows behind it?

It reads only the columns needed for that, so it finishes in a couple of minutes
and prints the whole resolution table instead of the first failure.

Neither the frozen V1 builder nor the historical builders are modified.
"""

import argparse
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
for candidate in (str(REPO_ROOT), str(SCRIPTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from morocco26.agent_society_v4.current_population_2026_v1 import AGING_YEARS  # noqa: E402
from p3_ci_annotate import emit_error, emit_notice  # noqa: E402

MIN_POOL = 256


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ind", required=True, help="RGPH 2014 individual microdata (.dta)")
    ap.add_argument("--hh", help="RGPH 2014 household microdata (.dta), hash-checked only")
    ap.add_argument("--encdm", help="ENCDM 2014 household survey (.sav), hash-checked only")
    ap.add_argument("--min-pool", type=int, default=MIN_POOL)
    ap.add_argument("--output", type=pathlib.Path)
    args = ap.parse_args(argv)

    import pyreadstat

    import agent_society_v2_build_rich_populations as b
    import agent_society_v2_build_current_population_2026_geo_v2 as geo_v2

    # 1. the files must be what their recorded digests say
    source_hashes: dict[str, Any] = {}
    mismatches = []
    for key, path in (("ind", args.ind), ("hh", args.hh), ("encdm", args.encdm)):
        if not path:
            continue
        digest = b.sha(path)
        expected = b.EXPECTED[key]
        size = pathlib.Path(path).stat().st_size
        source_hashes[key] = {"sha256": digest, "expected": expected, "bytes": size, "match": digest == expected}
        if digest != expected:
            mismatches.append(
                {"file": key, "path": str(path), "bytes": size, "sha256": digest, "expected": expected}
            )
    if mismatches:
        report = {
            "status": "FAIL_SOURCE_MICRODATA_SHA256",
            "note": (
                "A download that returned an error page still writes a file. Check the byte size: "
                "a few kilobytes means the fetch failed, not that HCP republished the data."
            ),
            "mismatches": mismatches,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if args.output:
            write_json(args.output, report)
        emit_error(
            "source microdata digest mismatch",
            "; ".join(
                f"{row['file']}: {row['bytes']} bytes, sha256 {row['sha256'][:16]} != "
                f"expected {row['expected'][:16]}"
                for row in mismatches
            ),
        )
        return 2

    # 2. every certified parent must exist in the RGPH parent space
    geometry_index, geometry_sha256, _ = geo_v2.load_geometry()
    # b.age2014 reads AGE1, AGE5 and, for the within-band offset, pro, MEN_PRO
    # and NOR_MEN. Reading fewer columns than the helper touches is what made
    # run 32743858862 die with an uncaught AttributeError.
    frame, meta = pyreadstat.read_dta(
        args.ind,
        usecols=["pro", "MEN_PRO", "NOR_MEN", "AGE1", "AGE5"],
        apply_value_formats=False,
    )
    frame["age2014"] = [b.age2014(row) for row in frame.itertuples(index=False)]
    frame = frame[frame.age2014.notna()].copy()
    frame["age2014"] = frame.age2014.astype(int)
    labels = (meta.variable_value_labels or {}).get("pro", {})
    frame["pro_name"] = frame["pro"].map(labels).fillna(frame["pro"].astype(str))
    frame["pro_norm"] = frame.pro_name.map(b.norm)
    eligible = frame[frame.age2014 + AGING_YEARS >= 18]
    available = set(eligible.pro_norm.drop_duplicates())
    counts = eligible.pro_norm.value_counts().to_dict()

    rows = []
    for cid, row in sorted(geometry_index.items()):
        parent = str(row.get("prefecture_or_province") or "")
        resolved, mode = b.resolve_parent(parent, available)
        pool = int(counts.get(resolved, 0))
        rows.append(
            {
                "constituency_id": cid,
                "certified_parent": parent,
                "resolved_rgph_parent": resolved,
                "resolution_mode": mode,
                "eligible_rows": pool,
                "sufficient": pool >= args.min_pool,
            }
        )

    unresolved = [row for row in rows if row["resolution_mode"] == "UNRESOLVED"]
    insufficient = [row for row in rows if row["resolution_mode"] != "UNRESOLVED" and not row["sufficient"]]
    modes: dict[str, int] = {}
    for row in rows:
        modes[row["resolution_mode"]] = modes.get(row["resolution_mode"], 0) + 1

    report = {
        "status": "PASS_POPULATION_2026_PREFLIGHT"
        if not unresolved and not insufficient
        else "FAIL_POPULATION_2026_PREFLIGHT",
        "geometry_certificate_sha256": geometry_sha256,
        "territories": len(rows),
        "rgph_parent_space_size": len(available),
        "resolution_modes": dict(sorted(modes.items())),
        "min_pool_required": args.min_pool,
        "unresolved": unresolved,
        "insufficient_pool": insufficient,
        "source_hashes": source_hashes,
        "rows": rows,
    }
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "rows"},
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.output:
        write_json(args.output, report)
    if unresolved or insufficient:
        print(
            "\nThe certified parents below do not reach the RGPH microdata. "
            "Fix the mapping before spending a full build:",
            file=sys.stderr,
        )
        for row in (unresolved + insufficient)[:30]:
            print(
                f"  {row['constituency_id']:28s} {row['certified_parent']:24s} "
                f"-> {row['resolved_rgph_parent']:24s} {row['resolution_mode']:32s} "
                f"rows={row['eligible_rows']}",
                file=sys.stderr,
            )
        emit_error(
            "certified parents unreachable in the RGPH parent space",
            "; ".join(
                f"{row['constituency_id']} -> {row['certified_parent']} "
                f"({row['resolution_mode']}, rows={row['eligible_rows']})"
                for row in (unresolved + insufficient)[:20]
            ),
        )
        return 2
    emit_notice(
        "population 2026 preflight",
        f"{len(rows)} territories resolved, modes {report['resolution_modes']}, "
        f"parent space {len(available)}",
    )
    return 0


if __name__ == "__main__":
    from p3_ci_annotate import run_guarded

    raise SystemExit(run_guarded(main))

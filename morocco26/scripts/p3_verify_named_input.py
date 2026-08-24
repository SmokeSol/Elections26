#!/usr/bin/env python3
from __future__ import annotations

"""Bind the 2026 population build to published bytes and to a politically empty result.

    --named-input PATH              the bytes about to be built from must be the
                                    ones NAMED_INPUT_2026_LINEAGE_V1.json records
    --population-certificate PATH   the produced certificate must declare no
                                    electoral input and a certified geometry

Both checks fail closed. The first is what makes "how many candidates do we
have?" have one answer for the artifact the build actually consumes; the second
is what stops a politically loaded population from reaching R3.
"""

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
LINEAGE = (
    REPO_ROOT
    / "morocco26"
    / "data"
    / "goal100"
    / "agent_society_v2"
    / "NAMED_INPUT_2026_LINEAGE_V1.json"
)
REQUIRED_FALSE = (
    "historical_outcome_read",
    "prior_election_raking_dimension",
    "sealed_mapping_read",
    "atlas_prior_reinjected",
    "target_outcome_used",
    "dummy_unknown_marginal_used",
)
EXPECTED_TERRITORIES = 92


class NamedInputError(RuntimeError):
    pass


def read_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NamedInputError(f"cannot read JSON {path}: {exc}") from exc


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_named_input(path: pathlib.Path, *, override: str = "") -> int:
    lineage = read_json(LINEAGE)
    if not lineage.get("all_recorded_digests_agree"):
        raise NamedInputError("the named-input lineage does not agree with its bound certificates")
    digest = sha256_file(path)
    if override.strip():
        # An override is allowed, but it is never silent: it must announce that
        # it is not the snapshot the published certificates describe.
        print(
            json.dumps(
                {
                    "status": "OVERRIDE_NAMED_INPUT_NOT_THE_PUBLISHED_SNAPSHOT",
                    "path": str(path),
                    "sha256": digest,
                    "published_sha256": lineage["sha256"],
                    "matches_published": digest == lineage["sha256"],
                    "consequence": (
                        "The R0 certificate and the ballot-cell census describe the published "
                        "snapshot. Republish both before using this population downstream."
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if digest != lineage["sha256"]:
        raise NamedInputError(
            f"named input sha256 {digest} != published {lineage['sha256']}; "
            "the build would not be the artifact the certificates describe"
        )
    print(
        json.dumps(
            {
                "status": "PASS_NAMED_INPUT_MATCHES_PUBLISHED_LINEAGE",
                "path": str(pathlib.Path(path)),
                "sha256": digest,
                "snapshot_known_as_of": lineage.get("snapshot_known_as_of"),
                "bound_certificates": [row["path"] for row in lineage["bound_certificates"]],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def verify_population_certificate(path: pathlib.Path) -> int:
    certificate = read_json(path)
    bad = [name for name in REQUIRED_FALSE if certificate.get(name) is not False]
    if bad:
        raise NamedInputError(f"population certificate does not declare a politically empty build: {bad}")
    if certificate.get("political_memory_population_source") != "NONE":
        raise NamedInputError("political_memory_population_source is not NONE")
    geometry = certificate.get("geometry_certificate") or {}
    if geometry.get("gate") != "PASS" or geometry.get("territories") != EXPECTED_TERRITORIES:
        raise NamedInputError(f"geometry lineage failed: {geometry}")
    source_hashes = certificate.get("source_hashes") or {}
    if source_hashes.get("geometry_2026_certificate") != geometry.get("sha256"):
        raise NamedInputError("geometry source hash mismatch between lineage and certificate")
    boundary = certificate.get("demographic_projection_boundary") or {}
    if boundary.get("rgph2024_demographic_marginals_calibrated") is not False:
        raise NamedInputError("the demographic projection boundary is missing or overclaims")
    if not str(certificate.get("status") or "").startswith("PASS"):
        raise NamedInputError(f"certificate status {certificate.get('status')}: {certificate.get('gates')}")
    print(
        json.dumps(
            {
                "status": "PASS_CURRENT_VINTAGE_POPULATION_2026_V2",
                "territories": certificate.get("territories"),
                "failures": len(certificate.get("failures") or []),
                "geometry_certificate_sha256": geometry.get("sha256"),
                "scale_or_forecast_population_use": boundary.get("scale_or_forecast_population_use"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--named-input", type=pathlib.Path)
    ap.add_argument("--allow-override", default="")
    ap.add_argument("--population-certificate", type=pathlib.Path)
    args = ap.parse_args(argv)
    if args.named_input:
        return verify_named_input(args.named_input, override=args.allow_override)
    if args.population_certificate:
        return verify_population_certificate(args.population_certificate)
    ap.error("choose --named-input or --population-certificate")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (NamedInputError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

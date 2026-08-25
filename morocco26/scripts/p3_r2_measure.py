#!/usr/bin/env python3
from __future__ import annotations

"""R2 on the real population: bridge, certify, overlay V9.1, and report the count.

Everything downstream of the population build has so far been measured on a
shape-faithful synthetic fixture, which gave 30 of 121 dimensions populated per
voter. That number was always labelled as a fixture result. This replaces it
with the observed one.

The Actions artifact holding the population needs a signed-in session to
download, so the measurement runs in the same job that produced it and reports
through check-run annotations, which are public.

One honest expectation to set before reading the result: there is no 2026
attitude overlay. The historical overlay builder derives stratum posteriors from
Afrobarometer R6 and R8 for 2016 and 2021, and nothing equivalent exists for the
current vintage. So `survey_stratum` will be empty and the twelve
SURVEY_STRATUM_PRIOR dimensions the fixture carried will be UNKNOWN here. The
observed figure should be lower than 30, and that is the correct answer rather
than a regression.
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

from morocco26.agent_society_v4.behavioral_environment_v8_1 import (  # noqa: E402
    build_behavioral_environment_v8_1,
)
from morocco26.agent_society_v4.empirical_environment_v9_1 import (  # noqa: E402
    build_empirical_environment_v9_1,
)
from morocco26.agent_society_v4.p3_data_layers_v1 import (  # noqa: E402
    build_cell_census,
    build_certificate,
    sha256_json,
)
from morocco26.agent_society_v4.rich_named_bridge_v1 import sha256_file  # noqa: E402
from morocco26.agent_society_v4.rich_named_bridge_v1 import (  # noqa: E402
    bridge_rich_population,
    read_json,
    read_jsonl,
)
from p3_ci_annotate import emit_error, emit_notice, run_guarded  # noqa: E402

BASE = REPO_ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"
LOCAL_PROMPT = BASE / "BEHAVIORAL_VOTER_PROMPT_V1_1_LOCAL_ONLY.md"
LOCAL_SCHEMA = BASE / "BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1_1_LOCAL_ONLY.json"
DIMENSIONS = BASE / "EMPIRICAL_MIND_DIMENSIONS_V1.json"
AMENDMENT = BASE / "EMPIRICAL_MIND_DIMENSIONS_V9_1_AMENDMENT.json"
SOURCES = BASE / "EMPIRICAL_SOURCE_REGISTRY_V1.json"
ADDENDUM = BASE / "EMPIRICAL_MIND_PROMPT_ADDENDUM_V1_1.md"
COVERAGE = REPO_ROOT / "morocco26" / "data" / "candidate_coverage_2026.json"


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--named-input", required=True, type=pathlib.Path)
    ap.add_argument("--rich-population", required=True, type=pathlib.Path)
    ap.add_argument("--attitude-overlay", type=pathlib.Path)
    ap.add_argument("--territory", default="ain-chock")
    ap.add_argument("--voters-per-territory", type=int, default=32)
    ap.add_argument("--snapshot-date", default="2026-08-24")
    ap.add_argument("--outdir", required=True, type=pathlib.Path)
    args = ap.parse_args(argv)

    outdir = args.outdir.expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    named_input = read_json(args.named_input)
    population = read_json(args.rich_population)
    overlay = read_jsonl(args.attitude_overlay) if args.attitude_overlay else []

    bridged, bridge_certificate = bridge_rich_population(
        named_input=named_input,
        rich_population=population,
        attitude_overlay_rows=overlay,
        voters_per_territory=args.voters_per_territory,
        only_territories=[args.territory],
    )
    write_json(outdir / "named_input_rich_2026.json", bridged)
    write_json(outdir / "rich_named_bridge_certificate.json", bridge_certificate)

    census = build_cell_census(named_input=bridged, named_input_sha256=sha256_json(bridged))
    certificate = build_certificate(
        named_input=bridged,
        named_input_sha256=sha256_json(bridged),
        cell_census=census,
        cell_census_path="derived from the bridged input",
        coverage_snapshot=read_json(COVERAGE) if COVERAGE.is_file() else None,
        coverage_path=str(COVERAGE.relative_to(REPO_ROOT)).replace("\\", "/"),
        rich_population_certificate={"status": "PASS"},
        environment_id=f"M26_P3_R2_{args.territory.upper()}",
    )
    write_json(outdir / "p3_data_layer_certificate_rich.json", certificate)

    scripts = str(SCRIPTS)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import three_regime_core as trc  # noqa: E402

    named_root = outdir / "named_env"
    trc.build_named_environment(bridged, named_root)
    v8_1 = build_behavioral_environment_v8_1(
        named_root,
        outdir / "v8_1",
        prompt_text=LOCAL_PROMPT.read_text(encoding="utf-8"),
        output_schema=read_json(LOCAL_SCHEMA),
        certificate=certificate,
    )
    v9_1 = build_empirical_environment_v9_1(
        v8_root=outdir / "v8_1",
        output_root=outdir / "v9_1",
        base_dimension_registry=read_json(DIMENSIONS),
        amendment=read_json(AMENDMENT),
        source_registry=read_json(SOURCES),
        prior_pack=None,
        snapshot_date=args.snapshot_date,
        prompt_addendum_text=ADDENDUM.read_text(encoding="utf-8"),
    )

    audit_index = read_json(outdir / "v9_1" / "empirical_mind_audit_index.json")
    independent = [
        int(row["mind_audit"]["independent_evidence_dimensions"]) for row in audit_index["voters"]
    ]
    mean_independent = sum(independent) / max(1, len(independent))
    sample = bridged["voter_population"]["batches"][0]["voters"][0]

    summary = {
        "schema_version": "ATLAS_P3_R2_MEASUREMENT_V1",
        "territory": args.territory,
        "population_id": population.get("population_id"),
        "voters": v9_1["voter_rows"],
        "layer_states": certificate["layer_states"],
        "individual_fields_per_voter": bridge_certificate["individual_fields_per_voter"],
        "household_fields_per_voter": bridge_certificate["household_fields_per_voter"],
        "survey_stratum_fields_per_voter": bridge_certificate["survey_stratum_fields_per_voter"],
        "territory_context_fields_per_voter": bridge_certificate["territory_context_fields_per_voter"],
        "attitude_overlay_rows_matched": bridge_certificate["attitude_overlay_rows_matched"],
        "prior_election_anchors_dropped": bridge_certificate["prior_election_anchors_dropped"],
        "dimensions_per_voter": v9_1["dimensions_per_voter"],
        "mean_populated_dimensions_per_voter": v9_1["mean_populated_dimensions_per_voter"],
        "mean_independent_evidence_dimensions_per_voter": round(mean_independent, 6),
        "epistemic_totals": v9_1["epistemic_totals"],
        "population_prior_relabelled_as_individual_fact": v9_1[
            "population_prior_relabelled_as_individual_fact"
        ],
        "ballots_simulated": v8_1["ballots_simulated"],
        "regional_surface_status": v8_1["regional_surface_status"],
        "fixture_figure_superseded": {
            "fixture": "30 of 121 populated, on a shape-faithful synthetic population",
            "note": "kept only so the two numbers are never confused",
        },
        "no_attitude_overlay_for_2026": not overlay,
        "sample_voter_keys": sorted(sample),
        # Published so a freeze revision can name the produced bytes rather than
        # only the inputs that made them. The population artifact needs a
        # signed-in session to download; this digest does not.
        "produced_population_sha256": sha256_file(args.rich_population),
        "produced_population_bytes": args.rich_population.stat().st_size,
        "bridged_named_input_sha256": sha256_json(bridged),
        "bridge_certificate_sha256": sha256_json(bridge_certificate),
        "data_layer_certificate_sha256": sha256_json(certificate),
    }
    write_json(outdir / "p3_r2_measurement.json", summary)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))

    if summary["population_prior_relabelled_as_individual_fact"]:
        emit_error("EM2 violated on the real population", "a stratum prior surfaced as an individual fact")
        return 2
    populated = [
        int(row["mind_audit"]["populated_dimensions"]) for row in audit_index["voters"]
    ]
    totals = summary["epistemic_totals"]
    lines = [
        f"{summary['voters']} voters in {args.territory}, from {summary['population_id']}.",
        "",
        f"POPULATED  {summary['mean_populated_dimensions_per_voter']} of "
        f"{summary['dimensions_per_voter']} per voter "
        f"(min {min(populated)}, max {max(populated)}); "
        f"independent evidence {summary['mean_independent_evidence_dimensions_per_voter']}.",
        "This supersedes the fixture's 30 of 121. The fixture carried an "
        "Afrobarometer attitude overlay; no equivalent exists for the current "
        "vintage, so the twelve SURVEY_STRATUM_PRIOR dimensions have no source "
        "here. A missing layer lowers the count rather than being filled in.",
        "",
        "LAYERS PER VOTER  "
        f"individual {summary['individual_fields_per_voter']}, "
        f"household {summary['household_fields_per_voter']}, "
        f"survey stratum {summary['survey_stratum_fields_per_voter']}, "
        f"territory context {summary['territory_context_fields_per_voter']}. "
        f"Prior-election anchors dropped: {summary['prior_election_anchors_dropped']}.",
        "",
        "EPISTEMIC STATUS  "
        + ", ".join(f"{key} {value}" for key, value in sorted(totals.items()) if value),
        "",
        "DATA LAYERS  "
        + ", ".join(f"{key} {value}" for key, value in sorted(summary["layer_states"].items())),
        f"Ballots simulated: {summary['ballots_simulated']}. "
        f"Regional surface: {summary['regional_surface_status']}. "
        "EM2 holds: no stratum prior surfaced as an individual fact.",
        "",
        "DIGESTS  population "
        f"{summary['produced_population_sha256']} "
        f"({summary['produced_population_bytes']} bytes); "
        f"bridged named input {summary['bridged_named_input_sha256']}; "
        f"data-layer certificate {summary['data_layer_certificate_sha256']}.",
    ]
    emit_notice("R2 measured on the real 2026 population", "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_guarded(main))

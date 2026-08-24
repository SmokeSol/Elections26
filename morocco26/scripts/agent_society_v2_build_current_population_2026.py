#!/usr/bin/env python3
from __future__ import annotations

"""Build the current-vintage 2026 rich population - no electoral raking dimension.

The historical builder is not modified. It is imported for its primitives
(normalisation, parent resolution, margins, IPF, record construction) and driven
with a raking problem that contains only demographic and socio-economic
dimensions.

    targets = age_band x sex x urban_rural x education_band x activity_status

`prior_vote_or_abstention` is not a target, not a column and not a dummy
`UNKNOWN = 100%` marginal: it is absent from the problem. Political memory then
stays UNKNOWN by contract downstream.

The heavy dependencies (pandas, numpy, pyreadstat) are imported inside main, so
the guards and the certificate stay importable and testable without them.
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

from morocco26.agent_society_v4.current_population_2026_v1 import (  # noqa: E402
    AGING_YEARS,
    POPULATION_SCHEMA,
    RAKING_DIMENSIONS,
    TARGET_YEAR,
    CurrentPopulationError,
    assert_no_electoral_raking,
    build_population_certificate,
    sha256_json,
    strip_political_memory,
    territory_specs_from_named_input,
    validate_labour_context,
)

ARCHETYPES_PER_CONSTITUENCY = 256
IPF_ATTEMPTS = 48
MIN_ESS = 128.0
MAX_WEIGHT = 0.05
MAX_RAKING_ERROR = 5e-6

# The historical builder ages the RGPH 2014 frame by +2 for 2016 and +7
# otherwise, hard-coded in build_hh_comp and build_record. Neither is edited, so
# 2026 compensates explicitly: the household composition is recomputed with the
# right offset, and the household-head age is pre-shifted so the builder's own
# +7 lands on +12.
HEAD_AGE_COMPENSATION = AGING_YEARS - 7


def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    path = pathlib.Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ind", required=True, help="RGPH 2014 individual microdata (.dta)")
    ap.add_argument("--hh", required=True, help="RGPH 2014 household microdata (.dta)")
    ap.add_argument("--encdm", required=True, help="ENCDM 2014 household survey (.sav)")
    ap.add_argument("--named-input", required=True, type=pathlib.Path)
    ap.add_argument("--labour-context", required=True, type=pathlib.Path)
    ap.add_argument("--snapshot-date", required=True)
    ap.add_argument("--outdir", required=True, type=pathlib.Path)
    ap.add_argument("--archetypes", type=int, default=ARCHETYPES_PER_CONSTITUENCY)
    args = ap.parse_args(argv)

    import numpy as np
    import pandas as pd
    import pyreadstat

    import agent_society_v2_build_rich_populations as b
    import agent_society_v2_build_rich_populations_v2 as v2

    labour_report = validate_labour_context(
        read_json(args.labour_context), snapshot_date=args.snapshot_date
    )
    # The historical builder reads LABOR[year] for the labour tilt and for the
    # target_year_* context fields. 2026 is supplied by the operator, sourced.
    b.LABOR[TARGET_YEAR] = {
        "unemployment": labour_report["rates"].get("unemployment"),
        "urban_unemployment": labour_report["rates"].get("urban_unemployment"),
        "rural_unemployment": labour_report["rates"].get("rural_unemployment"),
        "youth_unemployment": labour_report["rates"].get("youth_unemployment"),
        "female_unemployment": labour_report["rates"].get("female_unemployment"),
        "underemployment": labour_report["rates"].get("underemployment"),
        "activity": labour_report["rates"].get("activity"),
    }

    named_input = read_json(args.named_input)
    specs = territory_specs_from_named_input(named_input)
    out = pathlib.Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    source_hashes = {}
    for key, path in (("ind", args.ind), ("hh", args.hh), ("encdm", args.encdm)):
        digest = b.sha(path)
        if digest != v2.EXPECTED[key]:
            raise CurrentPopulationError(f"{key} sha256 mismatch: {digest}")
        source_hashes[key] = digest

    print("loading RGPH individual microdata...")
    ind, im = pyreadstat.read_dta(args.ind, usecols=b.IND_COLS, apply_value_formats=False)
    ind["age2014"] = [b.age2014(row) for row in ind.itertuples(index=False)]
    ind = ind[ind.age2014.notna()].copy()
    ind["age2014"] = ind.age2014.astype(int)
    labels = (im.variable_value_labels or {}).get("pro", {})
    ind["pro_name"] = ind["pro"].map(labels).fillna(ind["pro"].astype(str))
    ind["pro_norm"] = ind.pro_name.map(b.norm)

    head = (
        ind[pd.to_numeric(ind.LIEN_CM, errors="coerce") == 0][
            ["pro", "MEN_PRO", "sexe", "age2014", "NIV_ET_AGR", "TY_ACT"]
        ]
        .copy()
        .drop_duplicates(["pro", "MEN_PRO"])
        .rename(
            columns={
                "sexe": "head_sex",
                "age2014": "head_age2014",
                "NIV_ET_AGR": "head_edu",
                "TY_ACT": "head_activity",
            }
        )
        .set_index(["pro", "MEN_PRO"])
    )
    # build_hh_comp hard-codes the 2016/2021 offsets, so 2026 composes its own.
    ages = ind["age2014"].to_numpy() + AGING_YEARS
    composition_frame = ind[["pro", "MEN_PRO"]].copy()
    composition_frame["child"] = (ages < 18).astype("int8")
    composition_frame["adult"] = (ages >= 18).astype("int8")
    composition_frame["elderly"] = (ages >= 65).astype("int8")
    activity_codes = pd.to_numeric(ind["TY_ACT"], errors="coerce")
    composition_frame["worker"] = (activity_codes == 0).astype("int8")
    composition_frame["unemployed"] = activity_codes.isin([1, 2]).astype("int8")
    composition_frame["student"] = (activity_codes == 4).astype("int8")
    comp = composition_frame.groupby(["pro", "MEN_PRO"], sort=False)[
        ["child", "adult", "elderly", "worker", "unemployed", "student"]
    ].sum()
    head = head.copy()
    head["head_age2014"] = pd.to_numeric(head["head_age2014"], errors="coerce") + HEAD_AGE_COMPENSATION

    print("loading household and ENCDM...")
    hh, hm = pyreadstat.read_dta(args.hh, usecols=b.HH_COLS, apply_value_formats=False)
    hh = hh.drop_duplicates(["pro", "MEN_PRO"]).set_index(["pro", "MEN_PRO"])
    enc, _ = pyreadstat.read_sav(args.encdm, usecols=b.ENCDM_COLS, apply_value_formats=False)
    eidx = b.donor_index_encdm(enc)

    ind["age_target"] = ind.age2014 + AGING_YEARS
    ind["age_band"] = ind.age_target.map(b.age_band)
    ind["sex"] = ind.sexe.map(b.sex_band)
    ind["urban_rural"] = ind.mil.map(b.ur_band)
    ind["education_band"] = ind.NIV_ET_AGR.map(b.edu_band)
    ind["activity_status"] = ind.TY_ACT.map(b.act_band)
    eligible = ind[ind.age_target >= 18].copy()

    base_rates = {}
    for milieu in ("URBAN", "RURAL", "ALL"):
        frame = eligible if milieu == "ALL" else eligible[eligible.urban_rural == milieu]
        weights = pd.to_numeric(frame.pds, errors="coerce").fillna(1).clip(lower=0).to_numpy()
        activity = frame.activity_status.to_numpy()
        denominator = weights[np.isin(activity, ["ACTIVE_EMPLOYED", "UNEMPLOYED"])].sum()
        numerator = weights[activity == "UNEMPLOYED"].sum()
        base_rates[milieu] = float(numerator / denominator) if denominator else 0.1

    available = set(eligible.pro_norm.drop_duplicates())
    territories: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    n = args.archetypes

    for index, spec in enumerate(specs):
        cid = spec["constituency_id"]
        parent, geo0 = b.resolve_parent(spec["prefecture_or_province"], available)
        pool = eligible[eligible.pro_norm == parent]
        if len(pool) < n:
            failures.append(
                {"constituency_id": cid, "reason": "INSUFFICIENT_PARENT_POOL", "parent": parent, "rows": len(pool)}
            )
            continue
        person_weights = pd.to_numeric(pool.pds, errors="coerce").fillna(1).clip(lower=1e-6).to_numpy(float)
        multiplier = np.array(
            [
                b.labour_multiplier(activity, milieu, TARGET_YEAR, base_rates)
                for activity, milieu in zip(pool.activity_status, pool.urban_rural)
            ]
        )
        sample_weights = person_weights * multiplier

        # The raking problem: demographic margins only, checked before use.
        targets = {
            key: value
            for key, value in b.margins(pool, sample_weights).items()
            if key in RAKING_DIMENSIONS
        }
        assert_no_electoral_raking(targets)

        best = None
        for attempt in range(IPF_ATTEMPTS):
            rng = np.random.default_rng(b.SEED + TARGET_YEAR * 100000 + index * 101 + attempt)
            picked = rng.choice(len(pool), n, replace=False, p=sample_weights / sample_weights.sum())
            rows = pool.iloc[picked].copy().reset_index(drop=True)
            weights, error = b.ipf(rows, targets)
            if weights is None:
                continue
            ess = float(1 / (weights * weights).sum())
            max_weight = float(weights.max())
            candidate = (error, -ess, max_weight, rows, weights)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
            if error < 2e-8 and ess >= MIN_ESS and max_weight <= MAX_WEIGHT:
                break
        if best is None or best[0] > MAX_RAKING_ERROR or -best[1] < MIN_ESS or best[2] > MAX_WEIGHT:
            failures.append(
                {
                    "constituency_id": cid,
                    "reason": "IPF_GATE",
                    "best": None
                    if best is None
                    else {"err": best[0], "ess": -best[1], "max_weight": best[2]},
                }
            )
            continue

        error, negative_ess, max_weight, rows, weights = best
        records = []
        for position, person in rows.iterrows():
            key = (person["pro"], person["MEN_PRO"])
            household = hh.loc[key] if key in hh.index else pd.Series(dtype=object)
            composition = comp.loc[key] if key in comp.index else pd.Series(dtype=object)
            household_head = head.loc[key] if key in head.index else pd.Series(dtype=object)
            # build_record reads person["prior_vote_or_abstention"]; the 2026
            # problem has no such column, so a null placeholder is supplied and
            # the field is stripped from the record immediately afterwards.
            person = person.copy()
            person["prior_vote_or_abstention"] = None
            # Compensates the builder's hard-coded +7 on the fallback head age.
            person["age2014"] = int(person["age2014"]) + HEAD_AGE_COMPENSATION
            record = v2.build_record(
                person,
                household,
                composition,
                household_head,
                im,
                hm,
                weights[position],
                TARGET_YEAR,
                enc,
                eidx,
                index,
            )
            record = strip_political_memory(record)
            record["archetype_id"] = f"R{position + 1:03d}"
            records.append(record)

        geography = "PARENT_PROXY_SPLIT_CONSTITUENCY" if cid in b.SPLIT else geo0
        safe = [key for key in records[0] if key not in ("archetype_id", "weight")]
        territories.append(
            {
                "constituency_id": cid,
                "constituency_name": spec["constituency_name"],
                "prefecture_or_province": spec["prefecture_or_province"],
                "region_name": spec.get("region_name"),
                "geography_confidence": geography,
                "target_core_marginals": targets,
                "quality": {
                    "raking_max_abs_error": float(error),
                    "effective_archetype_count": float(-negative_ess),
                    "max_single_archetype_weight": float(max_weight),
                    "geography_confidence": geography,
                    "observed_or_derived_voter_dimensions": len(safe),
                },
                "archetypes": records,
            }
        )
        print(cid, "ok", len(records), "archetypes")

    population = {
        "schema_version": POPULATION_SCHEMA,
        "population_id": f"M26-ASV2-CURRENT-{TARGET_YEAR}-POP-V1",
        "experiment_id": "M26-AGENT-SOCIETY-V2-001",
        "target_election_year": TARGET_YEAR,
        "regime": "P3_CURRENT_VINTAGE_2026",
        "status": "PASS" if not failures and territories else "FAIL",
        "archetypes_per_constituency": n,
        "raking_dimensions": list(RAKING_DIMENSIONS),
        "prior_election_raking_dimension": False,
        "political_memory_population_source": "NONE",
        "target_outcome_used": False,
        "real_llm_outputs_used": False,
        "source_hashes": source_hashes,
        "target_year_update": {"aging_years": AGING_YEARS, "labor_context": b.LABOR[TARGET_YEAR]},
        "territories": territories,
        "failures": failures,
    }
    write_json(out / f"{TARGET_YEAR}_current_population_v1.json", population)

    certificate = build_population_certificate(
        territories=territories,
        failures=failures,
        archetypes_per_constituency=n,
        labour_report=labour_report,
        source_hashes=source_hashes,
        named_input_sha256=sha256_json(named_input),
        expected_territories=len(specs),
        safe_feature_count=(
            len([key for key in territories[0]["archetypes"][0] if key not in ("archetype_id", "weight")])
            if territories
            else None
        ),
    )
    write_json(out / "current_population_2026_certificate_v1.json", certificate)
    print(json.dumps(certificate["gates"], indent=2))
    print(certificate["status"])
    return 0 if certificate["status"].startswith("PASS") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CurrentPopulationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

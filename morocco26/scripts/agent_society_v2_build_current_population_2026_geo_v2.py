#!/usr/bin/env python3
from __future__ import annotations

"""Current-vintage 2026 population builder, geometry-bound wrapper (V2).

V1 correctly removes every electoral raking dimension, but derives the HCP
microdata parent from `territory_name`. That is not sufficient for split
constituencies whose electoral name does not contain its administrative parent
(e.g. Karia-Ghafsay -> Taounate, El Gharb -> Kenitra, Bzou-Ouaouizeght ->
Azilal). The repository already has a PASS geometry certificate with the exact
constituency_id -> prefecture_or_province relation.

This wrapper leaves both the historical builders and V1 untouched. It replaces
only V1's territory-spec resolver at runtime with the certified relation and
adds the geometry-certificate SHA256 to the population/certificate lineage.

A second boundary is made explicit rather than hidden: the person-level
microdata are RGPH 2014 aged by +12 years. HCP EMO2026 supplies current labour
context, but the five demographic raking marginals are not calibrated to RGPH
2024. That is sufficient for the paired R3 mechanism experiment because all
four cells use the identical population; it is NOT a final 2026
poststratification and is blocked for scale/forecast use until an RGPH2024 (or
equivalent) calibration is added.
"""

import hashlib
import json
import pathlib
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
for candidate in (str(REPO_ROOT), str(SCRIPTS)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import agent_society_v2_build_current_population_2026 as v1  # noqa: E402
from morocco26.agent_society_v4.current_population_2026_v1 import (  # noqa: E402
    AGING_YEARS,
    RGPH_REFERENCE_YEAR,
    CurrentPopulationError,
    normalize_place,
)
from p3_ci_annotate import emit_error, emit_notice  # noqa: E402

GEOMETRY_PATH = REPO_ROOT / "morocco26" / "data" / "goal100" / "geometry_2026_certificate.json"
EXPECTED_TERRITORIES = 92


def read_json(path: pathlib.Path) -> Any:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, value: Any) -> None:
    pathlib.Path(path).write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def demographic_projection_boundary() -> dict[str, Any]:
    return {
        "person_microdata_reference_year": RGPH_REFERENCE_YEAR,
        "deterministic_age_shift_years": AGING_YEARS,
        "rgph2024_demographic_marginals_calibrated": False,
        "hpc_current_labour_context_applied": True,
        "hcp_activity_rate_used_as_raking_target": False,
        "r3_paired_mechanism_use": "ALLOWED_IDENTICAL_POPULATION_ACROSS_ALL_2X2_CELLS",
        "scale_or_forecast_population_use": "BLOCKED_UNTIL_RGPH2024_OR_EQUIVALENT_POSTSTRATIFICATION",
        "reason": (
            "R3 identifies a within-population mechanism contrast, so current-population external "
            "representativeness is not the estimand. National/territorial forecast weighting is a "
            "different estimand and must not treat RGPH2014 aged by +12 as a final 2026 population."
        ),
    }


def load_geometry(path: pathlib.Path = GEOMETRY_PATH) -> tuple[dict[str, dict[str, Any]], str, dict[str, Any]]:
    value = read_json(path)
    if value.get("gate") != "PASS":
        raise CurrentPopulationError(f"2026 geometry certificate is not PASS: {value.get('gate')}")
    local = value.get("local") or {}
    rows = local.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_TERRITORIES:
        raise CurrentPopulationError(
            f"2026 geometry must contain {EXPECTED_TERRITORIES} local rows, got "
            f"{len(rows) if isinstance(rows, list) else 'non-list'}"
        )
    index: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise CurrentPopulationError("2026 geometry contains a non-object row")
        cid = str(raw.get("constituency_id") or "")
        parent = str(raw.get("prefecture_or_province") or "").strip()
        repo_name = str(raw.get("repo_name") or "").strip()
        if not cid or not parent or not repo_name or cid in index:
            raise CurrentPopulationError(f"invalid or duplicate 2026 geometry row: {cid!r}")
        index[cid] = dict(raw)
    if len(index) != EXPECTED_TERRITORIES:
        raise CurrentPopulationError("2026 geometry constituency ids are not unique")
    return index, sha256_file(path), value


def territory_specs_from_certified_geometry(
    named_input: Mapping[str, Any],
    *,
    geometry_index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    territories = named_input.get("territories") or []
    if not isinstance(territories, list) or len(territories) != EXPECTED_TERRITORIES:
        raise CurrentPopulationError(
            f"named input must contain {EXPECTED_TERRITORIES} territories for the 2026 population"
        )
    specs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for territory in territories:
        if not isinstance(territory, Mapping):
            raise CurrentPopulationError("named input contains a non-object territory")
        cid = str(territory.get("territory_id") or "")
        name = str(territory.get("territory_name") or "").strip()
        if not cid or not name or cid in seen:
            raise CurrentPopulationError(f"invalid or duplicate named territory {cid!r}")
        row = geometry_index.get(cid)
        if row is None:
            raise CurrentPopulationError(f"named territory {cid} absent from certified 2026 geometry")
        certified_name = str(row.get("repo_name") or "").strip()
        if normalize_place(name) != normalize_place(certified_name):
            raise CurrentPopulationError(
                f"named/geometry territory mismatch for {cid}: {name!r} != {certified_name!r}"
            )
        parent = str(row.get("prefecture_or_province") or "").strip()
        specs.append(
            {
                "constituency_id": cid,
                "constituency_name": name,
                "prefecture_or_province": parent,
                "prefecture_or_province_normalized": normalize_place(parent),
                "region_name": territory.get("region_name"),
                "geometry_source": "M26-GOAL100-GEOMETRY-2026-CERTIFICATE-V1",
            }
        )
        seen.add(cid)
    missing = sorted(set(geometry_index) - seen)
    if missing:
        raise CurrentPopulationError(f"certified geometry rows absent from named input: {missing[:5]}")
    return specs


def summarize_failures(failures: Sequence[Mapping[str, Any]], limit: int = 8) -> str:
    """Group the builder's per-territory failures by reason, with examples."""
    by_reason: dict[str, list[Mapping[str, Any]]] = {}
    for failure in failures:
        by_reason.setdefault(str(failure.get("reason") or "UNKNOWN"), []).append(failure)
    parts = []
    for reason, rows in sorted(by_reason.items(), key=lambda item: -len(item[1])):
        examples = []
        for row in rows[:3]:
            best = row.get("best") or {}
            detail = (
                f"err={best.get('err'):.2g} ess={best.get('ess'):.0f} maxw={best.get('max_weight'):.3f}"
                if best.get("err") is not None
                else f"parent={row.get('parent')} rows={row.get('rows')}"
            )
            examples.append(f"{row.get('constituency_id')} [{detail}]")
        parts.append(f"{reason} x{len(rows)}: " + ", ".join(examples))
    return " | ".join(parts[:limit]) or "no per-territory failure recorded"


# `MISSING` is what b.edu_band / b.act_band / b.ur_band return when a code
# cannot be mapped. Raking to it asks the sample to represent "we do not know",
# and with the +12 shift admitting the 2014 cohorts aged 6-10 it carries a mass
# around 1.4e-05: about one row in seventy thousand. b.ipf returns (None, None)
# the moment such a category has mass and no sampled row, so 83 of 92
# territories failed all 48 attempts in run 32828008051.
#
# The rows stay in the pool and can still be drawn; only the unknown cell leaves
# the target vector. That is what the historical 2016/2021 builds effectively
# had: their higher eligibility floor left those cells empty, and b.margins
# already drops categories below 1e-12.
UNKNOWN_MARGIN_CATEGORY = "MISSING"

# es-semara and tarfaya draw from the same RGPH parent pool, `es semara
# tarfaya`. In run 32831683586 es-semara converged and tarfaya did not, with a
# best raking error of 1e-03 against a 5e-06 ceiling while its ESS (245) and max
# weight (0.008) were both comfortable. Same pool, different seed sequence: the
# pool is marginal, not infeasible, so some draws admit weights matching all
# five marginals and some do not.
#
# The answer to a marginal pool is to search longer, not to lower the bar. This
# raises the number of draws attempted; it changes no threshold, no data and no
# policy. Territories that converge still break out on their first good draw, so
# the extra attempts are spent only where they are needed.
IPF_ATTEMPTS_FOR_MARGINAL_POOLS = 320


def drop_unknown_categories(margins: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Remove the unknown cell from each margin and renormalise the rest."""
    cleaned: dict[str, Any] = {}
    dropped: list[str] = []
    for dimension, categories in margins.items():
        kept = {
            category: mass
            for category, mass in categories.items()
            if category != UNKNOWN_MARGIN_CATEGORY
        }
        total = sum(kept.values())
        if not kept or total <= 0:
            # A margin that is nothing but the unknown cell cannot be cleaned:
            # keep it untouched, and do not claim a drop that did not happen.
            cleaned[dimension] = dict(categories)
            continue
        if len(kept) != len(categories):
            dropped.append(f"{dimension}={UNKNOWN_MARGIN_CATEGORY}")
        cleaned[dimension] = {category: mass / total for category, mass in kept.items()}
    return cleaned, sorted(set(dropped))


def margins_without_unknown(b, record: dict[str, Any]):
    """Wrap b.margins so the frozen builder rakes without the unknown cell."""
    original = b.margins

    def wrapped(frame, weights):
        cleaned, dropped = original(frame, weights), None
        cleaned, dropped = drop_unknown_categories(cleaned)
        for name in dropped:
            record["dropped_categories"][name] = record["dropped_categories"].get(name, 0) + 1
        record["margins_calls"] += 1
        return cleaned

    return wrapped


# Two gates in the frozen certificate are assertions of absence: they PASS when
# they are False. Reading them as ordinary booleans reported a clean build as
# having failed `historical_outcome_read` and `sealed_mapping_read`, which is the
# opposite of what those gates mean. The frozen builder's own pass computation
# already inverts them; this mirrors it.
GATES_THAT_PASS_WHEN_FALSE = frozenset({"historical_outcome_read", "sealed_mapping_read"})


def gate_holds(name: str, value: Any) -> bool:
    if name in GATES_THAT_PASS_WHEN_FALSE:
        return value is False
    return bool(value)


def failed_gates(gates: Mapping[str, Any]) -> list[str]:
    return sorted(name for name, value in gates.items() if not gate_holds(name, value))


def report_certificate(path: pathlib.Path, result: int) -> None:
    if not path.is_file():
        emit_error("population certificate missing", f"{path} was not written")
        return
    certificate = read_json(path)
    gates = certificate.get("gates") or {}
    failed = failed_gates(gates)
    quality = certificate.get("quality") or {}
    failures = certificate.get("failures") or []
    summary = (
        f"status={certificate.get('status')} territories={certificate.get('territories')} "
        f"failures={len(failures)} failed_gates={failed} "
        f"min_ess={quality.get('min_effective_archetype_count')} "
        f"max_weight={quality.get('max_single_archetype_weight')} "
        f"max_raking_error={quality.get('max_raking_abs_error')}"
    )
    if result == 0 and not failed:
        emit_notice("current-vintage 2026 population built", summary)
        return
    emit_error("current-vintage 2026 population certificate failed", summary)
    if failures:
        emit_error("per-territory failures", summarize_failures(failures))


def _outdir(argv: Sequence[str]) -> pathlib.Path | None:
    args = list(argv)
    try:
        position = args.index("--outdir")
        return pathlib.Path(args[position + 1]).expanduser().resolve()
    except (ValueError, IndexError):
        return None


def main(argv: Sequence[str] | None = None) -> int:
    geometry_index, geometry_sha256, geometry = load_geometry()
    projection = demographic_projection_boundary()
    unknown_record: dict[str, Any] = {"margins_calls": 0, "dropped_categories": {}}

    def resolver(named_input: Mapping[str, Any]) -> list[dict[str, Any]]:
        return territory_specs_from_certified_geometry(
            named_input, geometry_index=geometry_index
        )

    original_certificate_builder = v1.build_population_certificate

    def certificate_builder(**kwargs: Any) -> dict[str, Any]:
        source_hashes = dict(kwargs.get("source_hashes") or {})
        source_hashes["geometry_2026_certificate"] = geometry_sha256
        kwargs["source_hashes"] = source_hashes
        certificate = original_certificate_builder(**kwargs)
        certificate["geometry_certificate"] = {
            "certificate_id": geometry.get("certificate_id"),
            "as_of": geometry.get("as_of"),
            "gate": geometry.get("gate"),
            "sha256": geometry_sha256,
            "territories": len(geometry_index),
        }
        certificate["demographic_projection_boundary"] = projection
        certificate["unknown_margin_policy"] = {
            "policy": "DROP_UNKNOWN_CATEGORY_FROM_RAKING_TARGETS",
            "category": UNKNOWN_MARGIN_CATEGORY,
            "rows_remain_in_the_sampling_pool": True,
            "margins_calls": unknown_record["margins_calls"],
            "dropped_categories": dict(sorted(unknown_record["dropped_categories"].items())),
            "reason": (
                "MISSING is what the band helpers return for an unmappable code. Raking to it "
                "asks a 256-row sample to represent 'we do not know', and at a mass around "
                "1.4e-05 that is unreachable, so b.ipf returned (None, None) for 83 of 92 "
                "territories in run 32828008051. The rows are still eligible and can still be "
                "drawn; only the unknown cell leaves the target vector."
            ),
            "historical_comparability": (
                "The 2016 and 2021 builds effectively had the same targets: their higher "
                "eligibility floor left these cells empty and b.margins drops anything below 1e-12. "
                "The +12 shift admits the 2014 cohorts aged 6-10, where the unmappable codes live."
            ),
            "decision_owner": "repository owner, 2026-08-24",
            "reversible": "remove the margins patch in this wrapper; V1 is untouched",
        }
        certificate["raking_search_effort"] = {
            "ipf_attempts": IPF_ATTEMPTS_FOR_MARGINAL_POOLS,
            "frozen_v1_default": 48,
            "thresholds_unchanged": True,
            "reason": (
                "es-semara and tarfaya share the pool `es semara tarfaya`. In run 32831683586 the "
                "first converged and the second did not, at a best error of 1e-03 with ESS 245 and "
                "max weight 0.008 both comfortable. A marginal pool is answered by drawing more "
                "samples, not by relaxing a gate: min_ess 128, max_weight 0.05 and raking error "
                "5e-06 are exactly as the historical builders set them."
            ),
        }
        # The V1 helper hashes before this wrapper adds V2 metadata.
        # Recompute over the final object with the previous digest removed.
        certificate.pop("certificate_sha256", None)
        certificate["certificate_sha256"] = v1.sha256_json(certificate)
        return certificate

    v1.territory_specs_from_named_input = resolver
    v1.build_population_certificate = certificate_builder

    actual_argv = list(sys.argv[1:] if argv is None else argv)
    # The frozen builder calls b.margins once per territory; patching it here is
    # the same additive technique already used for the territory resolver.
    import agent_society_v2_build_rich_populations as b  # noqa: E402

    b.margins = margins_without_unknown(b, unknown_record)
    v1.IPF_ATTEMPTS = IPF_ATTEMPTS_FOR_MARGINAL_POOLS
    result = int(v1.main(actual_argv))

    outdir = _outdir(actual_argv)
    if outdir is not None:
        population_path = outdir / "2026_current_population_v1.json"
        if population_path.is_file():
            population = read_json(population_path)
            source_hashes = dict(population.get("source_hashes") or {})
            source_hashes["geometry_2026_certificate"] = geometry_sha256
            population["source_hashes"] = source_hashes
            population["geometry_certificate"] = {
                "certificate_id": geometry.get("certificate_id"),
                "as_of": geometry.get("as_of"),
                "gate": geometry.get("gate"),
                "sha256": geometry_sha256,
                "territories": len(geometry_index),
            }
            population["demographic_projection_boundary"] = projection
            write_json(population_path, population)

        # V1 is frozen at remediation revision 2, so it cannot be taught to
        # report. It returns 2 when its certificate gates fail and says nothing
        # else, which in CI is an exit code and no more: logs and artifacts both
        # need a signed-in session. The verdict is therefore republished here as
        # a check-run annotation, which is public.
        report_certificate(outdir / "current_population_2026_certificate_v1.json", result)
    return result


if __name__ == "__main__":
    # Actions logs and artifacts need a signed-in session, so any escape is also
    # emitted as a check-run annotation, which is public.
    from p3_ci_annotate import run_guarded

    raise SystemExit(run_guarded(main))

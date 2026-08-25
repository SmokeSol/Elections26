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
        # The V1 helper hashes before this wrapper adds V2 metadata.
        # Recompute over the final object with the previous digest removed.
        certificate.pop("certificate_sha256", None)
        certificate["certificate_sha256"] = v1.sha256_json(certificate)
        return certificate

    v1.territory_specs_from_named_input = resolver
    v1.build_population_certificate = certificate_builder

    actual_argv = list(sys.argv[1:] if argv is None else argv)
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

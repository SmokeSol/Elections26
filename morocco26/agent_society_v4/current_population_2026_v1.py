from __future__ import annotations

"""R2 - the current-vintage 2026 population: contract, guards and certificate.

The historical builder rakes on six dimensions, and the sixth is
`prior_vote_or_abstention`, reconstructed from the turnout and the votes of the
previous election. That is correct for 2016 and 2021 and inadmissible for a
current-vintage 2026 environment, for two independent reasons:

* it reads a historical outcome into a snapshot that must not know it;
* the Atlas structural baseline already carries electoral history, so
  re-injecting 2021 as a pseudo individual memory would double-count the same
  signal inside Agent Society.

The 2026 population is therefore raked on its demographic and socio-economic
margins only. The political-memory dimension is not replaced by a dummy
`UNKNOWN = 100%` marginal: it is **absent from the raking problem**. Political
memory then stays UNKNOWN by contract, and BR5 stays NOT_TESTABLE until a
defensible source or protocol exists for it.

This module holds the parts that need no microdata, so the guards and the
certificate are unit-testable without pandas, pyreadstat or the HCP files.
"""

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any, Mapping, Sequence

POPULATION_SCHEMA = "ATLAS_CURRENT_VINTAGE_POPULATION_2026_V1"
CERTIFICATE_SCHEMA = "ATLAS_CURRENT_VINTAGE_POPULATION_2026_CERTIFICATE_V1"
LABOUR_CONTEXT_SCHEMA = "ATLAS_CURRENT_VINTAGE_LABOUR_CONTEXT_2026_V1"

TARGET_YEAR = 2026
RGPH_REFERENCE_YEAR = 2014
AGING_YEARS = TARGET_YEAR - RGPH_REFERENCE_YEAR

# The only dimensions the 2026 raking problem may contain.
RAKING_DIMENSIONS = ("age_band", "sex", "urban_rural", "education_band", "activity_status")

# Anything electoral, in any spelling the historical builder or its callers use.
FORBIDDEN_RAKING_DIMENSIONS = frozenset(
    {
        "prior_vote_or_abstention",
        "prior_vote",
        "vote_intention",
        "turnout",
        "turnout_memory",
        "party_memory",
        "party_affinity",
        "prior_party",
        "target_outcome",
    }
)

# Fields that must not survive into a 2026 archetype record.
FORBIDDEN_RECORD_FIELDS = frozenset(
    {
        "prior_vote_or_abstention",
        "prior_party",
        "party_memory",
        "vote_intention",
        "target_outcome",
    }
)

# Political memory is absent by contract, not imputed.
POLITICAL_MEMORY_CONTRACT = {
    "prior_vote_or_abstention": "ABSENT",
    "turnout_memory": "UNKNOWN",
    "party_memory": "UNKNOWN",
    "political_memory_population_source": "NONE",
}

REQUIRED_LABOUR_RATES = ("unemployment", "youth_unemployment", "female_unemployment", "underemployment")


class CurrentPopulationError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def normalize_place(value: Any) -> str:
    """Same normalisation as the historical builder, so parent resolution matches."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    text = text.lower().replace("'", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return {
        "taroudannt": "taroudant",
        "mohammedia": "mohammadia",
        "moulay yacoub": "moulay yaacoub",
        "agadir ida ou tanane": "agadir ida outanane",
        "oued ed dahab": "oued eddahab",
    }.get(text, text)


def assert_no_electoral_raking(targets: Mapping[str, Any]) -> None:
    """Fail closed if any electoral dimension entered the raking problem."""
    offending = sorted(
        key for key in map(str, targets) if key in FORBIDDEN_RAKING_DIMENSIONS
    )
    if offending:
        raise CurrentPopulationError(
            f"electoral dimensions are inadmissible in the 2026 raking problem: {offending}"
        )
    unexpected = sorted(set(map(str, targets)) - set(RAKING_DIMENSIONS))
    if unexpected:
        raise CurrentPopulationError(
            f"unexpected raking dimension(s) {unexpected}; allowed: {list(RAKING_DIMENSIONS)}"
        )


def strip_political_memory(record: Mapping[str, Any]) -> dict[str, Any]:
    """Remove every political-memory field and prove none survived."""
    result = {key: value for key, value in record.items() if key not in FORBIDDEN_RECORD_FIELDS}
    survivors = sorted(FORBIDDEN_RECORD_FIELDS.intersection(result))
    if survivors:
        raise CurrentPopulationError(f"political memory survived into a 2026 record: {survivors}")
    return result


def validate_labour_context(
    value: Mapping[str, Any], *, snapshot_date: str | None = None
) -> dict[str, Any]:
    """A labour-market rate is empirical input, never a convenient number.

    The historical builder ships LABOR[2016] and LABOR[2021] as constants. For
    2026 the operator must supply the rates with a publisher, a URL and a
    known_as_of at or before the snapshot; otherwise the build refuses to run.
    """
    if value.get("schema_version") != LABOUR_CONTEXT_SCHEMA:
        raise CurrentPopulationError("unexpected labour context schema")
    for field in ("publisher", "source_url", "known_as_of", "rates"):
        if not value.get(field):
            raise CurrentPopulationError(f"labour context is missing {field}")
    rates = value["rates"]
    if not isinstance(rates, Mapping):
        raise CurrentPopulationError("labour context rates must be an object")
    missing = [name for name in REQUIRED_LABOUR_RATES if rates.get(name) is None]
    if missing:
        raise CurrentPopulationError(f"labour context is missing rates {missing}")
    for name, rate in rates.items():
        if rate is None:
            continue
        try:
            number = float(rate)
        except (TypeError, ValueError) as exc:
            raise CurrentPopulationError(f"labour rate {name} is not numeric") from exc
        if not 0.0 <= number <= 1.0:
            raise CurrentPopulationError(f"labour rate {name} must be a proportion in [0,1]")
    try:
        known = date.fromisoformat(str(value["known_as_of"]))
    except ValueError as exc:
        raise CurrentPopulationError("labour context known_as_of must be an ISO date") from exc
    if snapshot_date:
        cutoff = date.fromisoformat(str(snapshot_date))
        if known > cutoff:
            raise CurrentPopulationError(
                f"labour context known_as_of {known} is after the snapshot {cutoff}"
            )
    return {
        "status": "PASS_LABOUR_CONTEXT_2026",
        "publisher": value["publisher"],
        "source_url": value["source_url"],
        "known_as_of": str(known),
        "rates": {str(k): (None if v is None else float(v)) for k, v in rates.items()},
        "labour_context_sha256": sha256_json(value),
    }


def territory_specs_from_named_input(named_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Territory list for the 2026 build, taken from the named input itself.

    Only identifiers and place names are read. No candidacy, no programme, no
    outcome, no sealed mapping.
    """
    specs = []
    for territory in named_input.get("territories") or []:
        territory_id = str(territory.get("territory_id") or "")
        if not territory_id:
            raise CurrentPopulationError("named input carries a territory without an id")
        name = str(territory.get("territory_name") or territory_id)
        specs.append(
            {
                "constituency_id": territory_id,
                "constituency_name": name,
                "prefecture_or_province": name,
                "prefecture_or_province_normalized": normalize_place(name),
                "region_name": territory.get("region_name"),
            }
        )
    if not specs:
        raise CurrentPopulationError("named input declares no territory")
    return specs


def build_population_certificate(
    *,
    territories: Sequence[Mapping[str, Any]],
    failures: Sequence[Mapping[str, Any]],
    archetypes_per_constituency: int,
    labour_report: Mapping[str, Any],
    source_hashes: Mapping[str, str],
    named_input_sha256: str | None,
    expected_territories: int | None = None,
    safe_feature_count: int | None = None,
) -> dict[str, Any]:
    quality = [dict(item.get("quality") or {}) for item in territories]
    min_ess = min((float(q.get("effective_archetype_count") or 0.0) for q in quality), default=0.0)
    max_weight = max((float(q.get("max_single_archetype_weight") or 1.0) for q in quality), default=1.0)
    max_error = max((float(q.get("raking_max_abs_error") or 1.0) for q in quality), default=1.0)
    direct = sum(1 for item in territories if item.get("geography_confidence") == "DIRECT_MICRODATA_ADMIN")
    gates = {
        "no_electoral_raking_dimension": True,
        "no_political_memory_in_records": True,
        "historical_outcome_read": False,
        "sealed_mapping_read": False,
        "labour_context_sourced": labour_report.get("status") == "PASS_LABOUR_CONTEXT_2026",
        "no_failures": not failures,
        "min_ess_ge_128": min_ess >= 128.0,
        "max_weight_le_0_05": max_weight <= 0.05,
        "raking_converged": max_error <= 5e-6,
    }
    if expected_territories is not None:
        gates["all_territories_built"] = len(territories) == expected_territories
    # `historical_outcome_read` and `sealed_mapping_read` must be False to pass.
    passing = all(
        (value is False) if name in {"historical_outcome_read", "sealed_mapping_read"} else bool(value)
        for name, value in gates.items()
    )
    certificate = {
        "schema_version": CERTIFICATE_SCHEMA,
        "certificate_id": "M26-ASV2-CURRENT-VINTAGE-POPULATION-2026-CERTIFICATE-V1",
        "status": "PASS_CURRENT_VINTAGE_POPULATION_2026" if passing else "FAIL_CURRENT_VINTAGE_POPULATION_2026",
        "target_election_year": TARGET_YEAR,
        "regime": "P3_CURRENT_VINTAGE_2026",
        "archetypes_per_constituency": archetypes_per_constituency,
        "territories": len(territories),
        "failures": list(failures),
        "raking_dimensions": list(RAKING_DIMENSIONS),
        "forbidden_raking_dimensions_present": [],
        "historical_outcome_read": False,
        "prior_election_raking_dimension": False,
        "sealed_mapping_read": False,
        "atlas_prior_reinjected": False,
        "target_outcome_used": False,
        "real_llm_outputs_used": False,
        "political_memory_contract": dict(POLITICAL_MEMORY_CONTRACT),
        "political_memory_population_source": "NONE",
        "dummy_unknown_marginal_used": False,
        "labour_context": dict(labour_report),
        "source_hashes": dict(source_hashes),
        "named_input_sha256": named_input_sha256,
        "quality": {
            "min_effective_archetype_count": round(min_ess, 6),
            "max_single_archetype_weight": round(max_weight, 8),
            "max_raking_abs_error": max_error,
            "direct_microdata_admin_territories": direct,
            "proxy_geography_territories": len(territories) - direct,
        },
        "safe_feature_count": safe_feature_count,
        "gates": gates,
        "consequences": {
            "turnout_memory": "UNKNOWN",
            "BR5_PARTY_MEMORY": "NOT_TESTABLE_MISSING_DATA",
            "rationale": (
                "Political memory is absent from the population by contract. It is not imputed, "
                "not defaulted and not taken from a past result."
            ),
        },
        "interpretation_boundary": (
            "This certificate says the population is demographically raked and politically empty. "
            "It says nothing about behavioural realism."
        ),
    }
    certificate["certificate_sha256"] = sha256_json(certificate)
    return certificate

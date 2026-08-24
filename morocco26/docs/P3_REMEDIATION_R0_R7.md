# P3 remediation R0–R7 — runbook

Remediation of the V9 Aïn Chock pilot (2026-08-23). The pilot's `FAIL` was
localised to the environment, not to the voter mind: three of four data layers
were never collected and the fourth was disconnected upstream. This runbook is
the sequence that fixes that, in the order that keeps each step honest.

Nothing here changes the V8 modules or the frozen V9 payload. Every addition is
a versioned sibling, checked by CI against
`FREEZE_MANIFEST_V9_EMPIRICAL_MIND.json`.

---

## R0 — stop the system from lying to us

**Artifacts**

| file | role |
|---|---|
| `morocco26/agent_society_v4/p3_data_layers_v1.py` | measurement engine |
| `morocco26/scripts/p3_data_layer_certificate.py` | CLI |
| `morocco26/data/goal100/agent_society_v2/P3_DATA_LAYER_POLICY_V1.json` | the rules |
| `morocco26/data/goal100/agent_society_v2/P3_DATA_LAYER_CERTIFICATE_V1.json` | current measured state |
| `morocco26/data/candidate_ballot_cells_2026.json` | canonical ballot-cell census |

**Run**

```bash
python morocco26/scripts/p3_data_layer_certificate.py publish-cell-census \
  --named-input <named_input_current_vintage.json>

python morocco26/scripts/p3_data_layer_certificate.py certify \
  --named-input <named_input_current_vintage.json> \
  --environment-id <ID>

python morocco26/scripts/p3_data_layer_certificate.py verify --fail-on-block
```

**Measured on the pilot's own named input (sha `9a4e3c12…`, as-of 2026-08-22)**

```text
LOCAL_CANDIDATES  PARTIAL_REAL   828 cells, 521 OFFICIAL_CONFIRMED, 307 UNKNOWN, 9 parties, 92 territories
PARTY_PROGRAMMES  PLACEHOLDER    162/162 cells = VERIFIED_POSITION_AVAILABLE; rotation offsets
                                 PJD 3, USFP 4, FGD 6, RNI 8, PAM 11, MP 11, PI 14, UC 14, PPS 17
                                 → 9 parties, 7 distinct orderings
REGIONAL_BALLOT   MISSING        zero regional_ballot_cards anywhere
RICH_VOTER_STATE  DISCONNECTED   7 individual fields per voter, upstream certificate PASS

BR1_LOCAL      TESTABLE
BR1_REGIONAL   NOT_TESTABLE_MISSING_DATA
BR3_CANDIDATE  TESTABLE
BR4_PROGRAMME  NOT_TESTABLE_MISSING_DATA
BR5_PARTY_MEMORY NOT_TESTABLE_MISSING_DATA
SPLIT_TICKET   NOT_TESTABLE_MISSING_DATA
```

Lineage advisories, all real and all actionable:

* `candidate_coverage_2026.json` is dated 2026-08-16 while the environment is 2026-08-22;
* it reports 413 active local records against 521 resolved cells;
* it reports 12 "regional records" — rejected local rows, never a regional ballot.

**No more silent fallback.** `behavioral_mind_v8_1.py` /
`behavioral_environment_v8_1.py` build a LOCAL-only environment when the
certificate says the regional layer is not usable, and refuse the
`PARTY_PROGRAMME_ONLY_LOCAL_CANDIDATE_STRIPPED` branch outright.

```bash
python morocco26/scripts/agent_society_behavioral_v8_1.py build \
  --input-env <named_2026_environment> --output-env <v8_1_environment>
```

The programme scaffold is withheld from the model view: axis cells that carry
only "a position exists" are removed and replaced by
`programme_information_state = NOT_COLLECTED_AS_OF_SNAPSHOT`.

---

## R1 — V9.1, epistemology before enrichment

See `morocco26/agent_society_v4/EMPIRICAL_MOROCCAN_MIND_V9_1.md` for the full
argument. In one line: a stratum mean became `SURVEY_STRATUM_PRIOR` with its
dispersion, an ENCDM donor became `MATCHED_DONOR_LATENT_STATE`, manifest
assertions became measurements, and the four named-pipeline fields that matched
no dimension were registered explicitly.

```bash
python morocco26/scripts/agent_society_empirical_mind_v9_1.py validate-amendment \
  --snapshot-date 2026-08-24

python morocco26/scripts/agent_society_empirical_mind_v9_1.py build-environment \
  --base-environment <v8_1_environment> --output <v9_1_environment> \
  --snapshot-date 2026-08-24
```

R1 is done **before** R2 on purpose: reconnecting 158 fields on top of the V9
labelling would have turned twelve stratum averages per voter into twelve
personal opinions, and the society would have looked wonderfully rich for
exactly the wrong reason.

---

## R2 — reconnect the rich population

```bash
python morocco26/scripts/p3_rich_named_bridge.py bridge \
  --named-input <named_input.json> \
  --rich-population <YEAR_rich_population_v2.json> \
  --attitude-overlay <YEAR_attitude_overlay_v1.jsonl> \
  --output <named_input_rich.json> \
  --certificate-output <bridge_certificate.json>
```

Four layers per voter: individual, `household_context`, `survey_stratum`,
`territory_context`. Joined on the real territorial identifier, so no sealed
mapping is opened. The prior-election anchor is dropped by default — importing
it would carry a historical outcome into a current-vintage snapshot — which is
why `turnout_memory` stays UNKNOWN and BR5 stays NOT_TESTABLE.

**Still required:** a rich population artifact for target year 2026. The
existing CI builders produce 2016 and 2021. Producing the 2026 vintage is the
one engineering task left in R2, and it must not take its prior-vote marginals
from a sealed result.

---

## R3 — the LOCAL-only pilot (preregistered, not run)

`morocco26/data/goal100/agent_society_v2/P3_R3_LOCAL_ONLY_PILOT_PROTOCOL_V1.json`

```bash
python morocco26/scripts/p3_r3_local_pilot.py build-arms \
  --rich-named-input <named_input_rich.json> \
  --minimal-named-input <named_input_current_vintage.json> \
  --certificate morocco26/data/goal100/agent_society_v2/P3_DATA_LAYER_CERTIFICATE_V1.json \
  --snapshot-date 2026-08-24 --output-root <run_root>
```

| arm | population | mind | role |
|---|---|---|---|
| A0 | named pipeline, 7 columns | V8.1 | reference, **not** paired |
| A | rich | V8.1 | paired control |
| B | rich (identical) | V8.1 + V9.1 | paired treatment |
| C | rich (identical) | V8.1 + V9.1, one voter per context | intra-batch contamination |

A and B share archetype identity, so their contrast is clean. A0 does not: the
seven-column archetypes have no traceable mapping to any rich archetype, so it
is a reference point, never a control. Randomise arm order, one fresh context
per arm — the 2026-08-23 run generated ARM B after ARM A in the same context,
which is why its measured V9 effect is an upper bound rather than a test.

After the run:

```bash
python morocco26/scripts/p3_r3_local_pilot.py measure \
  --arm A_RICH_V8_1=<run>/A --arm B_RICH_V9_1=<run>/B --arm C_RICH_V9_1_SOLO=<run>/C \
  --certificate <certificate.json> --output <measurement.json>
```

Success threshold: the paired A→B L1 on LOCAL must exceed 20 % of the
between-voter dispersion. The 2026-08-23 pilot measured 4.3 %, which is noise.

---

## R4 / R5 — the two collections that have not started

`party_programme_2026.json` and `regional_ballot_2026.json` ship **empty and
valid**. That is the honest state, and R0 reports it as PLACEHOLDER / MISSING
instead of letting the environment invent a substitute.

```bash
python morocco26/scripts/p3_electoral_offer_2026.py validate-programmes --snapshot-date 2026-08-24
python morocco26/scripts/p3_electoral_offer_2026.py validate-regional --snapshot-date 2026-08-24
```

A collected programme row needs `source_document`, `source_url`,
`publication_date`, `known_as_of`, `document_sha256`, and every axis cell needs
`actual_position_summary` — the position itself, in a sentence a voter could
hear, not a code. The eighteen axes are a research taxonomy, not the content.
An earlier position may be recorded only as `PRE_2026_PARTY_POSITION`.

A regional row needs a region, a party, a verification state, a date and
sources. Rows labelled `REGIONAL_OR_MISSING` are refused: that label marks
candidates who could not be attached to a local constituency, not regional
candidacies.

Once collected:

```bash
python morocco26/scripts/p3_electoral_offer_2026.py ingest-programmes \
  --named-input <named_input.json> --output <named_input_with_programmes.json>

python morocco26/scripts/p3_electoral_offer_2026.py attach-regional \
  --environment <named_2026_environment> --territory-region-map <map.json>
```

Re-certify afterwards: BR4 and BR1-REGIONAL become TESTABLE on their own,
because the certificate measures the artifacts rather than trusting a flag.

---

## R6 / R7 — not yet

R6 (dual-ballot pilot) is blocked on R4 and R5. R7 (historical out-of-sample
validation) is blocked on R6. Agentic lambda stays 0 until R7 passes; nothing in
this remediation touches that boundary.

---

## What is verified, and what is not

Verified by running it:

* the R0 certificate reproduces every number in the audit from the pilot's own named input;
* V8.1 builds a LOCAL-only environment with `REGIONAL_SURFACE_STATUS = MISSING` and no fallback;
* V9.1 turns the same voter's `democracy_satisfaction` from `OBSERVED_INDIVIDUAL /
  individual_fact_claimed: true` into `SURVEY_STRATUM_PRIOR` with `sd` and `n` retained;
* populated dimensions go 2/108 → 4/121 on the named pipeline and → 30/121 on a bridged rich population;
* the 17 frozen V9 files are byte-identical;
* 66 unit tests pass (31 pre-existing, 35 new).

Not verified, and stated as such:

* the 30/121 figure comes from a **shape-faithful synthetic fixture**, not from Moroccan data;
* no 2026 rich population artifact exists yet, so R2 has not run on real data;
* R3 has not been executed — it requires model calls and is the owner's decision;
* R4 and R5 are field collection, not engineering.

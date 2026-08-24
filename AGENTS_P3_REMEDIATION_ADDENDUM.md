# Agent Society — P3 remediation addendum (R0–R7)

This addendum has priority over `AGENTS_BEHAVIORAL_MIND_ADDENDUM.md` and
`AGENTS_EMPIRICAL_MIND_ADDENDUM.md` for anything touching a P3 / current-vintage
2026 environment. Neither of those files is edited; V8 and the frozen V9 payload
stay exactly as they are.

## The finding that produced it

The V9 Aïn Chock pilot of 2026-08-23 returned `FAIL_BEHAVIORAL_REALISM` on
BR1-REGIONAL in both arms. The cause was not the voter mind. Of the four data
layers a substantive dual-ballot P3 needs, one was collected:

```text
LOCAL_CANDIDATES   PARTIAL_REAL    521 verified cells of 828, 307 honestly unknown
PARTY_PROGRAMMES   PLACEHOLDER     nine alphabetical rotations, 162 cells saying only "a position exists"
REGIONAL_BALLOT    MISSING         the V8 slot exists and was filled by copying the local ballot minus the candidate
RICH_VOTER_STATE   DISCONNECTED    158 fields upstream, 7 reaching the model
```

Given that packet, equiprobability across nine regional lists was the honest
answer. The model refused to invent. The gate was measuring the environment.

## Standing rules

### 1. A placeholder is never presented as data

Every P3 environment carries a `P3_DATA_LAYER_CERTIFICATE_V1`. A layer is
`REAL`, `PARTIAL_REAL`, `PLACEHOLDER`, `DISCONNECTED` or `MISSING`, measured —
never declared. Only `REAL` and `PARTIAL_REAL` may reach the model as electoral
information.

```bash
python morocco26/scripts/p3_data_layer_certificate.py certify --named-input <named_input.json>
```

### 2. NOT_TESTABLE is not FAIL

A gate the environment cannot feed is `NOT_TESTABLE_MISSING_DATA`. Reporting it
as FAIL blames the model for a data gap. Use
`morocco26/agent_society_v4/behavioral_realism_v8_1.py`, which scopes each gate
against the certificate and computes `pilot_pass_over_testable_gates`.

### 3. No ballot is ever fabricated to satisfy a schema

The V8 fallback `PARTY_PROGRAMME_ONLY_LOCAL_CANDIDATE_STRIPPED` is forbidden in
P3. When `regional_ballot_cards` is absent:

```text
REGIONAL_SURFACE_STATUS   = MISSING
REGIONAL_SIMULATION_ALLOWED = FALSE
BR1_REGIONAL              = NOT_TESTABLE_MISSING_DATA
SPLIT_TICKET              = NOT_TESTABLE_MISSING_DATA
```

Build with `morocco26/scripts/agent_society_behavioral_v8_1.py`, which picks the
LOCAL-only prompt and output schema automatically. A row that returns a regional
vote on a missing surface fails BR0.

### 4. A population average is never an individual fact

`latent_attitude_*_mean` is a survey stratum mean: `SURVEY_STRATUM_PRIOR`, with
its `_sd` and its stratum `n` retained. `latent_ses_*` and the
`latent_*_budget_share` family are ENCDM matched donors:
`MATCHED_DONOR_LATENT_STATE`. Neither may be rendered as a direct statement, and
neither raw value reaches the model view. Use V9.1, not V9, for anything that
carries these fields.

### 5. Manifest assertions are computed

No manifest may hard-code the absence of a defect. If a property is asserted, it
is measured on the artifact and the build fails closed when the measurement
disagrees. See `EM12_MANIFEST_ASSERTIONS_MEASURED`.

### 6. One answer per question, published together

A P3 environment may not embed a data layer whose canonical snapshot and
certificate are not published in the same lineage. The ballot-cell census
(`morocco26/data/candidate_ballot_cells_2026.json`) is published beside the
certificate; a mismatch blocks, a stale record-level coverage advises.

### 7. NO SOURCE means UNKNOWN

Never NO SOURCE → a synthetic rotation, never a rejected local row promoted into
a regional candidacy, never a pre-2026 position presented as the 2026 programme.

### 8. No dual-ballot model call before R4 and R5

R3 is LOCAL-only by construction. Spending calls on a ballot the environment
cannot describe tests the packet.

## Order of work

| phase | state |
|---|---|
| R0 certify the four layers, kill the silent fallback | done |
| R1 V9.1: EM2 corrected, assertions measured, vocabulary reconnected | done |
| R2 bridge the rich population into the named pipeline | code done, waiting on a 2026 rich-population artifact |
| R3 LOCAL-only pilot, arms A0/A/B/C | preregistered, not run — needs model calls |
| R4 collect real party programmes | contract and validator ready, dataset empty |
| R5 collect the real regional ballot | contract and validator ready, dataset empty |
| R6 dual-ballot pilot | blocked on R4 and R5 |
| R7 historical out-of-sample validation | blocked on R6; lambda stays 0 until then |

## Forecast boundary

Unchanged and non-negotiable:

```text
raw model vote  !=  2026 forecast
agentic lambda  =   0
scale_allowed   =   false
startup_work_item_cap = 1
```

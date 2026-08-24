# P3 remediation R0-R7 - runbook

> **Revision 2.** Three corrections landed after review, before any R3 model
> call: the CI freeze gate had a path filter that excluded the workflow and its
> own manifest, so its coverage depended on what else was in the push;
> `attention_score` turned out to be an engine composite, not evidence; and R3's
> three-arm design could not identify contamination. See *Revision 2
> corrections* at the end.

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

**The 2026 population.** The historical builder rakes on six dimensions and the
sixth is `prior_vote_or_abstention`, reconstructed from the previous election's
turnout and votes. That is inadmissible here, twice over: it reads a historical
outcome into a current-vintage snapshot, and the Atlas structural baseline
already carries electoral history, so re-injecting 2021 as a pseudo individual
memory would double-count the same signal inside Agent Society.

The historical builder is not modified. A sibling builds the 2026 vintage with

```text
targets = age_band x sex x urban_rural x education_band x activity_status
```

`prior_vote_or_abstention` is **absent from the raking problem** - not a dummy
`UNKNOWN = 100%` marginal. `assert_no_electoral_raking` refuses either form. The
certificate must declare `historical_outcome_read=false`,
`prior_election_raking_dimension=false`, `sealed_mapping_read=false`,
`atlas_prior_reinjected=false` and `political_memory_population_source=NONE`,
and CI asserts it. Consequence: `turnout_memory` stays UNKNOWN and BR5 stays
NOT_TESTABLE until a defensible source or protocol exists for political memory.

The labour context is empirical input: `LABOUR_CONTEXT_2026_TEMPLATE.json` ships
with null rates and **fails validation on purpose**. A build cannot start until
an operator fills it from a published HCP release with a URL and a known_as_of.

```bash
python morocco26/scripts/agent_society_v2_build_current_population_2026.py --ind rgph_individual.dta --hh rgph_household.dta --encdm encdm_household.sav --named-input named_input_current_vintage.json --labour-context LABOUR_CONTEXT_2026.json --snapshot-date 2026-08-24 --outdir out
```

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

A 2×2, all four cells on the same rich population:

|  | **batch 32** | **solo 1** |
|---|---|---|
| **V8.1** | `A_batch` | `A_solo` |
| **V9.1** | `B_batch` | `B_solo` |

which yields four paired contrasts and, above all, the interaction:

```text
D_mind_batch    = L1(A_batch, B_batch)
D_mind_solo     = L1(A_solo,  B_solo)     effect of V9.1 with no inter-voter conditioning
D_batching_v8_1 = L1(A_batch, A_solo)
D_batching_v9_1 = L1(B_batch, B_solo)
interaction     = D_mind_batch - D_mind_solo
```

The interaction is the question that matters: **does the V9.1 mind behave
differently because the 32 voters cohabit in one context?** Revision 1 tried to
read that from `B − C` alone, which confounds the batch effect, the context-size
effect, run stochasticity and contamination, and had no solo counterpart of A.

Every cell is replicated (3 batch, 2 solo by default) because two calls on
identical inputs already differ: `same_condition_noise` is the null. A0 stays an
unpaired historical reference — the seven-column archetypes have no traceable
mapping to any rich archetype.

Randomise the order of the (arm, replicate) units, one fresh context each — the
2026-08-23 run generated ARM B after ARM A in the same context, which is why its
measured V9 effect is an upper bound rather than a test.

Default budget: 6 batch calls + 2 × N solo calls (134 for a 32-voter territory).
`build-arms` prints it and refuses to proceed on a dirty tree or without a
recorded CI conclusion.

After the run:

```bash
python morocco26/scripts/p3_r3_local_pilot.py measure \
  --arm A_RICH_V8_1=<run>/A --arm B_RICH_V9_1=<run>/B --arm C_RICH_V9_1_SOLO=<run>/C \
  --certificate <certificate.json> --output <measurement.json>
```

Promotion needs **both** rules to hold on the contamination-free contrast:

```text
R3_PROMOTION_THRESHOLD = 0.20   D_mind_solo > 20% of between-voter dispersion in A_solo
R3_NOISE_MULTIPLE      = 2.0    D_mind_solo > 2x the same-condition replicate noise
```

The 2026-08-23 pilot measured 4.3 % of dispersion and estimated no null at all.

`R3_FAIL` blocks promotion of the current V9.1 mechanism **under the current
LOCAL information surface**. It does not prove that V9.1 cannot interact with a
richer electoral offer: R3 runs without real programmes, without party memory
and without a regional ballot.

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

---

## Revision 2 corrections

Three findings from the pre-R3 review, all fixed here.

### The freeze gate's coverage depended on the push, not on the change

`morocco26-p3-remediation-gates.yml` had a `paths` filter listing neither the
workflow nor `FREEZE_MANIFEST_V9_1_P3_REMEDIATION.json`. Commit `08d4b62`
changed exactly those two files.

Checked rather than assumed: run `32731849859` **did** fire on `08d4b62` and
concluded success — because GitHub evaluates `paths` over every commit in the
push, and that push also carried `d25b793`, which touched many listed paths.
Pushed alone, which is the normal shape of a follow-up fix, `08d4b62` would have
been skipped. A gate whose coverage depends on what else happens to be in the
push is not a gate.

The filter is gone — the gate runs on every push to the branch — and the inline
heredocs moved into `morocco26/scripts/p3_verify_freeze.py`.

The branch is not protected and has no required status check, so the freeze is a
**detector, not a barrier**. `p3_r3_local_pilot.py build-arms` therefore records
the git HEAD sha, the working-tree state, the freeze manifest sha and revision,
and the operator-supplied CI conclusion into `r3_arm_plan.json`, and refuses to
proceed on a dirty tree or an unrecorded CI run.

### attention_score is an engine composite, not evidence

`information_diet.derive_profile` computes

```text
attention = 0.45*political_discussion + 0.30*education_score
          + 0.15*digital_news_exposure + 0.10*localism
```

Verified on the named 2026 input: **2944/2944 rows exact**, max abs error
1.11e-16, with `digital_news_exposure` absent so the engine default 0.4 applies
to everyone as a constant.

`political_attention` was therefore misclassified twice: engine-derived rather
than observed, and a deterministic function of three dimensions already
registered separately. V9.1 adds `ENGINE_DERIVED_COMPOSITE` (precedence 10,
`individual_fact_claimed=false`, hidden from the model), the gate
`EM13_NO_ENGINE_COMPOSITE_COUNTED_AS_EVIDENCE`, and a new audit figure
`independent_evidence_dimensions`.

Corrected count on the named pipeline: **4 populated, 3 independent** — not 4.
The dimension keeps a genuine `political_attention` source field for the day a
measured variable exists. The 2026 builder must certify the provenance of any
attention variable it emits; re-injecting the engine composite is forbidden.

### R3 became a 2×2 with a null

See the R3 section. `B − C` was not identifiable; `D_mind_solo` and the
interaction are.

### Freeze manifests are chained

Revision 2 records `supersedes_manifest_sha256`, `git_commit_sha`, `reason` and
a `freeze_chain`, so a manifest cannot be silently replaced by a new truth.

### Recorded, not blocking

A `MATCHED_DONOR_LATENT_STATE` settles what a variable *is*, not how good the
imputation was. Before scale or forecast the donor fields must carry
`donor_source_year`, `donor_match_method`, `donor_match_distance`,
`donor_reuse_count` and `donor_support_overlap`. Recorded in the R2 contract as
a scale gate, not an R3 blocker: soft, clearly labelled contextual use is fine
for R3, promotion is not.

### The guiding principle

Not catalogue density. 30/121, 40/121 or 20/121 can each be correct. The target
is **maximum true information, minimum invented information.**

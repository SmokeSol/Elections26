# Empirical Moroccan Mind V9.1 — amendment 01

## Why an amendment and not a V10

The V9 payload `sha256 = 3cdda05d95ef387c85ef8919fe3ea188226f21c0ccc9d5ef9eb7bf35c7d32df0`
is frozen and stays frozen. Every file in `FREEZE_MANIFEST_V9_EMPIRICAL_MIND.json`
is byte-identical after this work; CI checks it. V9.1 is applied **on top** of the
frozen registry at load time, the same way `agent_society_v2_main_bridge_v6.py`
amends V5 without editing V5.

The Aïn Chock pilot showed that a bigger catalogue is not the lever. With seven
input columns, going from 108 to 142 dimensions moves the score from 2/108 to
2/142: the denominator grows, the numerator does not. V9.1 fixes what the score
was actually made of.

## What V9.1 corrects

### EM2 — a stratum mean is not a personal fact

`latent_attitude_<x>_mean` comes from `agent_society_v2_build_attitude_overlay.py`:
an Afrobarometer conditional mean over a demographic stratum, shipped with a
companion `_sd` and an `attitude_posterior_stratum_n`. V9 read it as an
individual source field and stamped it:

```json
{"epistemic_status": "OBSERVED_INDIVIDUAL", "individual_fact_claimed": true}
```

while never consuming the `_sd`. On the rich populations that was 12 of the 14
populated dimensions.

V9.1 routes those fields to a new status:

```text
SURVEY_STRATUM_PRIOR
  stratum_mean, stratum_sd, stratum_support_n, stratum_match_level
  individual_fact_claimed = false
  behavioral_use = CONTEXT_ONLY_NOT_INDIVIDUAL_TRAIT
  model_visibility = STRATUM_CONTEXT   (DIRECT_STATEMENT is refused)
```

The model sees a sentence about a group, never about the person:

> Autour de toi, chez des personnes comparables, « Ta satisfaction envers le
> fonctionnement démocratique » se situe en moyenne à un niveau bas ; les avis y
> sont assez partagés. Ce n'est pas forcément ton cas.

The raw mean and the raw dispersion are stripped from the model-visible copy and
kept in the audit. Promotion to `SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY`,
the status the model may embody, requires a validated conditional draw. That
validation does not exist, so no promotion happens.

### EM2 sibling — the ENCDM matched donor

`latent_ses_decile`, `latent_poverty_risk`, `latent_vulnerability_risk` and the
`latent_*_budget_share` family come from an ENCDM household matched
statistically to the synthetic person. The rich feature manifest already says
they are "not an observed fact about that synthetic person". Reconnecting the
158 fields without a rule would have turned them into biography, so V9.1 adds:

```text
MATCHED_DONOR_LATENT_STATE   precedence 45
  individual_fact_claimed = false
  synthetic_latent_state_claimed = true
  model_visibility = DONOR_CONTEXT
```

### Manifest assertions are measured

`build_empirical_environment()` wrote

```python
"population_prior_relabelled_as_individual_fact": False
```

as a constant. The manifest certified the absence of the defect that was
present. V9.1 measures the property over every mind it builds, refuses to write
a manifest that contradicts the measurement, and exposes two new gates:

```text
EM11  stratum dispersion retained
EM12  manifest assertions measured, not declared
```

### Wiring the V9 overlay could never exercise

* `household_context` was read from the voter **batch**, a key the named batch
  schema never emits, so the 15 household dimensions could not fire. V9.1 reads
  it per voter, then per batch.
* `territory_context` had the same problem while the territory record sat unread
  in `contexts/`. V9.1 builds the ecological map from the environment's own
  context files.

### Vocabulary

Four of the seven fields the named pipeline carries matched no dimension,
because `individual_source_fields` were written against the 158-column blind
population and never against the named pipeline.

| field | decision |
|---|---|
| `attention_score` | new dimension `political_attention` |
| `localism` | new dimension `territorial_local_orientation` |
| `prior_vote_or_abstention` | new dimension `turnout_memory` |
| `information_diet_tier` | **not** a dimension — it is the engine's information-distribution rule, not a psychological state |

Declined on purpose, and recorded in the amendment: `attention_score` is not
`campaign_attention` (attention to *this* campaign); `prior_vote_or_abstention`
is not `habitual_turnout` (one election is not a habit); owning a television is
not `television_news_exposure`; a current milieu is not a migration trajectory.

Ten further dimensions were registered for attributes the rich population
genuinely measures, and eight declared field transforms fold the measured coding
into the registry vocabulary. Every transform returns UNKNOWN on anything it
does not recognise — a transform never invents a value.

Two of them fix silent misreadings: 2.5 persons per room used to read as the
unit-interval value 0.025 and report LOW crowding; one unemployed household
member used to read as burden 1.0.

## Effect, measured

| | catalogue | populated per voter |
|---|---|---|
| V9 on the named pipeline (7 columns) | 108 | 2 |
| V9.1 on the named pipeline | 121 | 4 |
| V9.1 on the R2 rich population | 121 | 30 |

The rich figure is measured on a shape-faithful synthetic fixture, not on
Moroccan data. Re-measure once the CI builders publish a 2026 rich population.

## Commands

```bash
python morocco26/scripts/agent_society_empirical_mind_v9_1.py validate-amendment \
  --snapshot-date 2026-08-24

python morocco26/scripts/agent_society_empirical_mind_v9_1.py build-environment \
  --base-environment /path/to/v8_1_environment \
  --output /path/to/v9_1_environment \
  --snapshot-date 2026-08-24 \
  --stratum-visibility context
```

`--stratum-visibility hidden` keeps the stratum priors in the audit and out of
the model-visible context, for an arm that wants only observed evidence.

## What V9.1 does not change

Forecast lambda stays 0. EM3 is still blocked: no calibrated Moroccan prior pack
exists, so `SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY` remains unreachable
and scaling remains forbidden. V9.1 makes the evidence honest and connected; it
does not make the society validated.

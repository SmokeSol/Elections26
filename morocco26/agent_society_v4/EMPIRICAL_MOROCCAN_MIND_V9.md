# Empirical Moroccan Mind V9

## Purpose

Behavioral Mind V8 fixed the cognitive order of the simulation but intentionally left many psychopolitical states unknown. V9 adds a versioned, auditable empirical layer without converting Moroccan population averages into invented individual biographies.

## What V9 adds

- 108 registered dimensions in 10 families;
- individual, household, survey-prior, ecological and unknown evidence classes;
- deterministic posterior draws for synthetic replicates, only from a calibrated prior pack;
- explicit source and date cutoffs;
- direct-evidence-only protection for sensitive cultural/political mechanisms;
- model-visible human context with raw provenance and posterior distributions removed;
- fail-closed EM0–EM10 validation;
- an observed-only diagnostic mode and a separate calibrated-pilot mode;
- a Sol launcher that refuses observed-only V9 environments.

## Dimension families

```text
MATERIAL_HOUSEHOLD
LIFE_TRAJECTORY
POLITICAL_BIOGRAPHY
LOCAL_INSTITUTIONAL_EXPERIENCE
INFORMATION_MEDIA
SOCIAL_EMBEDDEDNESS
PARTY_CANDIDATE_RELATION
ISSUE_SALIENCE
AFFECT_DECISION
BALLOT_MECHANICS
```

The catalogue includes dimensions such as employment security, household unemployment burden, price pressure, deprivation, housing security, care burden, migration trajectory, political interest and efficacy, trust, government evaluation, public-service experiences, corruption exposure, media channels, political discussion, social pressure, candidate awareness, issue salience, hope/resignation, turnout cost and split-ticket openness.

It also registers sensitive mechanisms such as family recommendation or clientelistic exposure, but those are **direct-evidence-only** and therefore remain unknown unless explicitly supplied.

## Source precedence

```text
individual observation
> household observation
> calibrated survey posterior draw
> ecological context
> registered experimental prior
> UNKNOWN
```

Precedence means “use the strongest available evidence.” It never permits changing the label of the evidence.

## Population priors

A valid prior pack must:

1. be produced from registered Moroccan sources;
2. document survey design and weights;
3. contain no raw microdata;
4. contain no direct party-choice prior;
5. preserve uncertainty and cell support;
6. document fallback hierarchy;
7. pass weighted national/subgroup margin checks;
8. pass correlation and holdout checks;
9. be known before the simulation snapshot date;
10. be frozen and hashed before a model call.

A synthetic draw is deterministic for:

```text
snapshot_id × voter_id × replicate_id × prior_id × cell_id × dimension_id
```

The posterior distribution remains in the audit artifact; it is removed from the model-visible copy. The draw is always labelled synthetic, never observed.

## Commands

Validate the registries:

```bash
python3 morocco26/scripts/agent_society_empirical_mind_v9.py validate-registry \
  --dimensions morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/EMPIRICAL_MIND_DIMENSIONS_V1.json \
  --sources morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/EMPIRICAL_SOURCE_REGISTRY_V1.json \
  --snapshot-date 2026-08-23
```

Validate the blocked prior template:

```bash
python3 morocco26/scripts/agent_society_empirical_mind_v9.py validate-prior-pack \
  --dimensions .../EMPIRICAL_MIND_DIMENSIONS_V1.json \
  --sources .../EMPIRICAL_SOURCE_REGISTRY_V1.json \
  --prior-pack .../EMPIRICAL_PRIOR_PACK_TEMPLATE_V1.json \
  --snapshot-date 2026-08-23 \
  --allow-blocked-template
```

Build an observed-only V9 overlay over a valid V8 environment:

```bash
python3 morocco26/scripts/agent_society_empirical_mind_v9.py build-environment \
  --v8-environment /path/to/v8_environment \
  --output /path/to/v9_observed_only \
  --dimensions .../EMPIRICAL_MIND_DIMENSIONS_V1.json \
  --sources .../EMPIRICAL_SOURCE_REGISTRY_V1.json \
  --snapshot-date 2026-08-23 \
  --prompt-addendum .../EMPIRICAL_MIND_PROMPT_ADDENDUM_V1.md
```

This environment is diagnostic only and remains non-runnable by the V9 Sol launcher until the calibrated prior pack passes.

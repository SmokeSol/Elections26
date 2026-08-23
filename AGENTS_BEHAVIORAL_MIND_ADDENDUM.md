# Agent Society — Behavioral Mind V8 addendum

This is the highest-priority Agent Society behavioral instruction after the three-regime and current-vintage architecture.

Read before any new P3 model call:

```text
morocco26/data/goal100/agent_society_v2/BEHAVIORAL_MIND_STATE_V1.json
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/BEHAVIORAL_MIND_PROTOCOL_V1.json
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/BEHAVIORAL_VOTER_PROMPT_V1.md
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/BEHAVIORAL_VOTER_OUTPUT_SCHEMA_V1.json
```

## Canonical behavioral architecture

```text
OBJECTIVE WORLD
    ↓
VOTER STATE / MEMORY
    ↓
SUBJECTIVE ELECTORAL WORLD
    ↓
BEHAVIOR: turnout + LOCAL + REGIONAL
    ↓
FREE FIRST-PERSON POV
    ↓
SEPARATE POST-HOC AUDIT
```

A model is not asked to behave as a political analyst and then justify its answer. `factor_importance`, `reason_codes`, `cited_factors` and the old analyst-style `observable_rationale` are not part of the Behavioral Mind V8 voter output.

## P3 current-vintage rule

`P3_CURRENT_VINTAGE_2026` may run with honest `UNKNOWN` candidate cells. A complete final candidate roster is **not** required for a current-vintage pilot. `FINAL_BALLOT_2026` remains a separate strict gate.

Do not silently invent a candidate, personal familiarity, candidate reputation, family/neighbor recommendation, local notable network, clientelism, vote buying, tribal/community alignment, party affinity/rejection, or current political fact. Missing psychopolitical state stays `UNKNOWN` unless supplied upstream or by a separately registered prior.

## Existing Aïn Chock pilot

The pre-V8 atomic Aïn Chock run is preserved as a diagnostic, not promoted. It passed transport/dual-ballot mechanics but failed behavioral realism:

```text
32 unique voter archetypes
LOCAL probability vectors: 1 unique vector → FAIL_BR1
REGIONAL probability vectors: 2 unique vectors
LOCAL winner: PAM 32/32
REGIONAL winners: PPS 24, PAM 8
turnout: non-degenerate
POV: legacy analyst rationale → FAIL_BR8
```

See `BEHAVIORAL_MIND_STATE_V1.json` for hashes.

## Execution gate

Before any broader P3 run:

1. build a Behavioral Mind V8 overlay from the already-valid current-vintage named environment;
2. run exactly one work item / 32 voters with `run_g0_sol_named_2026_behavioral_v8.py`;
3. run `agent_society_behavioral_v8.py audit`;
4. require BR0 + BR1 + BR6 + BR8 before any second-stage pilot;
5. require paired BR2/BR3/BR4/BR5/BR7 tests and historical out-of-sample validation before broad scale.

There is no scale-override flag.

## Forecast boundary

Agent Society raw vote levels are not a forecast. The registered interpretation remains:

```text
ATLAS structural baseline
    +
calibrated λ × AgenticDelta
    =
forecast candidate
```

Until historical validation, λ is zero.

# Agent Society — three-regime goal addendum

> **Behavioral V8 / current-vintage override:** before any new P3 model call, read `AGENTS_BEHAVIORAL_MIND_ADDENDUM.md`. Its `P3_CURRENT_VINTAGE_2026` rules supersede the stale complete-roster fail-closed wording below **for current-vintage pilots only**. `FINAL_BALLOT_2026` remains strict. Historical text is retained here for auditability rather than rewritten.

This addendum supersedes the old assumption that the fully blind G0 is the candidate primary election simulation.

Read first:

```text
morocco26/data/goal100/agent_society_three_regime_goal_v1.json
morocco26/frontends/agent_society_opus/source_v2/simulation_goal/AGENT_SOCIETY_THREE_REGIME_GOAL_V1.json
morocco26/frontends/agent_society_opus/source_v2/simulation_goal/THREE_REGIME_SIMULATION_PROTOCOL_V1.json
morocco26/frontends/agent_society_opus/source_v2/simulation_goal/README.md
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/CHATGPT_ACCOUNT_BASELINE_PROTOCOL_V4_THREE_REGIME.json
```

## Canonical interpretation

```text
BLIND_ATTRIBUTE_CONTROL
    existing one-work-item / 32-agent run
    attribute-only control
    never primary election simulation

HISTORICAL_SEMIBLIND_RICH
    historical backtest regime
    identities and outcomes remain sealed
    same existing candidate/programme facts
    pointer-only reading contract; no duplicated values

REALISTIC_2026_NAMED
    intended primary current-election simulation
    real parties, candidates, territories and symbols
    per-voter information diets
    currently fail-closed because the certified roster is incomplete
```

`NAMED_2026_PSEUDONYMIZED_TWIN` is a non-primary diagnostic used only to compare the same 2026 facts with and without identity labels.

## Current hard truth

The attached/owner-local blind report contains 32 explained agents in one batch and one anonymous territory, not 32 work items. Do not repeat the stale statement that a 1,024-row startup has already occurred.

The pinned-main 2026 ballot certificate is `FAIL`: zero verified double-entry rows and zero territory coverage. No agent may launch a named national simulation, fill gaps from model memory, or invent candidates until a complete named input passes `NAMED_2026_INPUT_SCHEMA_V1.json`.

## Mandatory gates

```text
P0  register/preserve blind 32 control
P1  bind exact raw P0, then same-work-item semiblind-rich 32-agent pilot
P2  explicit review → 32 work items / 1,024 agents
P3  named source PASS → named/twin pilot
P4  explicit new freeze → any scale beyond startup
```

## Files that implement this goal

```text
morocco26/scripts/three_regime_core.py
morocco26/scripts/agent_society_v2_three_regime_goal.py
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/run_g0_sol_semiblind_rich.py
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/run_g0_sol_named_2026.py
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/run_three_regime_startup.py
morocco26/frontends/agent_society_opus/source_v2/chatgpt_baseline/compare_three_regime_startup.py
```

When this addendum conflicts with older startup prose in `AGENTS.md`, follow the newer machine-readable goal/freeze and this addendum. Never rewrite history to claim that V4 was frozen before the already-existing P0 blind output; it was frozen after P0 and before P1/P3.

## Additional V6 gates

- P1 requires the owner-local raw D0 snapshot with exactly one populated work item and 32 unique archetypes. The report alone cannot identify election + condition.
- Named 2026 uses `ballot_party_ids` per territory. A global party panel copied to all 92 territories is forbidden.
- Every named candidacy requires two registered sources from at least two independence clusters.
- Programmes contain exactly the canonical 18 axes and all timestamps must be at or before the packet snapshot.
- Source IDs, URLs and hashes remain builder provenance and are stripped from the model-visible electoral surface.
- P3 is a paired named/twin pilot; neither side may scale alone.

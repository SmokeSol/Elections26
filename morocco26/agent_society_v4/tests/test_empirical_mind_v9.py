from __future__ import annotations

import copy
import json
import pathlib
import tempfile
import unittest

from morocco26.agent_society_v4.empirical_mind_v9 import (
    build_empirical_mind,
    empiricalize_behavioral_voter,
)
from morocco26.agent_society_v4.empirical_environment_v9 import build_empirical_environment
from morocco26.agent_society_v4.empirical_priors_v9 import (
    CALIBRATED_STATUS,
    EmpiricalPriorError,
    deterministic_draw,
    select_prior,
    validate_dimension_registry,
    validate_prior_pack,
    validate_source_registry,
)
from morocco26.agent_society_v4.empirical_validation_v9 import audit_empirical_mind

ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "morocco26" / "frontends" / "agent_society_opus" / "source_v2" / "chatgpt_baseline"


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def calibrated_pack(dimension_id="political_interest"):
    return {
        "schema_version": "ATLAS_EMPIRICAL_MOROCCAN_PRIOR_PACK_V1",
        "status": CALIBRATED_STATUS,
        "pack_id": "TEST_PACK",
        "raw_microdata_embedded": False,
        "individual_facts_claimed": False,
        "direct_party_choice_prior_present": False,
        "priors": [
            {
                "prior_id": "P_TEST",
                "dimension_id": dimension_id,
                "source_ids": ["AFROBAROMETER_MAR_R10_2024"],
                "known_as_of": "2025-06-13",
                "conditioning_fields": ["urban_rural"],
                "ecological_inference_guard": True,
                "may_create_partisan_preference": False,
                "calibration_status": "CALIBRATED",
                "calibration_metrics": {
                    "weighted_margin_max_abs_error": 0.01,
                    "subgroup_margin_max_abs_error": 0.02,
                    "effective_sample_size": 700.0,
                },
                "cells": [
                    {
                        "cell_id": "URBAN",
                        "conditions": {"urban_rural": "URBAN"},
                        "distribution": {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.3},
                        "support_n": 800,
                        "effective_sample_size": 600.0,
                    },
                    {
                        "cell_id": "FALLBACK",
                        "conditions": {},
                        "distribution": {"LOW": 0.4, "MEDIUM": 0.4, "HIGH": 0.2},
                        "support_n": 2000,
                        "effective_sample_size": 1200.0,
                    },
                ],
            }
        ],
    }


class EmpiricalMindV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dimensions = load("EMPIRICAL_MIND_DIMENSIONS_V1.json")
        cls.sources = load("EMPIRICAL_SOURCE_REGISTRY_V1.json")
        cls.template = load("EMPIRICAL_PRIOR_PACK_TEMPLATE_V1.json")

    def test_registry_is_large_and_versioned(self):
        result = validate_dimension_registry(self.dimensions)
        self.assertGreaterEqual(result["dimensions"], 100)
        self.assertGreaterEqual(result["families"], 10)

    def test_source_registry_passes_snapshot_cutoff(self):
        result = validate_source_registry(self.sources, snapshot_date="2026-08-23")
        self.assertEqual(result["sources"], 5)

    def test_source_after_snapshot_fails_closed(self):
        bad = copy.deepcopy(self.sources)
        bad["sources"][0]["known_as_of"] = "2027-01-01"
        with self.assertRaises(EmpiricalPriorError):
            validate_source_registry(bad, snapshot_date="2026-08-23")

    def test_blocked_prior_template_is_valid_but_not_calibrated(self):
        result = validate_prior_pack(
            self.template,
            source_registry=self.sources,
            dimension_registry=self.dimensions,
            snapshot_date="2026-08-23",
            require_calibrated=False,
        )
        self.assertIn("BLOCKED", result["status"])
        with self.assertRaises(EmpiricalPriorError):
            validate_prior_pack(
                self.template,
                source_registry=self.sources,
                dimension_registry=self.dimensions,
                snapshot_date="2026-08-23",
                require_calibrated=True,
            )

    def test_direct_party_affinity_prior_is_rejected(self):
        pack = calibrated_pack("party_affinity")
        with self.assertRaises(EmpiricalPriorError):
            validate_prior_pack(
                pack,
                source_registry=self.sources,
                dimension_registry=self.dimensions,
                snapshot_date="2026-08-23",
            )

    def test_observed_individual_overrides_survey_prior(self):
        voter = {
            "weighted_archetype_id": "A001",
            "political_interest": 0.91,
            "urban_rural": "URBAN",
        }
        mind, _ = build_empirical_mind(
            voter=voter,
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=calibrated_pack(),
            snapshot_id="S1",
            snapshot_date="2026-08-23",
        )
        state = mind["dimensions"]["political_interest"]
        self.assertEqual(state["epistemic_status"], "OBSERVED_INDIVIDUAL")
        self.assertEqual(state["band_or_category"], "HIGH")

    def test_survey_prior_draw_is_labelled_synthetic_and_deterministic(self):
        pack = calibrated_pack()
        validate_prior_pack(
            pack,
            source_registry=self.sources,
            dimension_registry=self.dimensions,
            snapshot_date="2026-08-23",
        )
        selected = select_prior(pack, dimension_id="political_interest", voter={"urban_rural": "URBAN"})
        self.assertIsNotNone(selected)
        a = deterministic_draw(selected, snapshot_id="S", voter_id="A", replicate_id="R00")
        b = deterministic_draw(selected, snapshot_id="S", voter_id="A", replicate_id="R00")
        self.assertEqual(a, b)
        mind, _ = build_empirical_mind(
            voter={"weighted_archetype_id": "A", "urban_rural": "URBAN"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=pack,
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        state = mind["dimensions"]["political_interest"]
        self.assertEqual(
            state["epistemic_status"],
            "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY",
        )
        self.assertFalse(state["individual_fact_claimed"])
        self.assertIn("posterior_distribution", state)

    def test_ecological_context_never_becomes_individual_value(self):
        mind, _ = build_empirical_mind(
            voter={"weighted_archetype_id": "A"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-23",
            ecological_context={"water_stress_rate": 0.8},
        )
        state = mind["dimensions"]["water_service_stress"]
        self.assertEqual(state["epistemic_status"], "ECOLOGICAL_CONTEXT_ONLY")
        self.assertIsNone(state["value"])
        self.assertFalse(state["individual_fact_claimed"])

    def test_sensitive_mechanism_stays_unknown_without_direct_evidence(self):
        mind, _ = build_empirical_mind(
            voter={"weighted_archetype_id": "A", "gender": "F", "urban_rural": "URBAN"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=calibrated_pack(),
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        self.assertEqual(
            mind["dimensions"]["clientelistic_exchange_exposure"]["epistemic_status"],
            "UNKNOWN",
        )
        self.assertEqual(
            mind["dimensions"]["party_affinity"]["epistemic_status"],
            "UNKNOWN",
        )

    def test_missing_dimensions_are_explicit_unknowns(self):
        mind, audit = build_empirical_mind(
            voter={"weighted_archetype_id": "A"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        self.assertGreater(audit["epistemic_counts"]["UNKNOWN"], 90)
        self.assertEqual(mind["dimensions"]["political_anger"]["behavioral_use"], "DO_NOT_IMPUTE")

    def test_v8_state_is_preserved(self):
        voter = {
            "weighted_archetype_id": "A",
            "voter_mind_state": {"schema_version": "V8", "x": 1},
            "electoral_world_as_seen": {"LOCAL": {}, "REGIONAL": {}},
            "political_interest": 0.5,
        }
        visible, _ = empiricalize_behavioral_voter(
            voter,
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        self.assertEqual(visible["voter_mind_state"], voter["voter_mind_state"])
        self.assertIn("empirical_moroccan_mind", visible)

    def test_model_visible_copy_hides_raw_posterior_and_source_ids(self):
        visible, _ = empiricalize_behavioral_voter(
            {"weighted_archetype_id": "A", "urban_rural": "URBAN"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=calibrated_pack(),
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        state = visible["empirical_moroccan_mind"]["dimensions"]["political_interest"]
        self.assertNotIn("posterior_distribution", state)
        self.assertNotIn("source_ids", state)
        self.assertEqual(
            state["epistemic_status"],
            "SYNTHETIC_POSTERIOR_DRAW_FROM_MOROCCAN_SURVEY",
        )

    def test_gate_blocks_scale_without_calibrated_prior_and_paired_tests(self):
        mind, _ = build_empirical_mind(
            voter={"weighted_archetype_id": "A", "political_interest": 0.8},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        report = audit_empirical_mind(
            mind,
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_date="2026-08-23",
            forecast_lambda=0.0,
        )
        self.assertFalse(report["scale_allowed"])
        self.assertFalse(report["gates"]["EM3_MOROCCAN_PRIOR_PACK_CALIBRATED"])
        self.assertTrue(report["gates"]["EM9_FORECAST_BOUNDARY_LAMBDA_ZERO_PREVALIDATION"])

    def test_nonzero_lambda_fails_prevalidation_gate(self):
        mind, _ = build_empirical_mind(
            voter={"weighted_archetype_id": "A"},
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_id="S",
            snapshot_date="2026-08-23",
        )
        report = audit_empirical_mind(
            mind,
            dimension_registry=self.dimensions,
            source_registry=self.sources,
            prior_pack=None,
            snapshot_date="2026-08-23",
            forecast_lambda=0.1,
        )
        self.assertFalse(report["gates"]["EM9_FORECAST_BOUNDARY_LAMBDA_ZERO_PREVALIDATION"])

    def test_environment_overlay_is_observed_only_and_never_scale_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            v8 = root / "v8"
            out = root / "v9"
            (v8 / "voter_batches" / "T").mkdir(parents=True)
            (v8 / "packets" / "T").mkdir(parents=True)
            (v8 / "as2_full_environment_prompt_v2.md").write_text("V8 prompt\n", encoding="utf-8")
            (v8 / "behavioral_mind_environment_manifest.json").write_text(
                json.dumps({
                    "status": "PASS_BEHAVIORAL_MIND_V8_ENVIRONMENT_READY",
                    "target_outcomes_present": False,
                    "base_named_environment_manifest_sha256": "abc",
                }),
                encoding="utf-8",
            )
            batch = {
                "territory_id": "T",
                "batch_id": "B01",
                "voter_archetypes": [
                    {
                        "weighted_archetype_id": "A001",
                        "political_interest": 0.8,
                        "voter_mind_state": {"schema_version": "V8"},
                    }
                ],
            }
            (v8 / "voter_batches" / "T" / "B01.json").write_text(json.dumps(batch), encoding="utf-8")
            (v8 / "packets" / "T" / "B01.json").write_text(
                json.dumps({"territory_id": "T", "batch_id": "B01", "voter_batch": batch}),
                encoding="utf-8",
            )
            manifest = build_empirical_environment(
                v8_root=v8,
                output_root=out,
                dimension_registry=self.dimensions,
                source_registry=self.sources,
                prior_pack=None,
                snapshot_date="2026-08-23",
                prompt_addendum_text="# Empirical Moroccan Mind V9 addendum\nDo not fabricate.",
            )
            self.assertEqual(
                manifest["status"],
                "PASS_EMPIRICAL_MIND_V9_OBSERVED_ONLY_DIAGNOSTIC_READY",
            )
            self.assertFalse(manifest["scale_allowed"])
            self.assertFalse(manifest["calibrated_prior_pack_present"])
            overlaid = json.loads((out / "voter_batches" / "T" / "B01.json").read_text())
            self.assertIn("empirical_moroccan_mind", overlaid["voter_archetypes"][0])
            self.assertIn(
                "Empirical Moroccan Mind V9 addendum",
                (out / "as2_full_environment_prompt_v2.md").read_text(),
            )


if __name__ == "__main__":
    unittest.main()

"""The R2 outputs committed to the repo are the ones CI measured.

R2 ran inside the population build job, because the population it needs is an
Actions artifact and downloading one requires a signed-in session. Its outputs
were then downloaded once and committed, so R3 can be built from a frozen HEAD
without anybody needing that session again.

Committing a derived artifact is only worth anything if the copy can be shown to
be the measured one. The measurement records the digests it computed; these
tests recompute them from the committed bytes. If someone edits the bridged
input by hand, or refreshes one file from a later run without the others, the
digests stop agreeing and this fails.
"""

from __future__ import annotations

import json
import pathlib
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from morocco26.agent_society_v4.rich_named_bridge_v1 import sha256_json  # noqa: E402

DATA = REPO_ROOT / "morocco26" / "data" / "goal100" / "agent_society_v2"
MEASUREMENT = DATA / "P3_R2_MEASUREMENT_AIN_CHOCK_V1.json"
BRIDGED = DATA / "named_input_rich_ain_chock_2026.json"
CERTIFICATE = DATA / "P3_DATA_LAYER_CERTIFICATE_RICH_AIN_CHOCK_V1.json"
BRIDGE_CERTIFICATE = DATA / "RICH_NAMED_BRIDGE_CERTIFICATE_AIN_CHOCK_V1.json"
POPULATION_CERTIFICATE = DATA / "CURRENT_POPULATION_2026_CERTIFICATE_V1.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class CommittedOutputsMatchTheMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.measurement = read(MEASUREMENT)

    def test_the_bridged_named_input_is_the_measured_one(self):
        self.assertEqual(
            sha256_json(read(BRIDGED)), self.measurement["bridged_named_input_sha256"]
        )

    def test_the_data_layer_certificate_is_the_measured_one(self):
        self.assertEqual(
            sha256_json(read(CERTIFICATE)), self.measurement["data_layer_certificate_sha256"]
        )

    def test_the_bridge_certificate_is_the_measured_one(self):
        self.assertEqual(
            sha256_json(read(BRIDGE_CERTIFICATE)),
            self.measurement["bridge_certificate_sha256"],
        )

    def test_the_population_itself_is_named_but_not_committed(self):
        """91.6 MB has no business in a git history; its digest does."""
        self.assertEqual(len(self.measurement["produced_population_sha256"]), 64)
        self.assertEqual(self.measurement["produced_population_bytes"], 91588370)
        self.assertFalse((DATA / "2026_current_population_v1.json").exists())


class TheMeasurementSaysWhatItMeasuredTests(unittest.TestCase):
    """The numbers R3 is authorized against, pinned so they cannot drift quietly."""

    def setUp(self):
        self.measurement = read(MEASUREMENT)

    def test_the_observed_count_replaced_the_fixture_count(self):
        self.assertEqual(self.measurement["dimensions_per_voter"], 121)
        observed = self.measurement["mean_populated_dimensions_per_voter"]
        self.assertGreater(observed, 0)
        self.assertLess(observed, 30, "the fixture's 30 came with an attitude overlay this has not")

    def test_the_stratum_layer_is_absent_and_declared_absent(self):
        self.assertEqual(self.measurement["survey_stratum_fields_per_voter"], 0)
        self.assertTrue(self.measurement["no_attitude_overlay_for_2026"])
        self.assertEqual(self.measurement["epistemic_totals"]["SURVEY_STRATUM_PRIOR"], 0)

    def test_the_rich_voter_state_reads_partial_not_real(self):
        """Every voter has individual and household blocks, none has a stratum block."""
        self.assertEqual(self.measurement["layer_states"]["RICH_VOTER_STATE"], "PARTIAL_REAL")

    def test_no_political_memory_reached_the_voters(self):
        self.assertEqual(self.measurement["epistemic_totals"]["ENGINE_DERIVED_COMPOSITE"], 0)
        self.assertFalse(self.measurement["population_prior_relabelled_as_individual_fact"])
        certificate = read(POPULATION_CERTIFICATE)
        self.assertFalse(certificate["prior_election_raking_dimension"])
        self.assertFalse(certificate["historical_outcome_read"])
        self.assertFalse(certificate["sealed_mapping_read"])
        self.assertFalse(certificate["atlas_prior_reinjected"])
        self.assertEqual(certificate["political_memory_population_source"], "NONE")
        # These two gates pass when False; the plain fields above are the ones
        # that read as ordinary booleans.
        self.assertTrue(certificate["gates"]["no_political_memory_in_records"])
        self.assertTrue(certificate["gates"]["no_electoral_raking_dimension"])

    def test_only_the_local_ballot_was_simulated(self):
        self.assertEqual(self.measurement["ballots_simulated"], ["LOCAL"])
        self.assertEqual(self.measurement["regional_surface_status"], "MISSING")
        self.assertEqual(self.measurement["layer_states"]["REGIONAL_BALLOT"], "MISSING")


if __name__ == "__main__":
    unittest.main()

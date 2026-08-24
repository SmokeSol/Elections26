from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "morocco26" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import p3_verify_named_input as verifier  # noqa: E402

AS2 = REPO_ROOT / "morocco26" / "data" / "goal100" / "agent_society_v2"
NAMED_INPUT = AS2 / "named_input_current_vintage_2026-08-22.json"
LINEAGE = AS2 / "NAMED_INPUT_2026_LINEAGE_V1.json"
CENSUS = REPO_ROOT / "morocco26" / "data" / "candidate_ballot_cells_2026.json"
CERTIFICATE = AS2 / "P3_DATA_LAYER_CERTIFICATE_V1.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class NamedInputLineageTests(unittest.TestCase):
    """The named input is now committed, so the R0 lineage rule closes on itself.

    Three published artifacts record its sha256. If any of the four drifts, the
    question "which snapshot did we build from?" gets more than one answer again.
    """

    def test_the_committed_bytes_match_every_published_digest(self):
        digest = hashlib.sha256(NAMED_INPUT.read_bytes()).hexdigest()
        lineage = load(LINEAGE)
        self.assertEqual(digest, lineage["sha256"])
        self.assertEqual(digest, load(CERTIFICATE)["named_input_sha256"])
        self.assertEqual(digest, load(CENSUS)["named_input_sha256"])
        self.assertTrue(lineage["all_recorded_digests_agree"])

    def test_git_stores_the_exact_bytes(self):
        """A CRLF file without a -text attribute would be rewritten on commit."""
        relative = str(NAMED_INPUT.relative_to(REPO_ROOT)).replace("\\", "/")
        process = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{relative}"],
            capture_output=True,
            check=False,
        )
        if process.returncode:
            self.skipTest("named input not committed yet in this working copy")
        self.assertEqual(
            hashlib.sha256(process.stdout).hexdigest(), load(LINEAGE)["sha256"]
        )

    def test_gitattributes_protects_the_hashed_bytes(self):
        text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("named_input_current_vintage_*.json -text", text)

    def test_the_published_snapshot_carries_no_outcome(self):
        value = load(NAMED_INPUT)
        blob = json.dumps(value, ensure_ascii=False)
        for token in ("target_outcome", "seats_won", "sealed"):
            self.assertNotIn(token, blob)
        self.assertEqual(value["regime_gate"], "P3_CURRENT_VINTAGE_2026")
        self.assertEqual(len(value["territories"]), 92)

    def test_the_verifier_accepts_the_published_input(self):
        self.assertEqual(verifier.verify_named_input(NAMED_INPUT), 0)

    def test_the_verifier_refuses_other_bytes(self):
        import tempfile

        with tempfile.TemporaryDirectory() as holder:
            other = pathlib.Path(holder) / "other.json"
            other.write_bytes(NAMED_INPUT.read_bytes()[:2048])
            with self.assertRaises(verifier.NamedInputError):
                verifier.verify_named_input(other)

    def test_an_override_is_allowed_but_never_silent(self):
        import io
        import contextlib
        import tempfile

        with tempfile.TemporaryDirectory() as holder:
            other = pathlib.Path(holder) / "other.json"
            other.write_bytes(NAMED_INPUT.read_bytes()[:2048])
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(verifier.verify_named_input(other, override="12345"), 0)
            report = json.loads(buffer.getvalue())
            self.assertEqual(report["status"], "OVERRIDE_NAMED_INPUT_NOT_THE_PUBLISHED_SNAPSHOT")
            self.assertFalse(report["matches_published"])


class PopulationCertificateGateTests(unittest.TestCase):
    def _certificate(self, **overrides):
        certificate = {
            "status": "PASS_CURRENT_VINTAGE_POPULATION_2026",
            "historical_outcome_read": False,
            "prior_election_raking_dimension": False,
            "sealed_mapping_read": False,
            "atlas_prior_reinjected": False,
            "target_outcome_used": False,
            "dummy_unknown_marginal_used": False,
            "political_memory_population_source": "NONE",
            "territories": 92,
            "failures": [],
            "geometry_certificate": {"gate": "PASS", "territories": 92, "sha256": "a" * 64},
            "source_hashes": {"geometry_2026_certificate": "a" * 64},
            "demographic_projection_boundary": {
                "rgph2024_demographic_marginals_calibrated": False,
                "scale_or_forecast_population_use": "BLOCKED_UNTIL_RGPH2024_OR_EQUIVALENT_POSTSTRATIFICATION",
            },
        }
        certificate.update(overrides)
        return certificate

    def _write(self, certificate):
        import tempfile

        holder = tempfile.mkdtemp()
        path = pathlib.Path(holder) / "certificate.json"
        path.write_text(json.dumps(certificate), encoding="utf-8")
        return path

    def test_a_politically_empty_geometry_bound_certificate_passes(self):
        self.assertEqual(
            verifier.verify_population_certificate(self._write(self._certificate())), 0
        )

    def test_an_electoral_raking_dimension_is_refused(self):
        path = self._write(self._certificate(prior_election_raking_dimension=True))
        with self.assertRaises(verifier.NamedInputError):
            verifier.verify_population_certificate(path)

    def test_a_geometry_hash_mismatch_is_refused(self):
        path = self._write(self._certificate(source_hashes={"geometry_2026_certificate": "b" * 64}))
        with self.assertRaises(verifier.NamedInputError):
            verifier.verify_population_certificate(path)

    def test_dropping_the_demographic_boundary_is_refused(self):
        path = self._write(self._certificate(demographic_projection_boundary={}))
        with self.assertRaises(verifier.NamedInputError):
            verifier.verify_population_certificate(path)

    def test_an_uncalibrated_population_may_not_claim_rgph2024(self):
        path = self._write(
            self._certificate(
                demographic_projection_boundary={"rgph2024_demographic_marginals_calibrated": True}
            )
        )
        with self.assertRaises(verifier.NamedInputError):
            verifier.verify_population_certificate(path)


if __name__ == "__main__":
    unittest.main()

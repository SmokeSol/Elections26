from __future__ import annotations

import unittest

from morocco26.agent_society_v4.behavioral_realism import audit_rows, paired_delta


def row(i: int, *, local=None, regional=None, turnout=None, pov=None, legacy=False):
    if local is None:
        x = 0.20 + (i % 5) * 0.01
        local = {"PAM": x, "RNI": 0.45 - (i % 5) * 0.005, "PI": 1 - x - (0.45 - (i % 5) * 0.005)}
    if regional is None:
        y = 0.25 + (i % 4) * 0.01
        regional = {"PAM": 0.35, "RNI": y, "PI": 0.65 - y}
    value = {
        "weighted_archetype_id": f"A{i:03d}",
        "turnout_probability": turnout if turnout is not None else 0.25 + i * 0.015,
        "local_party_probabilities": local,
        "regional_party_probabilities": regional,
    }
    if legacy:
        value["observable_rationale"] = {"local_choice": "analyst"}
    else:
        value["pov_fr"] = pov or f"Je ne suis pas totalement décidé aujourd'hui; mon hésitation actuelle est propre à ma situation {i}."
    return value


class BehavioralRealismTests(unittest.TestCase):
    def test_old_style_degenerate_rows_fail_br1_and_br8(self):
        local = {"PAM": 0.2, "RNI": 0.4, "PI": 0.4}
        reg_a = {"PAM": 0.2, "RNI": 0.4, "PI": 0.4}
        reg_b = {"PAM": 0.4, "RNI": 0.2, "PI": 0.4}
        rows = [row(i, local=local, regional=reg_a if i < 24 else reg_b, legacy=True) for i in range(32)]
        report = audit_rows(rows)
        self.assertEqual(report["BR1_partisan_heterogeneity"]["status"], "FAIL_DEGENERATE_LOCAL")
        self.assertEqual(report["BR1_partisan_heterogeneity"]["unique_local_probability_vectors"], 1)
        self.assertEqual(report["BR1_partisan_heterogeneity"]["unique_regional_probability_vectors"], 2)
        self.assertEqual(report["BR8_pov_fidelity"]["status"], "FAIL_LEGACY_ANALYST_RATIONALE")
        self.assertFalse(report["pilot_pass"])
        self.assertFalse(report["scale_allowed"])

    def test_diverse_first_person_rows_pass_pilot_not_scale(self):
        report = audit_rows([row(i) for i in range(32)])
        self.assertEqual(report["BR0_integrity"]["status"], "PASS")
        self.assertEqual(report["BR1_partisan_heterogeneity"]["status"], "PASS_NONDEGENERATE")
        self.assertEqual(report["BR6_turnout_mechanism"]["status"], "PASS_NONDEGENERATE")
        self.assertEqual(report["BR8_pov_fidelity"]["status"], "PASS")
        self.assertTrue(report["pilot_pass"])
        self.assertFalse(report["scale_allowed"])

    def test_research_ontology_in_pov_fails(self):
        rows = [row(i) for i in range(32)]
        rows[0]["pov_fr"] = "Je penche pour le PAM parce que policy_program_fit me paraît élevé."
        report = audit_rows(rows)
        self.assertEqual(report["BR8_pov_fidelity"]["status"], "FAIL_RESEARCH_ONTOLOGY_IN_VOICE")

    def test_non_first_person_pov_fails(self):
        rows = [row(i) for i in range(32)]
        rows[0]["pov_fr"] = "Le votant hésite entre plusieurs partis et pourrait participer au scrutin."
        report = audit_rows(rows)
        self.assertEqual(report["BR8_pov_fidelity"]["status"], "FAIL_NOT_FIRST_PERSON")

    def test_paired_delta_uses_exact_archetype_pairing(self):
        base = [row(i) for i in range(4)]
        treatment = []
        for item in base:
            changed = dict(item)
            p = dict(item["local_party_probabilities"])
            p["PAM"] += 0.05
            p["RNI"] -= 0.05
            changed["local_party_probabilities"] = p
            treatment.append(changed)
        report = paired_delta(base, treatment, ballot="LOCAL", party_id="PAM")
        self.assertEqual(report["archetypes"], 4)
        self.assertAlmostEqual(report["mean_probability_delta"], 0.05)
        self.assertEqual(report["nonzero_delta_rows"], 4)


if __name__ == "__main__":
    unittest.main()

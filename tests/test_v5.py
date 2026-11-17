import os, sys, unittest
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau import pricing, calendar_fr, booking  # noqa: E402
from fretrau.agents import costcheck, risk, decision, sourcing  # noqa: E402
from fretrau.carriers import CARRIERS  # noqa: E402

PK = calendar_fr.next_business_day(date.today() + timedelta(days=4))
BY = {c.id: c for c in CARRIERS}


def q(o="Lyon", d="Paris", mode="FTL", pal=33, kg=15000, opts=None):
    return pricing.build_quote(o, d, mode, pal, kg, opts or {}, PK)


class CostCheck(unittest.TestCase):
    def test_agrees_with_market_on_core_distances(self):
        for o, d in [("Lyon", "Paris"), ("Paris", "Lille"), ("Paris", "Rennes"), ("Lille", "Cologne")]:
            r = costcheck.review(q(o, d))
            self.assertTrue(r["applicable"])
            self.assertIsNone(r["warning"], f"{o}-{d} ratio {r['ratio']}")
            self.assertTrue(0.85 <= r["ratio"] <= 1.15, f"{o}-{d} {r['ratio']}")

    def test_not_applicable_ltl_and_long_haul(self):
        self.assertFalse(costcheck.review(q(mode="LTL", pal=4, kg=1500))["applicable"])
        self.assertFalse(costcheck.review(q("Paris", "Madrid"))["applicable"])

    def test_flags_a_mispriced_quote(self):
        quote = q()
        quote.carrier_cost_estimate = quote.carrier_cost_estimate * 0.6     # tarif corrompu / obsolète
        self.assertIn("sous-évaluation", costcheck.review(quote)["warning"])

    def test_bottom_up_increases_with_distance(self):
        a, b = costcheck.bottom_up_cost(200)["total"], costcheck.bottom_up_cost(600)["total"]
        self.assertGreater(b, 2 * a * 0.9)


class Risk(unittest.TestCase):
    def ranked(self):
        r, _ = sourcing.rank(q(), PK, top_n=13)
        return r

    def test_value_above_cover_excludes_carrier(self):
        kept, rej, _ = risk.filter_candidates(self.ranked(), BY, 100000.0, 15000)
        names = {r["carrier"] for r in rej}
        self.assertTrue(all(BY[c["carrier_id"]].insurance_cover_eur >= 100000 for c in kept))
        self.assertIn("Garonne Routier (démo)", names)

    def test_no_value_no_exclusion(self):
        kept, rej, _ = risk.filter_candidates(self.ranked(), BY, None, 15000)
        self.assertEqual(rej, [])

    def test_value_per_kg_alert(self):
        _, _, alerts = risk.filter_candidates(self.ranked(), BY, 20000.0, 20)
        self.assertTrue(alerts)


class Decision(unittest.TestCase):
    def test_chosen_has_lowest_expected_cost_among_accepted(self):
        quote = q()
        ranked, _ = sourcing.rank(quote, PK)
        d = decision.choose(quote, ranked, BY)
        acc = [r for r in d["table"] if r["accepted"]]
        self.assertGreaterEqual(len(acc), 2)
        best_row, _ = d["best"]
        self.assertEqual(best_row["expected_cost"], min(r["expected_cost"] for r in acc))

    def test_unreliable_cheap_carrier_can_lose(self):
        # à prix quasi égal, la ponctualité départage : coût attendu plus bas pour le plus fiable
        self.assertLess(decision.expected_cost(1000, 0.97, 0.5), decision.expected_cost(995, 0.88, 0.5))

    def test_never_buys_above_ceiling(self):
        for o, d in [("Lyon", "Paris"), ("Lille", "Marseille"), ("Paris", "Strasbourg")]:
            quote = q(o, d)
            out = booking.run(quote.__dict__ if hasattr(quote, "__dict__") else quote, PK)
            if out["status"] == "confirmed":
                self.assertLessEqual(out["price"], quote.price_ht / (1 + pricing.MIN_MARGIN) + 0.01)

    def test_robustness_reports_stability(self):
        r = decision.robustness(q(), PK)
        self.assertEqual(set(r["winners"]), set(decision.SCENARIOS))
        self.assertTrue(0 < r["stability"] <= 1)


class Orchestration(unittest.TestCase):
    def run_booking(self, value=None, **kw):
        quote = q(**kw)
        return quote, booking.run(quote.__dict__, PK, None, value)

    def test_log_contains_all_agent_outputs(self):
        quote, out = self.run_booking()
        self.assertEqual(out["status"], "confirmed")
        for k in ("cost_crosscheck", "robustness", "decision", "rejected_by_risk", "alerts"):
            self.assertIn(k, out["log"])
        self.assertEqual(out["log"]["decision"]["chosen"], out["carrier"].name)

    def test_insured_value_filters_candidates_end_to_end(self):
        _, out = self.run_booking(value=200000.0)
        if out["status"] == "confirmed":
            self.assertGreaterEqual(out["carrier"].insurance_cover_eur, 200000.0)

    def test_value_above_every_cover_escalates(self):
        _, out = self.run_booking(value=29000.0 * 1)   # sous le seuil global mais...
        self.assertIn(out["status"], ("confirmed", "pending_human"))
        _, out2 = self.run_booking(value=40000.0)      # au-dessus du seuil de forte valeur : humain
        self.assertEqual(out2["status"], "pending_human")


if __name__ == "__main__":
    unittest.main()

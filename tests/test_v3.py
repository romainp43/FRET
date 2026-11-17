import os
import sys
import unittest
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")

from fretrau import calendar_fr, calibration, geo, pricing, tariff  # noqa: E402
from fretrau.agents import compliance, sourcing  # noqa: E402
from fretrau.carriers import CARRIERS  # noqa: E402

PICKUP = calendar_fr.next_business_day(date.today() + timedelta(days=3))


def q(o="Lyon", d="Paris", mode="FTL", pallets=33, kg=18000, opts=None, **kw):
    return pricing.build_quote(o, d, mode, pallets, kg, opts, pickup=PICKUP, **kw)


class TestTariff(unittest.TestCase):
    def test_loaded_tariff_valid(self):
        t = tariff.load()
        self.assertTrue(1.0 < t["market_index"]["eur_per_km"] < 3.0)
        self.assertEqual(t["fuel"]["weight"], 0.209)

    def test_validation_rejects_bad_tariff(self):
        import copy
        t = copy.deepcopy(tariff.load())
        t["market_index"]["eur_per_km"] = 50
        with self.assertRaises(tariff.TariffError):
            tariff.validate(t)
        t = copy.deepcopy(tariff.load())
        t["ftl"]["distance_band_multipliers"][0]["max_km"] = 9999
        with self.assertRaises(tariff.TariffError):
            tariff.validate(t)
        t = copy.deepcopy(tariff.load())
        t["margin"]["minimum"] = 0.3
        with self.assertRaises(tariff.TariffError):
            tariff.validate(t)

    def test_freshness_warning(self):
        t = tariff.load()
        old = date.fromisoformat(t["market_index"]["as_of"]) + timedelta(days=100)
        self.assertTrue(any("Indice marché" in w for w in tariff.freshness_warnings(t, old)))


class TestMarketAnchors(unittest.TestCase):
    """Le modèle doit rester dans les fourchettes de marché relevées (T3 2026) : garde-fou contre les dérives."""

    def per_km(self, o, d):
        x = q(o, d)
        return x.carrier_cost_estimate / x.distance_km

    def test_paris_madrid_within_market_range(self):
        self.assertTrue(1.30 <= self.per_km("Paris", "Madrid") <= 1.55)      # relevé 1,36 à 1,48 €/km

    def test_lille_cologne_in_market_range(self):
        self.assertTrue(1.95 <= self.per_km("Lille", "Cologne") <= 2.30)     # Duisbourg-Lille 2,10 à 2,21 €/km

    def test_french_medium_haul_near_index(self):
        idx = tariff.load()["market_index"]["eur_per_km"]
        self.assertTrue(0.85 * idx <= self.per_km("Lyon", "Paris") <= 1.05 * idx)


class TestPricingProperties(unittest.TestCase):
    def test_longer_distance_costs_more_total(self):
        self.assertGreater(q("Paris", "Marseille").carrier_cost_estimate, q("Paris", "Lyon").carrier_cost_estimate)
        self.assertGreater(q("Paris", "Lyon").carrier_cost_estimate, q("Paris", "Rouen").carrier_cost_estimate)

    def test_symmetric(self):
        self.assertAlmostEqual(q("Lyon", "Paris").carrier_cost_estimate, q("Paris", "Lyon").carrier_cost_estimate, 2)

    def test_ltl_monotonic_in_pallets_and_weight(self):
        prev = 0
        for n in range(1, 13):
            c = q(mode="LTL", pallets=n, kg=n * 300).carrier_cost_estimate
            self.assertGreaterEqual(c, prev)
            prev = c
        self.assertGreater(q(mode="LTL", pallets=2, kg=1800).carrier_cost_estimate,
                           q(mode="LTL", pallets=2, kg=400).carrier_cost_estimate)     # poids payant 740 kg/palette

    def test_ltl_never_exceeds_ftl(self):
        for o, d in [("Lyon", "Paris"), ("Lille", "Marseille"), ("Paris", "Madrid")]:
            ftl = q(o, d).carrier_cost_estimate
            for n in (10, 20, 33):
                self.assertLessEqual(q(o, d, "LTL", n, n * 500).carrier_cost_estimate, ftl + 0.01)

    def test_options_monotone(self):
        base = q().carrier_cost_estimate
        for opt in ("adr", "temperature", "urgent", "tail_lift"):
            self.assertGreater(q(opts={opt: True}).carrier_cost_estimate, base, opt)

    def test_margin_identity(self):
        x = q()
        m = tariff.load()["margin"]
        expected = x.carrier_cost_estimate * (1 + m["target"] + m["risk_premium_share"] * x.uncertainty)
        self.assertAlmostEqual(x.price_ht, expected, delta=0.01)
        self.assertGreater(x.price_ht / x.carrier_cost_estimate, 1 + m["minimum"])

    def test_interval_contains_mid_and_widens(self):
        dom, intl, ch = q(), q("Lyon", "Madrid"), q("Lyon", "Zurich")
        for x in (dom, intl, ch):
            self.assertLess(x.cost_low, x.carrier_cost_estimate)
            self.assertGreater(x.cost_high, x.carrier_cost_estimate)
        self.assertLess(dom.uncertainty, intl.uncertainty)
        self.assertLess(intl.uncertainty, ch.uncertainty)

    def test_vat_and_totals(self):
        dom = q()
        self.assertAlmostEqual(dom.price_ttc, round(dom.price_ht * 1.2, 2), places=2)
        self.assertEqual(q("Lyon", "Madrid").vat, 0.0)

    def test_warnings(self):
        self.assertTrue(any("alpine" in w for w in q("Lyon", "Milan").warnings))
        self.assertTrue(any("Suisse" in w for w in q("Lyon", "Zurich").warnings))
        self.assertTrue(any("plafonné" in w for w in q(mode="LTL", pallets=33, kg=15000).warnings))

    def test_fuel_indexation(self):
        import copy
        t = copy.deepcopy(tariff.load())
        base = pricing.estimate_cost("FTL", "Lyon", "Paris", 33, 18000, {}, t)["mid"]
        t["fuel"]["index_now"] = t["fuel"]["index_ref"] * 1.10
        up = pricing.estimate_cost("FTL", "Lyon", "Paris", 33, 18000, {}, t)["mid"]
        self.assertAlmostEqual(up / base, 1 + 0.209 * 0.10, places=3)
        t["fuel"]["index_now"] = t["fuel"]["index_ref"] * 0.90
        self.assertLess(pricing.estimate_cost("FTL", "Lyon", "Paris", 33, 18000, {}, t)["mid"], base)

    def test_quote_records_tariff_version(self):
        self.assertEqual(q().tariff_version, tariff.load()["version"])

    def test_invalid_combo(self):
        with self.assertRaises(pricing.QuoteError):
            q(opts={"adr": True, "temperature": True})


class TestCalendar(unittest.TestCase):
    def test_easter_known_dates(self):
        self.assertEqual(calendar_fr.easter(2026), date(2026, 4, 5))
        self.assertEqual(calendar_fr.easter(2027), date(2027, 3, 28))

    def test_holidays_2026(self):
        h = calendar_fr.holidays(2026)
        for d in (date(2026, 4, 6), date(2026, 5, 14), date(2026, 5, 25), date(2026, 12, 25), date(2026, 11, 11)):
            self.assertIn(d, h)

    def test_weekend_pickup_rejected(self):
        saturday = date(2026, 11, 21)
        with self.assertRaises(pricing.QuoteError):
            pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000, None, pickup=saturday)

    def test_delivery_skips_weekend_and_holidays(self):
        self.assertEqual(calendar_fr.earliest_delivery(date(2026, 11, 20), 470).weekday() < 5, True)
        self.assertEqual(calendar_fr.earliest_delivery(date(2026, 11, 10), 100), date(2026, 11, 12))   # saute le 11/11
        self.assertEqual(calendar_fr.earliest_delivery(date(2026, 11, 20), 470), date(2026, 11, 23))   # vend. -> lundi

    def test_deadline_infeasible_suggests_express(self):
        pickup = date(2026, 11, 18)       # mercredi
        std = calendar_fr.earliest_delivery(pickup, 470, False)
        fast = calendar_fr.earliest_delivery(pickup, 470, True)
        self.assertLess(fast, std)
        with self.assertRaises(pricing.QuoteError) as cm:
            pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000, None, pickup=pickup, deliver_by=fast)
        self.assertIn("Express", str(cm.exception))
        ok = pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000, {"urgent": True}, pickup=pickup, deliver_by=fast)
        self.assertEqual(ok.earliest_delivery, fast.isoformat())


class TestEquipmentAndRanking(unittest.TestCase):
    def test_adr_requires_certified_carriers(self):
        x = q(opts={"adr": True})
        ranked, rejected = sourcing.rank(x, PICKUP, top_n=50)
        adr_ids = {c.id for c in CARRIERS if c.adr}
        self.assertTrue(ranked)
        self.assertTrue(all(r["carrier_id"] in adr_ids for r in ranked))
        self.assertTrue(any("ADR" in " ".join(r["reasons"]) for r in rejected))

    def test_temperature_requires_reefer(self):
        x = q(opts={"temperature": True})
        ranked, _ = sourcing.rank(x, PICKUP, top_n=50)
        self.assertTrue(all(next(c for c in CARRIERS if c.id == r["carrier_id"]).reefer for r in ranked))

    def test_tail_lift_requires_equipment(self):
        ok, reasons = compliance.check(CARRIERS[1], "FTL", "Lille", "Paris", PICKUP, {"tail_lift": True})
        self.assertFalse(ok)

    def test_tight_deadline_prefers_punctuality(self):
        x = pricing.build_quote("Lyon", "Paris", "FTL", 33, 18000, {}, pickup=date(2026, 11, 18))
        tight = sourcing.rank(x, date(2026, 11, 18), deliver_by=date.fromisoformat(x.earliest_delivery), top_n=50)[0]
        loose = sourcing.rank(x, date(2026, 11, 18), top_n=50)[0]
        self.assertTrue(tight[0]["tight_deadline"])
        self.assertFalse(loose[0]["tight_deadline"])
        self.assertGreaterEqual(tight[0]["reliability"], max(r["reliability"] for r in tight) - 0.03)


class TestCalibration(unittest.TestCase):
    def test_bias_detected_and_shrunk(self):
        import csv
        import tempfile
        rows = []
        for o, d in [("Lyon", "Paris"), ("Lyon", "Marseille"), ("Paris", "Lille"), ("Bordeaux", "Toulouse")] * 6:
            est = pricing.estimate_cost("FTL", o, d, 33, 18000, {})
            rows.append({"origin": o, "destination": d, "mode": "FTL", "pallets": 33, "weight_kg": 18000,
                         "actual_price_ht": round(est["mid"] * 1.15, 2)})
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        samples = calibration.load_samples(f.name)
        os.unlink(f.name)
        rep = calibration.evaluate(samples)
        self.assertAlmostEqual(rep["overall"]["bias_median_ratio"], 1.15, places=2)
        self.assertEqual(rep["overall"]["coverage"], 0.0)      # +15 % dépasse l'intervalle national (+/- 8 %, +3 % de marge quand la distance est estimée)
        for g in calibration.suggest(samples).values():
            self.assertTrue(1.0 < g["suggested_multiplier"] < 1.15)        # rétrécissement vers 1

    def test_small_bias_stays_inside_interval(self):
        samples = [{"origin": "Lyon", "destination": "Paris", "mode": "FTL", "pallets": 33, "weight_kg": 18000,
                    "options": {}, "actual": round(pricing.estimate_cost("FTL", "Lyon", "Paris", 33, 18000, {})["mid"] * 1.05, 2)}]
        self.assertEqual(calibration.evaluate(samples)["overall"]["coverage"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)

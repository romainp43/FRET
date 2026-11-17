import io, json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error, zipfile
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
os.environ.setdefault("FRETRAU_DB", ":memory:")
os.environ.setdefault("FRETRAU_ADMIN_PASSWORD", "mot-de-passe-de-test-long")
from fretrau import geo, places, pricing, calendar_fr  # noqa: E402
from fretrau.agents import intake  # noqa: E402
import import_places  # noqa: E402


def commune(nom, code, cps, lon, lat, pop, centre=True):
    c = {"nom": nom, "code": code, "codesPostaux": cps, "population": pop}
    if centre:
        c["centre"] = {"type": "Point", "coordinates": [lon, lat]}
    return c


# Jeu d'ESSAI au format exact de geo.api.gouv.fr (coordonnées approximatives, uniquement pour tester le code)
FR = [
    commune("Tence", "43236", ["43190"], 4.2850, 45.1000, 2800),
    commune("Sainte-Sigolène", "43220", ["43600"], 4.2430, 45.2290, 6200),
    commune("Monistrol-sur-Loire", "43135", ["43120"], 4.1741, 45.2955, 9000),
    commune("Saint-Martin", "01001", ["01700"], 5.0, 45.9, 300),
    commune("Saint-Martin", "69001", ["69400"], 4.7, 46.0, 900),
    commune("Saint-Martin", "38001", ["38000"], 5.7, 45.1, 1500),
    commune("Saint-Étienne", "42218", ["42000", "42100"], 4.3872, 45.4397, 172000),
    commune("Lyon", "69123", ["69001", "69002", "69003"], 4.8357, 45.7640, 520000),
    commune("Pour", "08000", ["08400"], 4.8, 49.5, 100),
    commune("Ajaccio", "2A004", ["20000"], 8.7, 41.9, 70000),          # Corse : exclue
    commune("Fort-de-France", "97209", ["97200"], -61.0, 14.6, 80000),  # outre-mer : exclue
    commune("Sans-Centre", "99999", ["99999"], 0, 0, 10, centre=False),  # sans coordonnées : ignorée
]


def geonames_line(gid, name, lat, lon, cc, pop):
    cols = [str(gid), name, name, "", str(lat), str(lon), "P", "PPL", cc] + [""] * 5 + [str(pop)] + [""] * 4
    return "\t".join(cols)


GN = "\n".join([
    geonames_line(2886242, "Köln", 50.9333, 6.95, "DE", 1000000),
    geonames_line(3117735, "Madrid", 40.4165, -3.7026, "ES", 3200000),
    geonames_line(3169070, "Roma", 41.8919, 12.5113, "IT", 2800000),
    geonames_line(2523920, "Palermo", 38.1157, 13.3615, "IT", 650000),     # Sicile : exclue
    geonames_line(2523119, "Cagliari", 39.2305, 9.1196, "IT", 150000),     # Sardaigne : exclue
    geonames_line(2988507, "Paris", 48.8534, 2.3488, "FR", 2100000),       # France : vient de geo.api.gouv.fr
    geonames_line(5128581, "New York", 40.7143, -74.006, "US", 8000000),   # pays non desservi : ignoré
    geonames_line(111, "Neustadt", 50.0, 8.0, "DE", 5000),
    geonames_line(222, "Neustadt", 52.0, 9.0, "DE", 9000),                 # nom en double
])


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cities500.txt", GN)
    return buf.getvalue()


class PlacesBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "places.db")
        cls.old = os.environ.get("FRETRAU_PLACES_DB")
        os.environ["FRETRAU_PLACES_DB"] = cls.path
        places.reset()
        cls.n = import_places.build(cls.path, json.dumps(FR).encode(), zip_bytes())

    @classmethod
    def tearDownClass(cls):
        places.reset()
        if cls.old is None:
            os.environ.pop("FRETRAU_PLACES_DB", None)
        else:
            os.environ["FRETRAU_PLACES_DB"] = cls.old
        places.reset()
        cls.tmp.cleanup()


class Import(PlacesBase):
    def test_exclusions_and_counts(self):
        # FR : 12 - Corse - outre-mer - sans centre = 9 ; Europe : Köln, Madrid, Roma, Neustadt x2 = 5
        self.assertEqual(self.n, 14)
        self.assertEqual(places.count(), 14)
        for banned in ("Ajaccio", "Fort-de-France", "Palermo", "Cagliari", "New York", "Sans-Centre"):
            self.assertEqual(places.by_name(banned), [], banned)

    def test_france_comes_from_communes_not_geonames(self):
        self.assertEqual(len(places.by_name("Paris")), 0)              # absent du jeu officiel d'essai, et GeoNames-FR ignoré
        self.assertTrue(places.by_name("Tence"))

    def test_labels_are_unique_and_disambiguated(self):
        labels = [r["label"] for r in places.search("saint martin", 10)]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(sorted(labels), ["Saint-Martin (01700)", "Saint-Martin (38000)", "Saint-Martin (69400)"])
        de = sorted(r["label"] for r in places.by_name("Neustadt"))
        self.assertEqual(len(de), 2)
        self.assertTrue(all(l.startswith("Neustadt (DE #") for l in de))

    def test_search_is_accent_dash_saint_insensitive(self):
        for q in ("monistrol", "MONISTROL-SUR", "monistrol sur loire"):
            self.assertEqual(places.search(q)[0]["label"], "Monistrol-sur-Loire", q)
        for q in ("st etienne", "saint-etienne", "Saint Étienne", "ST-ETIENNE"):
            self.assertTrue(any(r["label"].startswith("Saint-Étienne") for r in places.search(q)), q)

    def test_search_by_postal_code(self):
        self.assertEqual([r["label"] for r in places.search("43120")], ["Monistrol-sur-Loire"])
        self.assertIn("Saint-Étienne", [r["label"] for r in places.search("42100")])

    def test_ordering_by_population(self):
        r = places.search("saint", 10)
        pops = [x["pop"] for x in r]
        self.assertEqual(pops, sorted(pops, reverse=True))

    def test_atomic_reimport_replaces_data(self):
        p2 = os.path.join(self.tmp.name, "other.db")
        n = import_places.build(p2, json.dumps(FR[:1]).encode(), None)
        self.assertEqual(n, 1)
        places.reset()


class Resolution(PlacesBase):
    def test_unique_plain_name(self):
        self.assertEqual(geo.canonical("tence"), "Tence")
        self.assertEqual(geo.canonical("  SAINTE-SIGOLENE "), "Sainte-Sigolène")

    def test_ambiguous_name_asks_for_precision(self):
        with self.assertRaises(places.PlaceError) as cm:
            geo.canonical("Saint-Martin")
        self.assertEqual(len(cm.exception.suggestions), 3)
        self.assertEqual(geo.canonical("Saint-Martin 01700"), "Saint-Martin (01700)")
        self.assertEqual(geo.canonical("01700"), "Saint-Martin (01700)")

    def test_unknown_has_suggestions_or_clear_message(self):
        with self.assertRaises(places.PlaceError) as cm:
            geo.canonical("Atlantis")
        self.assertIn("introuvable", str(cm.exception))

    def test_seed_city_still_wins_and_no_duplicate_in_suggestions(self):
        labels = [s["label"] for s in geo.suggest("lyon")]
        self.assertEqual(labels.count("Lyon"), 1)
        self.assertNotIn("Lyon (69001)", labels)

    def test_any_commune_can_be_quoted(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4))
        q = pricing.build_quote("Tence", "Sainte-Sigolène", "LTL", 2, 800, {}, pk)
        self.assertGreater(q.price_ht, 0)
        self.assertGreater(q.distance_km, 5)
        q2 = pricing.build_quote("Tence", "Köln (DE)", "FTL", 33, 15000, {}, pk)
        self.assertGreater(q2.distance_km, 500)
        self.assertGreater(q2.price_ht, q.price_ht)
        q3 = pricing.build_quote("Saint-Martin (01700)", "Madrid (ES)", "FTL", 33, 15000, {}, pk)
        self.assertGreater(q3.distance_km, 800)

    def test_commune_to_seed_symmetry(self):
        a, b = geo.road_km("Tence", "Lyon"), geo.road_km("Lyon", "Tence")
        self.assertEqual(a, b)
        self.assertTrue(40 < a < 120)


class IntakeCommunes(PlacesBase):
    TODAY = date(2026, 11, 17)

    def p(self, t):
        return intake.parse(t, self.TODAY)

    def test_small_communes_from_free_text(self):
        r = self.p("Bonjour, de Tence à Sainte-Sigolène, 2 palettes, 800 kg, demain. Merci")
        self.assertTrue(r["complete"], r)
        self.assertEqual((r["fields"]["origin"], r["fields"]["destination"]), ("Tence", "Sainte-Sigolène"))

    def test_stopword_communes_are_not_mistaken_for_places(self):
        r = self.p("Pour un camion complet de Tence vers Lyon, 10 tonnes, demain")     # « Pour » est une vraie commune
        self.assertTrue(r["complete"], r)
        self.assertEqual((r["fields"]["origin"], r["fields"]["destination"]), ("Tence", "Lyon"))

    def test_postal_code_disambiguates(self):
        r = self.p("de 69400 Saint-Martin vers Lyon, 5 tonnes, camion complet, demain")
        self.assertTrue(r["complete"], r)
        self.assertEqual(r["fields"]["origin"], "Saint-Martin (69400)")

    def test_ambiguous_commune_asks_for_postal_code(self):
        r = self.p("de Saint-Martin vers Lyon, 5 tonnes, camion complet, demain")
        self.assertFalse(r["complete"])
        self.assertIn("code postal", r["ambiguity"])

    def test_german_town_by_local_name(self):
        r = self.p("de Tence à Köln, 10 tonnes camion complet demain")
        self.assertEqual(r["fields"]["destination"], "Cologne")      # grande ville intégrée sous son nom habituel


class Api(PlacesBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import server
        cls.server = server
        cls.httpd = server.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        super().tearDownClass()

    def setUp(self):
        for rl in (self.server.RL_QUOTE, self.server.RL_GLOBAL, self.server.RL_TRACK):
            rl.hits.clear()

    def call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method, headers={"Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_autocomplete_endpoint(self):
        s, r = self.call("GET", "/api/places?q=sainte-sig")
        self.assertEqual(s, 200)
        self.assertTrue(r["complete"])
        self.assertEqual(r["results"][0]["label"], "Sainte-Sigolène")
        self.assertEqual(self.call("GET", "/api/places?q=a")[1]["results"], [])       # trop court : rien

    def test_quote_accepts_free_text_commune(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, q = self.call("POST", "/api/quote", {"origin": "tence", "destination": "Sainte-Sigolène", "mode": "LTL", "pallets": 2,
                                                  "weight_kg": 800, "pickup_date": pk, "options": {}})
        self.assertEqual(s, 200, q)
        self.assertEqual((q["origin"], q["destination"]), ("Tence", "Sainte-Sigolène"))

    def test_ambiguous_commune_returns_suggestions(self):
        pk = calendar_fr.next_business_day(date.today() + timedelta(days=4)).isoformat()
        s, e = self.call("POST", "/api/quote", {"origin": "Saint-Martin", "destination": "Lyon", "mode": "FTL", "pallets": 33,
                                                  "weight_kg": 15000, "pickup_date": pk, "options": {}})
        self.assertEqual(s, 422)
        self.assertEqual(len(e["suggestions"]), 3)

    def test_coverage_flag_complete(self):
        s, r = self.call("GET", "/api/cities")
        self.assertTrue(r["coverage"]["complete"])


class WithoutReferential(unittest.TestCase):
    def test_limited_coverage_is_announced_not_hidden(self):
        old = os.environ.get("FRETRAU_PLACES_DB")
        os.environ["FRETRAU_PLACES_DB"] = "/nonexistent/places.db"
        places.reset()
        try:
            self.assertFalse(places.available())
            with self.assertRaises(places.PlaceError) as cm:
                geo.canonical("Tence")
            self.assertIn("référentiel complet", str(cm.exception))
            self.assertEqual(geo.canonical("lyon"), "Lyon")                 # les grandes villes marchent toujours
        finally:
            if old is None:
                os.environ.pop("FRETRAU_PLACES_DB", None)
            else:
                os.environ["FRETRAU_PLACES_DB"] = old
            places.reset()


if __name__ == "__main__":
    unittest.main()

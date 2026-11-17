#!/usr/bin/env python3
"""Banc d'essai de l'agent de lecture d'e-mails (intake) : un corpus étiqueté, une note par champ.

  python3 tools/eval_intake.py            # rapport complet
  python3 tools/eval_intake.py --fail     # code de sortie 1 si l'exactitude globale < 97 %

Le corpus mélange des cas rédigés à la main (pièges : négations, citations d'e-mails, mois en lettres, abréviations)
et des cas générés (gabarits x villes x formats de poids/dates). Il est ÉCRIT PAR NOUS : il mesure les régressions et
les angles morts connus, pas la performance sur de vrais e-mails de clients (à compléter avec des e-mails réels anonymisés).
"""
import random
import sys
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fretrau.agents import intake  # noqa: E402

TODAY = date(2026, 11, 17)          # mardi
D = lambda s: s  # noqa: E731


def case(text, origin=None, destination=None, mode=None, weight=None, pallets=None, pickup=None, options=(), complete=True, missing=None):
    return {"text": text, "origin": origin, "destination": destination, "mode": mode, "weight": weight, "pallets": pallets,
            "pickup": pickup, "options": set(options), "complete": complete, "missing": missing}


HAND = [
    case("Bonjour, je dois envoyer 3 palettes de Lyon à Lille le 25/11. Poids 1,2 t. Merci", "Lyon", "Lille", "LTL", 1200, 3, "2026-11-25"),
    case("Camion complet Paris -> Marseille, 24t, enlèvement demain. Hayon non requis.", "Paris", "Marseille", "FTL", 24000, None, "2026-11-18"),
    case("Sans ADR : 10 palettes Nantes → Toulouse, 800 kg, vendredi.", "Nantes", "Toulouse", "LTL", 800, 10, "2026-11-20"),
    case("Chargement à Bordeaux, livraison à Lyon, 6 palettes, 2 tonnes, le 3 décembre", "Bordeaux", "Lyon", "LTL", 2000, 6, "2026-12-03"),
    case("Départ Strasbourg pour Milan, camion complet, 18 tonnes, le 1er décembre", "Strasbourg", "Milan", "FTL", 18000, None, "2026-12-01"),
    case("Bonjour,\nMerci pour votre dernier prix.\nNouvelle demande : Lille vers Rotterdam, 20 palettes, 9 000 kg, mardi 24 novembre.\nCordialement",
         "Lille", "Rotterdam", "FTL", 9000, 20, "2026-11-24"),
    case("Besoin d'un camion frigorifique (+2/+6) de Rennes à Nantes demain, 12 palettes, 6 t", "Rennes", "Nantes", "LTL", 6000, 12, "2026-11-18", ["temperature"]),
    case("Transport urgent de 2 palettes de Dijon à Paris, 400 kg, demain avec hayon", "Dijon", "Paris", "LTL", 400, 2, "2026-11-18", ["urgent", "tail_lift"]),
    case("Merci de nous coter Lyon -> Munich, 33 palettes europe, 22,5 tonnes, enlèvement le 02/12/2026", "Lyon", "Munich", "FTL", 22500, 33, "2026-12-02"),
    case("Salut, 1 palette de 600kg Nice > Marseille après-demain", "Nice", "Marseille", "LTL", 600, 1, "2026-11-19"),
    case("Un plateau pour du matériel : Metz - Lyon, 15 t, camion complet, le 27/11", "Metz", "Lyon", "FTL", 15000, None, "2026-11-27", ["flatbed"]),
    case("> Le 10/11/2026, Paul a écrit :\n> Envoi du 12/11 à confirmer\n\nBonjour, merci de coter Toulouse vers Bordeaux, 4 palettes, 1 500 kg, le 20/11/2026",
         "Toulouse", "Bordeaux", "LTL", 1500, 4, "2026-11-20"),
    case("Matières dangereuses (ADR) : 5 palettes de Mulhouse à Lyon, 2 t, jeudi", "Mulhouse", "Lyon", "LTL", 2000, 5, "2026-11-19", ["adr"]),
    case("Pas de hayon nécessaire. 8 palettes Grenoble - Annecy 3 tonnes le 30/11", "Grenoble", "Annecy", "LTL", 3000, 8, "2026-11-30"),
    case("Cotation svp : Madrid → Lyon, camion complet, 12 000 kg, le 4 décembre", "Madrid", "Lyon", "FTL", 12000, None, "2026-12-04"),
    case("Nous voulons expédier du matériel de Lyon à Paris la semaine prochaine, 5 palettes, 2 t", "Lyon", "Paris", "LTL", 2000, 5, None, (), False, "date"),
    case("Bonjour, camion complet de Nantes à Rennes demain", "Nantes", "Rennes", "FTL", None, None, "2026-11-18", (), False, "poids"),
    case("Prix pour 3 palettes de 900 kg Lyon Paris demain svp", "Lyon", "Paris", "LTL", 900, 3, "2026-11-18"),
    case("Pouvez-vous organiser le transport de 24 palettes de papier, 12 tonnes, au départ de Reims à destination de Hambourg le 02.12", "Reims", "Hambourg", "FTL", 12000, 24, "2026-12-02"),
    case("Départ: Le Havre\nArrivée: Lyon\n14 palettes\n9,5 t\nDate: 26/11/2026", "Le Havre", "Lyon", "FTL", 9500, 14, "2026-11-26"),
    case("de St Etienne à Clermont-Ferrand, 2 palettes, 300 kg, demain", "Saint-Etienne", "Clermont-Ferrand", "LTL", 300, 2, "2026-11-18"),
    case("TRANSPORT LYON PARIS 7 PALETTES 3T LUNDI", "Lyon", "Paris", "LTL", 3000, 7, "2026-11-23"),
    case("Bonjour, groupage 2 palettes Marseille→Nice 500kg le 1er décembre, sans hayon", "Marseille", "Nice", "LTL", 500, 2, "2026-12-01"),
    case("Besoin d'un camion complet Lille - Paris, 20 t, enlèvement le 19 novembre, livraison au plus tard le 20/11", "Lille", "Paris", "FTL", 20000, None, "2026-11-19"),
]

# Second lot, rédigé APRÈS les premières corrections (cas « jamais vus ») : 11 cas sur 14 étaient réussis du premier coup,
# les 3 échecs (poids « 7/12, 24 000 kg », « camion plateau » sans « complet », « livrer à B depuis A ») ont été corrigés ensuite.
HAND2 = [
    case("Bonjour, nous aurions besoin de faire transporter 4 palettes (environ 1,8 tonne) depuis notre site de Tours jusqu'à Bordeaux. Enlèvement possible dès jeudi.", "Tours", "Bordeaux", "LTL", 1800, 4, "2026-11-19"),
    case("RE: devis\nBonjour,\nOk pour le tarif précédent. Pour la prochaine : Lyon→Genève, 2 palettes, 450 kg, lundi 30 novembre.", "Lyon", "Genève", "LTL", 450, 2, "2026-11-30"),
    case("Camion complet Madrid vers Paris pour le 7/12, 24 000 kg, merci de confirmer le tarif", "Madrid", "Paris", "FTL", 24000, None, "2026-12-07"),
    case("Hello, 1 palette 250 kg Paris Lille demain avec hayon svp", "Paris", "Lille", "LTL", 250, 1, "2026-11-18", ["tail_lift"]),
    case("Transport de matières dangereuses ADR, 3 palettes, 900 kg, de Marseille à Lyon, le 25 novembre", "Marseille", "Lyon", "LTL", 900, 3, "2026-11-25", ["adr"]),
    case("Nous cherchons un transporteur Nantes-Paris, 14 palettes, 7,5 T, express demain", "Nantes", "Paris", "FTL", 7500, 14, "2026-11-18", ["urgent"]),
    case("Bonjour, il me faut un prix pour Dijon -> Strasbourg 12 palettes 5 t, chargement le 24/11/26", "Dijon", "Strasbourg", "LTL", 5000, 12, "2026-11-24"),
    case("Merci de me chiffrer 33 palettes de Lille à Lyon, poids 20000 kg, départ le 1er décembre, arrivée le 3 décembre au plus tard", "Lille", "Lyon", "FTL", 20000, 33, "2026-12-01"),
    case("Prix pour un camion plateau Lyon Grenoble, 10 t, jeudi 26 novembre", "Lyon", "Grenoble", "FTL", 10000, None, "2026-11-26", ["flatbed"]),
    case("Besoin urgent ! 2 palettes Paris → Rouen, 300kg, aujourd'hui possible ?", "Paris", "Rouen", "LTL", 300, 2, None, ["urgent"], False, "date"),
    case("Bonjour, 8 palettes à livrer à Toulouse depuis Bordeaux, 3,2 tonnes, chargement mardi prochain", "Bordeaux", "Toulouse", "LTL", 3200, 8, "2026-11-24"),
    case("Cotation Lyon-Paris. 5 palettes. 2 tonnes. Merci.", "Lyon", "Paris", "LTL", 2000, 5, None, (), False, "date"),
    case("Pouvez-vous me donner un tarif pour un transport frigorifique 0°C/+4°C, Rennes → Lille, 18 palettes, 8000 kg, le 30/11 ?", "Rennes", "Lille", "FTL", 8000, 18, "2026-11-30", ["temperature"]),
    case("Hayon obligatoire. 3 palettes Nancy vers Metz, 700 kg, demain", "Nancy", "Metz", "LTL", 700, 3, "2026-11-18", ["tail_lift"]),
]

CITIES = ["Lyon", "Paris", "Marseille", "Lille", "Bordeaux", "Toulouse", "Nantes", "Strasbourg", "Rennes", "Dijon", "Grenoble", "Nancy",
          "Madrid", "Barcelone", "Milan", "Bruxelles", "Munich", "Cologne", "Rotterdam", "Metz", "Tours", "Reims"]
TEMPLATES = [
    "Bonjour, pouvez-vous me coter {o} → {d}, {load}, {when} ? Merci",
    "{o} - {d} : {load}, {when}",
    "Demande de prix de {o} vers {d}. {load}. Enlèvement {when}.",
    "Bonjour,\nNous avons un transport au départ de {o} à destination de {d}.\n{load}\nDate : {when}\nCordialement",
    "Cotation svp {o} > {d} {load} {when}",
    "Je souhaite expédier de {o} à {d} : {load} ({when}).",
]


def _weight_fmt(kg, rnd):
    t = kg / 1000
    return rnd.choice([f"{int(kg)} kg", f"{int(kg)}kg", f"{kg:,.0f} kg".replace(",", " ")] + ([f"{int(t)} tonnes", f"{int(t)} t", f"{int(t)}T"] if kg % 1000 == 0 else
                                                                                     [f"{str(t).replace('.', ',')} t"]))


def generated(n=60, seed=7):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        o, d = rnd.sample(CITIES, 2)
        ftl = rnd.random() < 0.45
        kg = rnd.choice([18000, 22000, 24000, 12000, 15000]) if ftl else rnd.choice([300, 450, 600, 800, 1200, 1500, 2400, 3000, 4500])
        pal = None if ftl and rnd.random() < 0.6 else (rnd.randint(20, 33) if ftl else rnd.randint(1, 8))
        if pal and kg > pal * 1000:
            kg = pal * 700
        load = []
        if ftl:
            load.append(rnd.choice(["camion complet", "un lot complet", "FTL"]))
        if pal:
            load.append(rnd.choice([f"{pal} palettes", f"{pal} pal", f"{pal} palettes europe"]) if pal > 1 else "1 palette")
        load.append(_weight_fmt(kg, rnd))
        when_kind = rnd.choice(["demain", "apres", "date", "iso", "month", "weekday"])
        if when_kind == "demain":
            when, pk = "demain", "2026-11-18"
        elif when_kind == "apres":
            when, pk = "après-demain", "2026-11-19"
        elif when_kind == "date":
            day = rnd.randint(20, 30)
            when, pk = f"le {day}/11", f"2026-11-{day:02d}"
        elif when_kind == "iso":
            day = rnd.randint(1, 15)
            when, pk = f"le 2026-12-{day:02d}", f"2026-12-{day:02d}"
        elif when_kind == "month":
            day = rnd.randint(2, 20)
            when, pk = f"le {day} décembre", f"2026-12-{day:02d}"
        else:
            name, pk = rnd.choice([("jeudi", "2026-11-19"), ("vendredi", "2026-11-20"), ("lundi", "2026-11-23")])
            when = name
        opts = []
        extra = ""
        r = rnd.random()
        if r < 0.15:
            extra, opts = " Avec hayon.", ["tail_lift"]
        elif r < 0.25:
            extra, opts = " Température dirigée.", ["temperature"]
        elif r < 0.33:
            extra, opts = " Sans hayon.", []
        elif r < 0.40:
            extra, opts = " Livraison express.", ["urgent"]
        text = rnd.choice(TEMPLATES).format(o=o, d=d, load=", ".join(load), when=when) + extra
        mode = "FTL" if ftl else "LTL"
        out.append(case(text, o, d, mode, kg, pal, pk, opts))
    return out


def corpus():
    return HAND + HAND2 + generated()


def compare(c, res):
    f, errs = res["fields"], {}
    if (f.get("origin") != c["origin"]) or (f.get("destination") != c["destination"]):
        errs["route"] = (f.get("origin"), f.get("destination"))
    if c["mode"] and f.get("mode") != c["mode"]:
        errs["mode"] = f.get("mode")
    if c["weight"] is not None and abs(f.get("weight_kg", -1) - c["weight"]) > 1:
        errs["weight"] = f.get("weight_kg")
    if c["weight"] is None and "weight_kg" in f:
        errs["weight"] = f.get("weight_kg")
    if c["pallets"] is not None and f.get("pallets") != c["pallets"]:
        errs["pallets"] = f.get("pallets")
    if c["pickup"] is None and "pickup_date" in f:
        errs["pickup"] = f.get("pickup_date")
    if c["pickup"] and f.get("pickup_date") != c["pickup"]:
        errs["pickup"] = f.get("pickup_date")
    if set(f.get("options", {})) != c["options"]:
        errs["options"] = set(f.get("options", {}))
    if res["complete"] != c["complete"]:
        errs["complete"] = res["complete"]
    if c["missing"] and not any(c["missing"] in m for m in res["missing"]):
        errs["missing"] = res["missing"]
    return errs


def evaluate(cases=None, today=TODAY):
    cases = cases or corpus()
    totals, fails, ok = {}, [], 0
    for c in cases:
        errs = compare(c, intake.parse(c["text"], today))
        for k in errs:
            totals[k] = totals.get(k, 0) + 1
        if errs:
            fails.append((c, errs))
        else:
            ok += 1
    return {"n": len(cases), "ok": ok, "accuracy": ok / len(cases), "errors_by_field": totals, "fails": fails}


if __name__ == "__main__":
    r = evaluate()
    print(f"Cas : {r['n']} — parfaits : {r['ok']} ({r['accuracy']:.1%}) — erreurs par champ : {r['errors_by_field']}")
    for c, e in r["fails"][:40]:
        print("-", c["text"].replace("\n", " | ")[:110], "→", e)
    if "--fail" in sys.argv and r["accuracy"] < 0.97:
        sys.exit(1)

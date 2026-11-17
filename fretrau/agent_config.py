"""Réglages des agents lus dans config/agents.json (produit par tools/train_agents.py). Supprimer le fichier = retour aux valeurs d'origine.

Chaque valeur est validée ; un réglage invalide est ignoré (le défaut s'applique) plutôt que de faire tomber la réservation.
"""
import json
import os
import sys

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "agents.json")


def _weights_ok(w):
    return isinstance(w, list) and len(w) == 4 and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in w) and abs(sum(w) - 1) < 0.02


MIN_TIGHT_RELIABILITY = 0.30   # règle métier : quand le délai est serré, la ponctualité pèse au moins 30 % (aucun réglage appris ne peut passer dessous)


def tight_ok(w_normal, w_tight):
    """Poids = (prix, proximité, note, ponctualité). En délai serré, la ponctualité doit peser au moins MIN_TIGHT_RELIABILITY et plus qu'en temps normal."""
    return w_tight[3] >= MIN_TIGHT_RELIABILITY and w_tight[3] >= w_normal[3]


def load(path=None):
    path = path or PATH
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        out = {"version": str(c.get("version", ""))}
        s = c.get("sourcing", {})
        if _weights_ok(s.get("weights_normal")) and _weights_ok(s.get("weights_tight")) and tight_ok(s["weights_normal"], s["weights_tight"]):
            out["weights_normal"], out["weights_tight"] = tuple(s["weights_normal"]), tuple(s["weights_tight"])
        d = c.get("decision", {})
        if isinstance(d.get("late_cost_ratio"), (int, float)) and 0 <= d["late_cost_ratio"] <= 1.5:
            out["late_cost_ratio"] = float(d["late_cost_ratio"])
        n = c.get("negotiation", {})
        o = n.get("offers")
        if isinstance(o, list) and len(o) == 4 and all(isinstance(x, (int, float)) and 0.7 <= x <= 1.2 for x in o) and o == sorted(o):
            out["offers"] = tuple(o)
        if isinstance(n.get("soft_target"), (int, float)) and 0.9 <= n["soft_target"] <= 1.15:
            out["soft_target"] = float(n["soft_target"])
        return out
    except FileNotFoundError:
        return {}
    except (ValueError, OSError, AttributeError) as e:
        print(f"[FRETRAU] config/agents.json ignoré : {e}", file=sys.stderr)
        return {}


CONFIG = load()

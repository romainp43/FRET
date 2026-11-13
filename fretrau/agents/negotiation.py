"""Agent de négociation tarifaire avec un transporteur.

- Les offres successives sont calculées par une stratégie déterministe, bornée par un
  plafond de prix qui garantit la marge minimale FRETRAU.
- Le LLM (optionnel) ne fait que rédiger le texte des messages (voir llm.py).
- En production, la réponse du transporteur arrive par e-mail/API : on en extrait UN montant,
  validé par du code (nombre, fourchette plausible). Le texte libre n'est jamais exécuté.
- Si aucun accord sous le plafond : escalade vers un humain (aucun engagement automatique).

Ici, le transporteur est SIMULÉ (prix de réserve déterministe) pour la démonstration.
"""
from .. import pricing
from . import llm

MAX_ROUNDS = 4


def _eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")


class SimulatedCarrierReply:
    """Simule un transporteur : prix de réserve = 96 % de son prix habituel, première demande +18 %."""

    def __init__(self, market_cost: float, price_factor: float):
        self.reservation = round(market_cost * price_factor * 0.96, 2)
        self.ask = round(self.reservation * 1.18, 2)

    def respond(self, offer: float) -> tuple[bool, float]:
        if offer >= self.reservation:
            return True, offer
        self.ask = round(max(self.reservation, self.ask - 0.5 * (self.ask - offer)), 2)
        return False, self.ask


def negotiate(quote, candidate: dict, carrier) -> dict:
    market = quote.carrier_cost_estimate
    ceiling = round(quote.price_ht / (1 + pricing.MIN_MARGIN), 2)   # prix d'achat max
    soft_target = round(market * 1.03, 2)                           # on accepte sans insister
    sim = SimulatedCarrierReply(market, carrier.price_factor)
    transcript = []

    def say(role, price, text):
        transcript.append({"role": role, "price": price, "text": text})

    ask_text = llm.draft(
        "Demande de prix pour un transport.",
        {"origin": quote.origin, "destination": quote.destination, "mode": quote.mode,
         "price_text": _eur(market * 0.90)},
        f"Bonjour, pouvez-vous prendre en charge {quote.origin} → {quote.destination} ({quote.mode}) "
        f"à {_eur(market * 0.90)} HT ?")
    say("fretrau", round(market * 0.90, 2), ask_text)

    offers = [market * 0.90, market * 0.94, market * 0.98, min(ceiling, market * 1.04)]
    counter = None
    for rnd, offer in enumerate(offers[:MAX_ROUNDS], start=1):
        offer = round(min(offer, ceiling), 2)
        accepted, counter = sim.respond(offer)
        if accepted:
            say("transporteur", offer, f"D'accord pour {_eur(offer)} HT.")
            return _result(True, offer, quote, transcript, rnd, ceiling)
        say("transporteur", counter, f"Je peux faire {_eur(counter)} HT.")
        if counter <= soft_target:
            say("fretrau", counter, f"Accepté à {_eur(counter)} HT.")
            return _result(True, counter, quote, transcript, rnd, ceiling)
        if rnd < MAX_ROUNDS:
            nxt = round(min(offers[rnd], ceiling), 2)
            say("fretrau", nxt, f"Je peux monter à {_eur(nxt)} HT.")

    return _result(False, counter, quote, transcript, MAX_ROUNDS, ceiling)


def _result(ok, price, quote, transcript, rounds, ceiling):
    margin = round(quote.price_ht - price, 2) if ok else None
    return {
        "accepted": ok, "price": price if ok else None, "rounds": rounds,
        "ceiling": ceiling, "margin_eur": margin,
        "margin_pct": round(margin / price * 100, 1) if ok else None,
        "escalate_to_human": not ok, "transcript": transcript,
    }

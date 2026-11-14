"""Agent de lecture des réponses : comprend ce qu'un transporteur a répondu à une offre, en texte libre.

Trois issues possibles, et rien d'autre :
  accept   « ok pour moi », « on prend »           -> il accepte NOTRE prix (jamais un prix tiré du texte) ;
  decline  « pas disponible », « complet »         -> l'offre est close, l'agent de surveillance relance ailleurs ;
  unclear  tout le reste                           -> un humain lit le message.
Un message qui contient un montant n'arrive jamais ici : il est traité comme une contre-proposition chiffrée.
Les règles décident d'abord ; le modèle de langage n'est consulté que si elles ne tranchent pas, et sa réponse
doit être l'un des trois mots ci-dessus. Il ne peut donc ni fixer un prix ni attribuer un transport hors cadre.
"""
import re
import unicodedata

from . import llm

_ANY_MONEY = re.compile(r"\d\s*(?:€|eur\b|euros?\b)", re.I)
_DECLINE = re.compile(r"\b(pas dispo\w*|indisponible|complet|impossible|pas interess\w*|non merci|ne peux pas|"
                      r"ne pouvons pas|ne peut pas|refus\w*|decline\w*|pas de camion|aucun camion|pas possible)\b")
_ACCEPT = re.compile(r"\b(ok|d accord|accepte|acceptons|on prend|je prends|nous prenons|c est bon|entendu|valide|"
                     r"confirme|confirmons|ca marche|bon pour accord)\b")
_NEGATION = re.compile(r"\b(ne|n|pas|non|sauf|mais|si|condition)\b")


def _fold(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9€ ]+", " ", text)


def classify(text: str) -> str:
    """accept | decline | unclear. Ne lit que le début du message (la réponse, pas l'historique cité)."""
    text = (text or "")[:600]
    if _ANY_MONEY.search(text):
        return "unclear"                       # un montant illisible ou multiple se traite à la main
    low = _fold(text)
    declined, accepted = bool(_DECLINE.search(low)), bool(_ACCEPT.search(low))
    if declined and not accepted:
        return "decline"
    if accepted and not declined and not _NEGATION.search(low):
        return "accept"
    if llm.available():
        got = llm.extract(text, {"intent": "accept si le transporteur accepte l'offre telle quelle, decline s'il la "
                                           "refuse ou n'est pas disponible, unclear dans tous les autres cas"})
        if got.get("intent") in ("accept", "decline"):
            return got["intent"]
    return "unclear"

"""Agent de triage des réclamations : priorité, preuves à réunir, prochaines étapes. Ne tranche jamais sur le fond (décision humaine)."""
from datetime import date

CHECKLIST = {
    "damage": ["Photos de la marchandise ET de l'emballage", "Récépissé de livraison avec réserves", "Facture de la marchandise", "Poids et nombre de colis avant/après"],
    "shortage": ["Récépissé avec réserve sur le nombre de colis", "Bon de livraison / liste de colisage", "Photos du chargement à l'arrivée"],
    "loss": ["Lettre de voiture", "Dernier jalon de suivi connu", "Facture de la marchandise"],
    "delay": ["Date et heure de livraison prévues et réelles", "Justificatif du préjudice (pénalités, arrêt de production)"],
    "other": ["Description détaillée", "Pièces justificatives"],
}


def triage(claim: dict, deadlines: dict, today: date = None) -> dict:
    today = today or date.today()
    left = (date.fromisoformat(deadlines["written_reserve_before"]) - today).days
    steps, priority = [], "normal"
    if left < 0:
        priority = "urgent"
        steps.append("Le délai de protestation écrite est dépassé : vérifier tout de suite si des réserves figurent sur le récépissé ; sinon avis juridique.")
    elif left <= 2:
        priority = "urgent"
        steps.append(f"Protestation motivée à envoyer au transporteur dans {left} jour(s) (lettre recommandée).")
    else:
        steps.append(f"Protestation écrite au transporteur avant le {deadlines['written_reserve_before']}.")
    if not claim.get("reserves_on_receipt"):
        steps.append("Aucune réserve sur le récépissé : le dossier est plus fragile, le signaler au client sans préjuger de l'issue.")
        priority = "urgent" if priority == "urgent" else "elevated"
    if claim.get("amount_eur") and claim["amount_eur"] >= 5000 and priority == "normal":
        priority = "elevated"
    steps.append("Transmettre la réclamation au transporteur et à son assureur avec les pièces ci-dessous.")
    return {"priority": priority, "days_left": left, "evidence": CHECKLIST.get(claim.get("kind"), CHECKLIST["other"]), "steps": steps}

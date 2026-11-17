# Entraînement et évaluation des agents FRETRAU

## Ce que « entraîner » signifie ici (et ce que cela ne signifie pas)

Aucune donnée réelle de transport n'existe encore : il n'y a ni historique de prix, ni transporteurs réels, ni clients. Il n'y a donc **pas d'apprentissage sur le marché**. Deux méthodes ont été utilisées :

1. **Réglage dans un simulateur de marché** (`fretrau/simulation.py`, `tools/train_agents.py`). Chaque « monde » tire au hasard des prix de réserve cachés pour les transporteurs, un écart entre prix affiché et vrai prix, une ponctualité réelle différente de l'affichée, un coût de retard inconnu. Les agents (classement, négociation, décision) y sont rejoués. On cherche les paramètres qui minimisent le **regret** : écart entre le coût obtenu et le meilleur choix possible connu du simulateur seul.
2. **Corpus de régression d'e-mails** (`tools/eval_intake.py`, 98 cas écrits à la main + générés). Sert à corriger et surveiller l'agent de saisie (négations, noms de mois, texte cité, dates, poids).

## Protocole (pour éviter l'auto-illusion)

- 800 jeux de paramètres tirés ; sélection sur 500 mondes d'entraînement ; confirmation sur 1 500 mondes de validation ; mesure finale sur 2 500 mondes de test jamais vus.
- Gain mesuré en **mondes appariés** (mêmes mondes, avant/après) avec erreur-type.
- Adoption seulement si le gain est significatif sur validation et test ; sinon `config/agents.json` n'est pas écrit.
- **Contrainte métier** : en délai serré, la ponctualité pèse au moins 30 % (validée aussi au chargement du fichier). Une première version, sans cette contrainte, avait réduit ce poids à presque zéro parce que le simulateur le permettait : le test existant l'a signalé et la règle a été ajoutée. Le gain est passé de 1,57 à 1,35 point.
- Un transporteur simulé peut refuser net une offre jugée insultante (92 % de son prix de réserve), pour ne pas surestimer le gain de la négociation.

## Résultats (dernier entraînement)

| Mesure | Valeur |
|---|---|
| Regret moyen, réglage d'origine (test, 2 500 mondes) | 7,39 % |
| Regret moyen, réglage retenu | 6,04 % |
| Gain apparié | 1,35 point ± 0,08 |
| Gain sur validation | 1,41 point |
| Taux d'accord de négociation | 99,5 % |
| Robustesse : pénalité de retard 30 % / 80 % | 6,93 → 5,85 / 7,04 → 6,11 |
| Agent de saisie e-mail, corpus de 98 cas | 98/98 |

## Limites à connaître

- Ces chiffres valent **sous les hypothèses du simulateur** (bruit des prix, comportement des transporteurs). Le marché réel peut les contredire. Ils ne prouvent ni une économie réelle de 1,35 % ni une précision de 100 % de la saisie : le corpus est écrit par le même auteur que l'agent (biais d'auto-évaluation).
- L'agent de saisie par règles n'est pas un modèle de langage ; un LLM optionnel (`agents/llm.py`) peut rédiger mais ne décide jamais d'un prix.
- Quand de vraies données existent : `tools/calibrate.py` recale les coefficients de coût ; `tools/train_agents.py` peut être relancé avec des prix de réserve réels ; tout nouveau réglage doit repasser le protocole ci-dessus.

## Agents utilisés

Conformité (`compliance`), sourcing, négociation, décision, risque (`risk`), second avis de coût (`costcheck`), saisie e-mail (`intake`), alignement de prix (`ratematch`), agent e-mail (`email_agent`), rédaction optionnelle (`llm`), demande de devis (`rfq`), garde anti-fraude (`guard`), veille (`watchtower`), triage des réclamations (`claims_triage`). Les contrôles de candidature transporteur (`vetting`, `verify_remote`) sont des règles, pas des agents.

## Relancer

    python3 tools/train_agents.py     # ~3 minutes, écrit config/agents.json si le gain est confirmé
    python3 tools/eval_intake.py --fail
    rm config/agents.json             # retour aux valeurs d'origine

## Banc d'essai du modèle de prix

`python3 tools/backtest_market.py` compare le prix d'achat estimé aux relevés publics de `data/market_benchmarks.json` (Upply/Ti/IRU T3 2026). Écart absolu moyen actuel : 7,3 % sur 4 liaisons (biais −6,9 %). Quatre liaisons ne prouvent rien de solide : le vrai recalage viendra des réponses des transporteurs (agent `rfq`).


## Mise à jour : réentraînement sur trajets élargis (communes réelles)
Le simulateur tire désormais ses trajets dans la base complète des lieux. Sur ce simulateur élargi, la recherche de paramètres (800 candidats) **n'a pas été adoptée** : gain test 0,0 point, gain validation −0,01. Les réglages livrés sont donc ceux de base (regret ≈ 5,87 %), sans gain revendiqué. Les chiffres 7,39 → 6,04 (+1,35) ci-dessus concernent l'ancien simulateur à 15 trajets et ne sont plus à présenter comme performance actuelle.

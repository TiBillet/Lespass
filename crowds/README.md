# Crowdfunding en mode Cascade

Voici le manifeste de Cascade.coop : https://www.cascade.coop/modele-economique-non-lucratif

# Résumé (merci LLM) :

## TL;DR

- Contribution adaptative → équilibre à l’intérieur d’une même cascade, pour ajuster les apports à un objectif partagé.
- Contribution cascade → équilibre entre plusieurs cascades, pour redistribuer les surplus et soutenir d’autres projets.

L’un régule horizontalement (entre personnes), l’autre verticalement (entre projets) — ensemble, ils forment une
économie contributive fluide et solidaire.

## 💧 Mode contribution cascade

- Principe : le surplus d’un financement (ce qui dépasse l’objectif prévu) ruisselle vers une autre cascade ou un autre
budget.

- Effet : le trop-perçu n’est jamais perdu ni capté, il alimente d’autres projets collectifs ou réduit d’éventuelles
dettes dans le réseau.

- Logique : solidarité et mutualisation — une cascade soutient les autres pour renforcer la résilience du système global.

→ Exemple : une cantine dépasse son budget du mois, le surplus finance un repas solidaire dans une autre cantine du
réseau.

## ⚖️ Mode contribution adaptative

- Principe : la contribution de chacun diminue à mesure que de nouveaux contributeurs rejoignent la cascade.

- Effet : le coût est réparti équitablement entre tous les participants selon l’objectif collectif, sans générer de
profit.

- Logique : ajustement dynamique — plus on est nombreux, moins chacun paie, dans un esprit de coopération économique.

→ Exemple : un festival vise 10 000 €. À 1000 participants, chacun paie 10 €. Si 2000 participants arrivent, chacun paie
5 €.

## Financement global : débranché (2026-09-30)

Le financement global (« contribuer au pot commun », route `global-funding`, bouton
« Je finance » de la page d'accueil Crowds) est débranché : jamais utilisé en production.
Il n'existe plus de route, de vue ni de bouton. Le modèle `GlobalFunding` et les champs
`CrowdConfig.global_funding_button` / `global_funding_button_text` restent en base
(leur retrait demande une migration).

The global funding feature (route, view, "Je finance" button) is disconnected: it was never
used in production. The `GlobalFunding` model and the two `CrowdConfig` button fields stay
in the database (removing them needs a migration).

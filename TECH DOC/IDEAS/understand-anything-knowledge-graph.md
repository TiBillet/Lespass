# Understand-Anything : knowledge graph interactif du codebase pour l'onboarding

## Source

- GitHub : https://github.com/Lum1104/Understand-Anything
- Découvert via la veille de Camille Roux (newsletter #49)

## Le problème

Lespass est un projet complexe : multi-tenant (django-tenants), multi-app Django
(BaseBillet, crowds, fedow_connect, fedow_core, laboutik, Administration, api_v2,
ApiBillet, AuthBillet, PaiementStripe, QrcodeCashless, wsocket), WebSocket,
Stripe, Celery, HTMX, plusieurs skins de templates.

Pour un nouveau contributeur, comprendre l'architecture prend du temps.
Les relations entre les modules ne sont pas évidentes à la lecture du code.
Le projet est coopératif — les contributeurs tournent, l'onboarding est récurrent.

## Ce que fait Understand-Anything

Un plugin Claude Code (et multi-plateforme) qui transforme un codebase en
**graphe de connaissances interactif** :

- Pipeline de 5 agents : scan → analyse fichiers → analyse architecture →
  génération de tours guidés → validation du graphe
- Chaque fichier, fonction, classe et dépendance = un nœud cliquable
- Explications en langage naturel générées par LLM sur chaque nœud
- Dashboard web interactif (React Flow) avec visualisation par couches
  architecturales (API, Service, Data, UI, Utility)
- Recherche fuzzy et sémantique ("comment fonctionne le paiement ?")
- Analyse d'impact des changements (`/understand-diff`)
- Guide d'onboarding auto-généré (`/understand-onboard`)
- Mises à jour incrémentales (ne ré-analyse que les fichiers modifiés)

## Pourquoi c'est pertinent pour TiBillet

1. **Onboarding des contributeurs coopératifs** — un nouveau contributeur
   pourrait visualiser les dépendances entre BaseBillet, crowds, fedow_connect,
   laboutik en quelques minutes au lieu de quelques jours

2. **Documentation vivante** — le graphe se met à jour avec le code, contrairement
   à une documentation markdown qui devient obsolète

3. **Compréhension des flux** — `/understand-chat "comment fonctionne le flux
   de paiement Stripe ?"` donnerait une réponse contextualisée avec les fichiers
   et fonctions impliqués

4. **Impact des changements** — `/understand-diff` avant un merge pour voir
   quels modules sont impactés par une PR

5. **Accessible aux non-dev** — les explications en langage naturel permettent
   aux membres non-techniques de la coopérative de comprendre l'architecture

## Installation

```bash
# Dans Claude Code
/plugin marketplace add Lum1104/Understand-Anything
/plugin install understand-anything

# Puis dans le projet Lespass
/understand
/understand-dashboard
```

## Points d'attention

- Le pipeline consomme des tokens LLM (scan complet d'un gros codebase = coûteux)
- Le graphe est stocké dans `.understand-anything/knowledge-graph.json` — à
  ajouter au `.gitignore` ou au contraire à versionner si on veut le partager
- Les mises à jour incrémentales limitent le coût après le scan initial
- Licence MIT — compatible avec notre usage

## Action proposée

Tester sur Lespass dans une session dédiée. Évaluer :
- La qualité des explications générées sur nos ViewSets et modèles
- La pertinence de la détection des couches architecturales
- L'utilité du guide d'onboarding auto-généré
- Le coût en tokens du scan initial

## Priorité

Basse — c'est un outil de confort, pas un fix de bug ou une amélioration de
performance. Mais le ROI sur l'onboarding pourrait être significatif si on
accueille régulièrement de nouveaux contributeurs.

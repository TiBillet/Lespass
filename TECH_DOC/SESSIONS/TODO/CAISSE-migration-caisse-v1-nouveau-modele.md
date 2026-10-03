# Caisse — migrer la caisse LaBoutik V1 sur le modèle Vente / Règlement

> **Statut** : idée, spec à écrire. Demande du mainteneur (2026-10-03), pendant le
> chantier 05 (ouverture de la fiche F). « Gros chantier », à faire plus tard.
> Pré-requis : chantier 05 terminé.

## Le but, en une phrase
Faire passer la caisse LaBoutik V1 sur le modèle du chantier 05 (`Vente`, articles en
centimes entiers, `Reglement`, une clôture et un FEC par lieu), pour qu'un lieu n'ait
plus qu'une comptabilité.

## Pourquoi
Aujourd'hui, l'argent encaissé par la V1 et déclaré à Lespass (webhook d'adhésion de
Fedow, « payé ailleurs » de l'API v2) est écrit comme une vente de Lespass **et** reste
dans la comptabilité de la V1. Le mainteneur l'accepte (2026-10-01, confirmé le
2026-10-03, question Q-F3 du chantier 05) en attendant cette migration.

## À préciser
- Le périmètre : ventes de la V1, clôtures, FEC, reprise de l'historique (voir la fiche
  `COMPTABILITE/CHANTIER-05-R-reprise-ventes.md`).
- L'ordre avec le sujet PRIORITÉ du kiosque et la charge en festival.

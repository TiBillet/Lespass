# INVENTAIRE — hub des chantiers

Hub permanent de l'app `inventaire/` : stock des produits de caisse et des fûts,
mouvements de stock, sections Stock de l'admin, badges de stock de la caisse.

Le stock a été construit dans `TECH_DOC/SESSIONS/LABOUTIK/DONE/Session 03 - Inventaire et stock/`.
La section Stock de la fiche produit est décrite dans
`A TESTER et DOCUMENTER/stock-onglet-produit.md`.

## Chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Désactiver le suivi de stock d'un produit (booléen `actif`) | Spec relue (Fable) et corrigée, à valider (D10) | [SPEC.md](SPEC.md) |
| 02 | Afficher ou masquer le stock sur la tuile de caisse (booléen `afficher_en_caisse`) | Spec écrite | [CHANTIER-02-afficher-en-caisse.md](CHANTIER-02-afficher-en-caisse.md) |

Les deux chantiers sont indépendants. Le 02 est le plus court et sans décision en attente.
Le premier livré prend la migration `inventaire 0002`, l'autre la `0003`.

## Ajouter un chantier

Créer `CHANTIER-NN-<slug>.md` dans ce dossier, puis ajouter une ligne au tableau.

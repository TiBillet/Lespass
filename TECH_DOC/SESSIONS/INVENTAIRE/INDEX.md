# INVENTAIRE — hub des chantiers

Hub permanent de l'app `inventaire/` : stock des produits de caisse et des fûts,
mouvements de stock, sections Stock de l'admin, badges de stock de la caisse.

Le stock a été construit dans `TECH_DOC/SESSIONS/LABOUTIK/DONE/Session 03 - Inventaire et stock/`.
La section Stock de la fiche produit est décrite dans
`A TESTER et DOCUMENTER/stock-onglet-produit.md`.

## Chantiers

| # | Chantier | Statut | Spec |
|---|---|---|---|
| 01 | Désactiver le suivi de stock d'un produit (booléen `actif`) | **Codé 2026-10-24, non commité** (migration `0003` appliquée en dev) — CHANGELOG `2026-10-24-stock-desactivation.md` | [SPEC.md](SPEC.md) |
| 02 | Afficher ou masquer le stock sur la tuile de caisse (booléen `afficher_en_caisse`) | **Codé 2026-10-24, non commité** (migration `0002` appliquée en dev) — CHANGELOG `2026-10-24-stock-afficher-en-caisse.md` | [CHANTIER-02-afficher-en-caisse.md](CHANTIER-02-afficher-en-caisse.md) |

Les deux chantiers sont indépendants. Migrations : `inventaire 0002` (chantier 02),
`inventaire 0003` (chantier 01).

## Ajouter un chantier

Créer `CHANTIER-NN-<slug>.md` dans ce dossier, puis ajouter une ligne au tableau.

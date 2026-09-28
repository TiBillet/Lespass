# Bouton « Synchroniser la TVA » d'une catégorie de caisse / "Synchronize VAT" button on a POS category

**Date :** 2026-09-28
**Migration :** Non

## Resume / Summary

**Quoi / What :** la fiche admin d'une catégorie de caisse qui a une TVA propose un bouton
« Synchroniser la TVA (X %) sur tous les articles ». Il ouvre une confirmation (« Êtes-vous
sûr ? ») qui explique l'effet et liste les articles dont la TVA change (actuelle → nouvelle).
« Confirmer » donne la TVA de la catégorie à **tous** ses articles (y compris une TVA choisie
exprès), puis recharge la page avec un message. L'aide du champ TVA d'un article dit la
vérité : la vente prend la TVA de l'article, sinon celle du lieu, jamais celle de la
catégorie. / A POS category page offers a button that copies the category VAT to all its
items, after an explained confirmation. The item VAT help text no longer promises
category inheritance.

**Pourquoi / Why :** la TVA d'une vente vient de l'article (`Product.tva`), sinon de la
configuration du lieu (`LigneArticle._compute_default_vat`) ; la « TVA par défaut » de la
catégorie n'est lue nulle part à la vente, alors que l'aide de l'admin promettait
« Même TVA que la catégorie si laissé vide ». Décision du mainteneur : pas d'héritage
automatique, un bouton explicite. / Category VAT is never used at sale time; maintainer
decision: an explicit button, no automatic inheritance.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `CategorieProductAdmin` : `change_form_before_template`, `get_urls()` (confirmation en GET, synchronisation en POST, CSRF, permission admin du lieu, `HX-Refresh`) ; `_articles_dont_la_tva_va_changer()` ; aide du champ TVA de `POSProductForm` |
| `Administration/templates/admin/categorie_product/synchroniser_tva_bouton.html` | nouveau : bouton (si la catégorie a une TVA) |
| `Administration/templates/admin/categorie_product/partials/synchroniser_tva_confirmation.html` | nouveau : confirmation expliquée, liste des articles qui changent, Confirmer / Annuler |
| `tests/pytest/test_synchronisation_tva_categorie.py` | nouveau : 7 tests (schéma dédié) |

Les ventes déjà enregistrées gardent leur TVA (chaque ligne de vente stocke la sienne).
La mise à jour passe par `QuerySet.update()` : pas de signal `post_save` produit (rien à
notifier pour un changement de TVA).

Avant correctif : 5 tests rouges sur 7. Mutations (6, toutes détectées) : bouton masqué,
confirmation listant tous les articles, synchronisation de toutes les catégories,
synchronisation acceptée en GET, pas de rechargement, aide promettant l'héritage.
`make test` 2080 passed.

**i18n** : « TVA appliquée à la vente de cet article. Vide : TVA par défaut du lieu (pas celle
de la catégorie). Pour donner à tous les articles la TVA de leur catégorie : bouton
« Synchroniser la TVA » de la catégorie. », « Synchroniser la TVA (%(taux)s %) sur tous les
articles », « Êtes-vous sûr ? Tous les articles de « %(nom)s » vont prendre la TVA de
%(taux)s %. », « %(nombre)s article dans la catégorie. » (pluriel), « Une TVA choisie exprès
sur un article est remplacée par celle de la catégorie. », « Les ventes déjà enregistrées
gardent leur TVA : seules les prochaines ventes utilisent la nouvelle. », « TVA actuelle »,
« Nouvelle TVA », « aucune (TVA du lieu) », « Tous les articles ont déjà cette TVA. »,
« Cette catégorie n'a pas de TVA à synchroniser. », « TVA de %(taux)s %% appliquée aux
%(nombre)s articles de la catégorie. ». L'ancienne chaîne bilingue « Même TVA que la
catégorie… » n'est plus utilisée.

---

## Comment tester (a la main) / Manual test

1. Admin → Caisse → Catégories → une catégorie avec une TVA (ex. 5,5 %).
2. Bouton « Synchroniser la TVA (5.50 %) sur tous les articles » en haut de la fiche.
3. La confirmation explique l'effet et liste les articles qui changent (ex. « 20.00 % → 5.50 % »,
   « aucune (TVA du lieu) → 5.50 % ») ; « Annuler » la ferme.
4. « Confirmer » : la page se recharge, message « TVA de 5.50 % appliquée aux N articles… » ;
   la fiche d'un de ces articles montre la TVA 5,5 %.
5. Une catégorie sans TVA : pas de bouton.

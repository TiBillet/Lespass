# Articles de caisse : méthode « Vente » figée / POS items: "Sale" method locked

**Date :** 2026-11-24
**Migration :** Non

## Resume / Summary
**Quoi / What :** Dans l'admin des articles de caisse, le champ « Méthode de caisse » est
caché. Un nouvel article est toujours une « Vente ». Un article existant garde sa méthode,
l'admin ne peut plus la changer. L'aide du « Prix d'achat » dit qu'il sert à calculer le
bénéfice, et que le prix de vente se règle dans les tarifs.
/ The "POS method" field is hidden in the POS item admin. A new item is always a "Sale".
An existing item keeps its method. The purchase price help text says it is used to
compute the profit, and that the sale price is set in the prices below.

**Pourquoi / Why :** Pour l'instant, on veut empêcher la création d'autres types
d'articles (recharges, retours de consigne…) depuis l'admin.
/ For now, other item types must not be created from the admin.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `Administration/admin/products.py` | `POSProductForm` : `methode_caisse` en champ caché + `clean_methode_caisse()` (création = VT, modification = valeur en base) ; aide de `prix_achat` |
| `tests/pytest/test_admin_article_caisse_methode_vente.py` | Nouveau : champ caché, création forcée en Vente, méthode d'un article existant inchangée |
| `tests/pytest/test_admin_retour_de_consigne.py` | Les retours de consigne sont testés sur la page de MODIFICATION d'un retour existant (l'ajout crée toujours une Vente) |

---

## Comment tester (a la main) / Manual test

### Test 1 — création
1. Admin > Caisse > Articles > Ajouter.
2. Vérifier : pas de liste « Méthode de caisse » dans la section « Général ».
3. Vérifier l'aide sous « Prix d'achat » : elle parle du bénéfice et des tarifs plus bas.
4. Remplir le nom, enregistrer.
5. Dans la liste des articles, la colonne méthode affiche « Vente ».

### Test 2 — article existant d'un autre type
1. Ouvrir un article « Retour de consigne » existant.
2. Vérifier : pas de liste « Méthode de caisse », mais le champ « Rembourse la consigne »
   reste visible.
3. Enregistrer : l'article reste un « Retour de consigne ».
4. Même chose avec une recharge : elle reste une recharge.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_admin_article_caisse_methode_vente.py tests/pytest/test_admin_retour_de_consigne.py"`

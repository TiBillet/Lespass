# Catalogue comptable : tout le catalogue pour un logiciel qui tient la comptabilité avec ses factures / Accounting catalogue: the whole catalogue for a software keeping the books from its invoices

**Date :** 2026-10-15
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- `GET /api/v2/products/?accounting=true` : tout le catalogue du lieu (publié ou non, archivé ou non, tous les tarifs), trié par nom puis uuid, rendu en français. Dans `additionalProperty` : `productType`, `posCategory`, `vatRate` (ou `vatRateError`), `accountingAccount` (ou `accountingAccountError`), `forAccountingSync`, `archived` ; par tarif : `archived`, `soldByWeightOrVolume`. Un en-tête `ETag` (sha256 du JSON) ; `If-None-Match` égal (préfixe `W/` accepté) → `304` sans corps. Sans le paramètre, la réponse ne change pas.
- Pas de nouvelle route ni de nouveau droit : la clé du logiciel a les droits « Produits » et « Comptabilité (lecture) ». `get_apikey_valid` n'est pas touché.
- Deux règles sorties de leur fonction, sans copie : `compte_pour_produit()` (toutes les règles de `compte_pour_article`, dans le même ordre ; `compte_pour_article` l'appelle avec la monnaie de la ligne) et `taux_de_tva_du_produit()` (recharge, consigne, produit, lieu ; `_taux_tva_de_la_ligne_de_caisse` l'appelle). Un retour de consigne sans gobelet lève `ConsigneRembourseeManquante` au lieu d'un `AttributeError`.
- `productType.label` : « Article de caisse » pour le type `N` (le libellé du choix est la consigne d'un menu, « Sélectionner une catégorie »). Le catalogue est lu en un nombre fixe de requêtes (adhésions obligatoires préchargées).
- `est_une_vente_pour_la_comptabilite()` : faux pour les produits système, les recharges, le virement reçu, vider carte, le retour de consigne, la recharge en temps, la fidélité. Le fût est une vente (la tireuse le vend au litre).

/ `?accounting=true` on the products route: the whole catalogue with accounting properties and an ETag (304 when unchanged). The account and VAT rules are shared with the register and the FEC, not copied.

**Pourquoi / Why :** Chantier 06-C. Un lieu peut choisir, à la place du FEC, de laisser Dolibarr tenir sa comptabilité avec ses propres factures : TiBillet n'est alors qu'un « front » de vente. Le module Dolibarr recopie d'abord le catalogue chaque nuit ; les ventes viendront en 06-D. Spec : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-C-catalogue.md` (relue par Fable).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `laboutik/plan_comptable.py` | `compte_pour_produit` (la règle, déplacée telle quelle), `compte_pour_article` l'appelle ; `taux_de_tva_du_produit`, `ConsigneRembourseeManquante` ; `est_une_vente_pour_la_comptabilite` |
| `laboutik/views.py` | `_taux_tva_de_la_ligne_de_caisse` garde le point 1 (offert / points) et appelle `taux_de_tva_du_produit` |
| `api_v2/views.py` | `ProductViewSet.list` : `?accounting=true` → `_catalogue_pour_la_comptabilite` (ETag, 304, langue fixe) |
| `api_v2/serializers.py` | `ProductSchemaSerializer` : mode comptable (tous les tarifs, propriétés comptables) ; `_propriete_schema` |
| `api_v2/openapi-schema.yaml` | paramètre `accounting`, en-tête `If-None-Match`, `ETag`, réponse `304` |
| `api_v2/GUIDELINES.md` | section « Catalogue for an accounting software » |
| `tests/pytest/test_api_v2_catalogue_comptable.py` | 17 tests, schéma dédié (dont nombre de requêtes fixe, ETag sur nom / archivage / compte) |

Module Dolibarr (dépôt `tibillet-dolibarr`) : choix du mode, synchro du catalogue, tâche de nuit unique à heure réglable (fuseau de la personne), produit passé hors vente quand son tarif ne peut plus être recopié, réponse illisible refusée, résumé sans balise, `304` qui garde le résumé, Dolibarr 24 minimum. Voir son README.

**i18n :** une nouvelle chaîne `_("Article de caisse")` (source en français) : à passer dans `makemessages` / `compilemessages`.

---

## Comment tester (a la main) / Manual test

### Test 1 — le catalogue
1. Dans l'admin, une clé d'API avec les droits « Produits » et « Comptabilité (lecture) ».
2. `curl -sk -H "Authorization: Api-Key <clé>" "https://lespass.tibillet.localhost/api/v2/products/?accounting=true" -D - -o /tmp/catalogue.json`
3. Attendu : `200`, un en-tête `ETag`, des produits archivés et non publiés, et pour chacun `vatRate`, `accountingAccount` (ou sa phrase d'erreur), `forAccountingSync`.
4. Relancer avec `-H 'If-None-Match: <ETag>'` : `304`, sans corps.
5. Changer le prix d'un tarif dans l'admin, relancer : `200` et un autre `ETag`.

### Test 2 — la TVA ne vient jamais de la catégorie
1. Un article sans TVA dans une catégorie de caisse à 20 %, le lieu à 10 % par défaut.
2. Attendu dans le catalogue : `vatRate` = `10.00`.

### Test 3 — la caisse n'a pas changé
1. Vendre en caisse une bière, une recharge et un retour de consigne.
2. Attendu : mêmes taux de TVA qu'avant (20 %, 0 %, taux du gobelet), FEC de la J identique.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_catalogue_comptable.py -q`
- Côté module : `docker exec dolibarr-dev-dolibarr-1 php /var/www/html/custom/tibillet/scripts/essai.php`

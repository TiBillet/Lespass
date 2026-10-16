# Ventes comptables : les ventes d'une J pour un logiciel de facturation / Accounting sales: a closure's sales for an invoicing software

**Date :** 2026-10-16
**Migration :** Non

## Resume / Summary
**Quoi / What :**
- `GET /api/v2/closures/<uuid>/sales/?after_number=<n>&limit=<m>` : les ventes réglées en euros d'une clôture J (sauf les CORRECTION, dont les règlements sont ajoutés à la vente corrigée), triées par numéro, page par page (`nextAfterNumber`). Chaque vente est découpée par TiBillet en `orderedItem` (lignes de facture au tarif vendu, `priceIdentifier` = `ref_ext` du produit Dolibarr), `invoicePayments`, `transfers` (recharges et vidages : virements internes) et `variousPayments` (recharge offerte, jetons repris, écart d'encaissement : paiements divers). Montants en centimes, comptes par leur numéro, acheteur par son uuid et son **e-mail seul**.
- Droit : la clé doit avoir « Comptabilité » **et** « Ventes » (`CleAvecLeDroitDesVentes`). `get_apikey_valid` n'est pas touché.
- `comptabilite/ventes_a_facturer.py` : `vente_a_facturer()` et `ventes_a_facturer_de_la_cloture()`. Les règles du FEC sont réutilisées, pas recopiées : compte par compte, la découpe donne les sommes du FEC de la J (testé sur le scénario complet du FEC).
- `laboutik/plan_comptable.py` : `est_une_recharge(produit)`, partagée par le FEC (`_ecrire_la_recharge_offerte`) et la découpe.
- `tests/pytest/fabriques_vente.py` : `fabriquer_vente_encaissee(..., client=None)`.
- `est_une_vente_pour_la_comptabilite()` : le **fût** est une vente (la tireuse le vend au litre) ; il va maintenant dans le catalogue comptable (correction de 06-C).

/ A J closure's sales, split by TiBillet for an invoicing software (invoice lines, payments, internal transfers, various payments). Per account, equal to the FEC.

**Pourquoi / Why :** Chantier 06-D. En mode « articles et ventes », Dolibarr tient la comptabilité avec ses propres factures : chaque matin, il vient chercher les ventes des J clôturées. Spec : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-06-connecteurs-comptables/CHANTIER-06-D-ventes.md`, plan : `CHANTIER-06-D-PLAN.md`.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `comptabilite/ventes_a_facturer.py` (neuf) | la découpe d'une vente, `RepartitionImpossible` |
| `laboutik/plan_comptable.py` | `est_une_recharge` |
| `comptabilite/ventilation.py` | `_ecrire_la_recharge_offerte` appelle `est_une_recharge` |
| `api_v2/views.py` | action `ClosureViewSet.sales` |
| `api_v2/permissions.py` | `CleAvecLeDroitDesVentes` |
| `api_v2/serializers.py` | `VenteAFacturerSerializer` |
| `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md` | la route |
| `tests/pytest/test_ventes_a_facturer.py` (neuf) | 15 tests de la découpe |
| `tests/pytest/test_api_v2_catalogue_comptable.py` | le fût est une vente |
| `tests/pytest/test_api_v2_ventes_comptables.py` (neuf) | 10 tests de la route |
| `tests/pytest/test_fec_equilibre.py` | découpe = FEC, compte par compte |
| `tests/pytest/fabriques_vente.py` | paramètre `client` |

**Tests (les ventes de test ne bloquent plus la vraie journée de `lespass`)** :
- `test_admin_alignements_et_fiche_vente.py` : `pytestmark = pytest.mark.django_db` (ses ventes étaient validées pour de vrai).
- `fabriques_vente.creer_tarif_vendu()` : un produit sans compte reçoit la catégorie « TEST_vente Caisse 707000 » (`donner_un_compte_au_produit`) ; `avec_compte=False` pour les tests du refus (9 appels, 4 tests de `test_plan_comptable_unique.py`, le jus du `setUp` de `test_rapport_unique.py`).
- Le fût de `test_controlvanne_review_fixes.py` et les produits de 5 tests E2E (vendus sans annulation) reçoivent un compte par la même fonction.
- Piège documenté : `tests/PIEGES.md`, « Une vente de test restée dans `lespass` bloque la vraie journée ».

Module Dolibarr (dépôt `tibillet-dolibarr`) : import des ventes en factures, virements internes et paiements divers. Voir son README.

**i18n :** deux nouvelles chaînes `_()` (messages 400 de `after_number` et `limit`, source en français) : à passer dans `makemessages` / `compilemessages`.

---

## Comment tester (a la main) / Manual test

### Test 1 — les ventes d'une J
1. Une clé d'API avec les droits « Comptabilité (lecture) » et « Ventes ».
2. `curl -sk -H "Authorization: Api-Key <clé>" "https://lespass.tibillet.localhost/api/v2/closures/?after_number=0"` → l'uuid d'une J.
3. `curl -sk -H "Authorization: Api-Key <clé>" "https://lespass.tibillet.localhost/api/v2/closures/<uuid>/sales/?limit=5"`
4. Attendu : `200`, au plus 5 ventes, `nextAfterNumber` rempli s'il en reste ; une bière en espèces a une ligne et un paiement au 530000 ; une recharge a un virement 419100 → banque du moyen.
5. Avec une clé « Comptabilité » seule : `403`.

### Verifs automatiques
- `docker exec lespass_django poetry run pytest tests/pytest/test_ventes_a_facturer.py tests/pytest/test_api_v2_ventes_comptables.py tests/pytest/test_fec_equilibre.py -q`

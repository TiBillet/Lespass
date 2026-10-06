# Un article d'une vente réglée ne se supprime jamais ; fixtures E2E sur des lectures publiques ; Mailpit capteur dans la copie de production / A settled sale's item is never deleted; E2E fixtures on public reads; Mailpit catcher in the production copy

**Date :** 2026-10-06
**Migration :** Non

## Résumé / Summary

**Quoi / What :**
1. **Garde de suppression** (`BaseBillet/models.py`, receveur `pre_delete` de `LigneArticle`,
   à côté de la garde d'immutabilité de `save()`) : supprimer l'article d'une vente RÉGLÉE
   lève `ProtectedError` (message en français : « faire un avoir »). Vaut pour
   `article.delete()`, `LigneArticle.objects.filter(...).delete()` (Django envoie
   `pre_delete` pour chaque ligne dès qu'un receveur existe) et la cascade d'un `PriceSold`
   supprimé. Un article d'une vente EN ATTENTE, ANNULÉE, ou sans vente, se supprime toujours.
   / Deleting an item of a SETTLED sale raises ProtectedError (instance, queryset and
   cascade deletes). Pending, cancelled or sale-less items are still deleted.
2. **Tests qui supprimaient des articles de ventes réglées** :
   - `tests/pytest/test_billetterie_pos.py` tournait sur le vrai lieu `lespass` et son
     nettoyage supprimait les articles de ventes réglées (vente et règlement restaient sans
     article : égalité rompue, empreinte fausse). Il tourne maintenant dans un schéma dédié
     (`FastTenantTestCase`, `test_billetterie_pos`), chaque test annulé : plus aucune
     suppression. Les 16 tests et toutes leurs vérifications sont gardés.
   - `test_admin_reservation_add.py`, `test_admin_annulation_abonnement_stripe.py`,
     `test_parcours_vente_fed_et_remise_en_banque.py`, et 6 tests de `booking/tests/`
     (`test_booking_engine.py`, `test_timezone_slots.py`, réservation acceptée) : déjà en
     `django_db` (transaction annulée), leur nettoyage manuel des articles réglés est
     retiré ; le parcours FED retrouve sa vente par l'uuid de sa demande.
   - `test_qrcodescanpay_flux_complet.py` : la boucle FED puis TLF ne supprime plus la
     vente du tour précédent, elle la met de côté par son uuid.
   - `test_rapport_unique.py` (`_supprimer_la_vente`) : simule une écriture à la main par
     SQL brut, comme `test_vente_service.py`.
   / Tests that deleted settled items now run in a dedicated schema or rely on the
   rolled-back transaction.
3. **Rapport des ventes, deux lectures publiques** (`comptabilite/rapport.py`) :
   `totaux_caisse_et_en_ligne()` (règlements argent + cashless, recharges encaissées,
   adhésions, séparés en « caisse » = ventes d'un point de vente / « en_ligne » = les
   autres) et `perimetre_de_l_article(uuid)` (« caisse », « en_ligne » ou None). Testées
   dans `test_rapport_unique.py`, avec un test qui refuse un `rapport._` dans
   `tests/e2e/conftest.py`.
   / Two public report reads, split by scope; tested in pytest.
4. **Fixtures E2E** `rapports_comptables` et `rapports_qui_voient_la_ligne`
   (`tests/e2e/conftest.py`) : elles ne lisent plus que des méthodes publiques
   (`section_caisse_especes`, `totaux_caisse_et_en_ligne`, `perimetre_de_l_article`).
   Mêmes clés, montants exacts. Les vérifications « compté deux fois » entre les deux
   anciens rapports sont retirées (un seul rapport : une vente est d'un seul périmètre).
   / The E2E fixtures read public methods only; "counted twice" checks removed.
5. **Copie de la production** (`db-prod/`, hors git) : un Mailpit capteur
   (`copie_prod_mailpit`) est le seul serveur de mail de Django ; écran web sur
   `127.0.0.1:18025` seulement (second réseau sans NAT, Mailpit seul : Docker ne publie
   aucun port d'un conteneur seulement sur un réseau interne) ; `verifier` contrôle
   `EMAIL_HOST` et qu'aucun autre serveur de mail n'est joignable ; `compter` affiche le
   total des messages captés. Procédure : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-05-R-copie-prod.md`.
   / Production copy: a Mailpit catcher, UI on 127.0.0.1 only, total watched.

**Pourquoi / Why :** une vente réglée est scellée (total = articles = règlements, empreinte
LNE). Supprimer un de ses articles casse l'égalité, l'empreinte et les rapports ; une erreur
se corrige par un avoir. / A settled sale is sealed; a mistake is corrected by a credit note.

### Fichiers modifiés / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/models.py` | receveur `pre_delete` `refuser_la_suppression_d_un_article_d_une_vente_reglee` ; renvoi depuis la garde de `save()` |
| `comptabilite/rapport.py` | `totaux_caisse_et_en_ligne()`, `perimetre_de_l_article()` |
| `tests/pytest/test_garde_suppression_article.py` | nouveau : 6 tests de la garde |
| `tests/pytest/test_billetterie_pos.py` | schéma dédié, plus aucune suppression |
| `tests/pytest/test_admin_reservation_add.py`, `tests/pytest/test_admin_annulation_abonnement_stripe.py`, `tests/pytest/test_parcours_vente_fed_et_remise_en_banque.py`, `booking/tests/test_booking_engine.py`, `booking/tests/test_timezone_slots.py` | nettoyage manuel des articles réglés retiré (transaction annulée) |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | la vente du tour précédent est mise de côté, plus supprimée |
| `tests/pytest/test_rapport_unique.py` | 3 tests (lectures par périmètre, fixtures E2E sans méthode privée) ; `_supprimer_la_vente` en SQL brut |
| `tests/e2e/conftest.py` | fixtures sur des méthodes publiques |
| `tests/e2e/test_adhesion_recompense_puis_qrcode.py`, `test_renouvellement_adhesion_recurrente.py`, `test_recharge_pos_puis_qrcode.py` | vérifications « compté deux fois » retirées |

---

## Comment tester / How to test
```bash
make test ARGS="tests/pytest/test_garde_suppression_article.py tests/pytest/test_billetterie_pos.py tests/pytest/test_rapport_unique.py"
make e2e ARGS="tests/e2e/test_recharge_pos_puis_qrcode.py tests/e2e/test_adhesion_recompense_puis_qrcode.py tests/e2e/test_recompense_au_scan_puis_qrcode.py tests/e2e/test_renouvellement_adhesion_recurrente.py"
```
À la main / By hand : `manage.py shell`, dans un lieu, prendre l'article d'une vente réglée
et appeler `.delete()` : `ProtectedError`, l'article reste.

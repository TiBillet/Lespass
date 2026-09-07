# Les vues carte écrivent aussi côté Lespass / Card views now write on the Lespass side too

**Date :** 2026-09-05
**Migration :** Non

## Resume / Summary

**Quoi / What :** `lost_my_card` et le parcours QR (`ScanQrCode.link`) parlaient à Fedow sans
jamais écrire dans la base Lespass. Ils appellent désormais `CarteService.declarer_perdue` et
`CarteService.lier_a_user`, qui posent (ou retirent) `CarteCashless.user`.
/ `lost_my_card` and the QR flow talked to Fedow without ever writing to the Lespass database.
They now call `CarteService.declarer_perdue` / `CarteService.lier_a_user`.

**Pourquoi / Why :** deux conséquences, dont une de sécurité.

1. **Carte perdue toujours dépensable (grave).** `lost_my_card` ne détachait la carte que chez
   Fedow. `CarteCashless.user` restant posé, le point de vente V2 continuait de résoudre la
   carte vers le wallet de son ancien porteur (`_obtenir_ou_creer_wallet` rend
   `carte.user.wallet`, `laboutik/views.py:1095`) et signait la cascade legacy avec sa clé.
   **Qui trouve une carte déclarée perdue dépense le portefeuille de qui l'a perdue.**
2. **Carte liée par le web invisible au POS.** Sans `CarteCashless.user`, la carte reste
   « anonyme » pour la caisse V2 : le solde fédéré est masqué par le garde
   `if carte.user is not None` (`laboutik/views.py:1210`), et l'identification de l'adhérent
   au comptoir ne fonctionne pas.

Les deux branchements sont **non bloquants** : Fedow a déjà fait sa part, une incohérence
locale ne doit pas transformer un parcours abouti en erreur pour l'usager. Le détachement local
n'a lieu **que si Fedow a accepté** — les deux bases ne doivent pas diverger dans l'autre sens.

**Deux niveaux de journalisation**, parce que les deux cas n'appellent pas la même réaction :
- `CarteIntrouvable` → `warning`. Cas **attendu** : la carte existe chez Fedow mais pas dans
  cette base (lieu V1, dont les cartes vivent dans LaBoutik ; ou carte hors réseau).
- toute autre exception (`CarteDejaLiee`, `UserADejaCarte`…) → **`error`**. Les deux bases
  divergent sur le propriétaire de la carte, et c'est la version **locale** que lit le point de
  vente. Ça demande une action, pas un breadcrumb.

### Pourquoi les tests existants ne l'ont pas vu

`CarteService` est couvert par 17+ tests (`tests/pytest/test_scan_qr_carte_v2.py`), tous
excellents — mais ils appellent le **service** directement. Ils restaient verts alors qu'aucune
vue ne l'appelait : `scanner_carte`, `lier_a_user` et `declarer_perdue` avaient **zéro appelant
en production**. Les tests E2E qui auraient couvert la couture ont été explicitement reportés
(`TECH_DOC/SESSIONS/LABOUTIK/DONE/Session 34 - Scan QR carte V2/TESTS_E2E_A_FAIRE.md`, motif :
teardowns Playwright destructifs sur la base de dev).

C'est l'angle mort qui compte : la frontière **vue → service**, que ni les tests unitaires du
service ni les E2E absents ne regardaient.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `MyAccount.lost_my_card` : appelle `CarteService.declarer_perdue` après le succès Fedow. `ScanQrCode.link` : appelle `CarteService.lier_a_user` après la fusion Fedow. Import `get_client_ip` ajouté à la ligne d'import existante d'`AuthBillet.utils` ; `CarteService` importé localement, comme `WalletService` l'est déjà dans ce fichier. |
| `tests/pytest/test_vues_carte_branchees_sur_service.py` | **Nouveau.** Teste la COUTURE : passe par l'URL réelle, mocke Fedow, vérifie l'état de la base locale. 3 tests. |
| `laboutik/management/commands/create_test_pos_data.py` | `CarteCashless.uuid` **EST** le qrcode_uuid (celui que porte `/qr/<uuid>/` et par lequel `CarteService.lier_a_user` résout la carte). Le seed posait un uuid aléatoire : la carte locale était introuvable au moment de la liaison, alors que Fedow, lui, l'avait liée. Helper `_qrcode_uuid_depuis_tag`, formule identique à celle de `demo_data_v2._seed_cartes_nfc_fedow` (commentaire croisé dans les deux fichiers). |

---

## Comment tester (a la main) / Manual test

### Test 1 — automatique

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_vues_carte_branchees_sur_service.py -q
```

Attendu : **3 passed**. Validé par mutation : retirer l'appel à `declarer_perdue` fait échouer
`test_lost_my_card_detache_la_carte_cote_lespass`.

Non-régression du périmètre (43 tests) :

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_scan_qr_carte_v2.py \
  tests/pytest/test_demo_wallet_alignment.py \
  tests/pytest/test_vues_carte_branchees_sur_service.py \
  tests/pytest/test_wallet_carte_fedow.py \
  tests/pytest/test_wallet_carte_fedow_integration.py \
  tests/pytest/test_membership_card_wallet_fedow.py \
  tests/pytest/test_caisse_navigation.py -q
```

### Test 2 — le scénario de vol (à faire après un flush complet)

1. Lier la carte client 1 (`52BE6543`) à un compte via le QR code + email.
2. Vérifier en base que `CarteCashless.user` est posé :
   ```bash
   docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
   from django_tenants.utils import tenant_context
   from Customers.models import Client
   from QrcodeCashless.models import CarteCashless
   with tenant_context(Client.objects.get(schema_name='lespass')):
       c = CarteCashless.objects.get(tag_id='52BE6543')
       print('user =', c.user)
   "
   ```
   **Avant le correctif** : `user = None` alors que la liaison Fedow avait réussi.
3. Depuis `/my_account/`, déclarer la carte perdue.
4. Rejouer la commande ci-dessus : `user = None` attendu.
5. Scanner la carte au POS V2 : elle doit être vue comme **anonyme**, sans le solde de
   l'ancien porteur.

**Avant le correctif**, l'étape 5 affichait le solde du propriétaire et permettait de le
dépenser.

### Test 3 — Fedow refuse

Le second test automatique le couvre : si `lost_my_card_by_signature` renvoie `False`, la carte
doit **rester liée** côté Lespass (pas de divergence inverse).

### Reste à faire / Still open

**Les cartes liées avant ce correctif.** Sur un tenant V1, `WalletValidator._user()`
(`QrcodeCashless/views.py:446`) pose déjà `CarteCashless.user` au scan QR. Les cartes déclarées
perdues depuis lors ont donc un `user` obsolète que rien n'a nettoyé. Sans conséquence
aujourd'hui (aucune caisse V2 ne lit ce champ sur un tenant V1), mais **à réconcilier avant de
migrer un tenant en V2** — sinon ces cartes deviennent des portes ouvertes le jour de la
bascule. Requête de diagnostic : comparer `CarteCashless.user` à `Card.user` côté Fedow.

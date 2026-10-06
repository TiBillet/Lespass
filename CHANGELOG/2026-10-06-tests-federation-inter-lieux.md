# Tests de la fédération d'assets entre deux lieux / Tests for asset federation between two venues

**Date :** 2026-10-06
**Migration :** Non

## Résumé / Summary

**Quoi / What :** tests E2E (14-1, 14-2), et une correction de nom de route d'admin (14-2).

### Session 14-1 — test A : fédération V2 (`fedow_core`)

- Nouveau test `tests/e2e/test_federation_asset_fedow_core.py`, portage de l'ancien test
  Playwright `31-admin-asset-federation.spec.ts` (supprimé en mars 2026, jamais réécrit).
  Le second lieu est `le-coeur-en-or` (`chantefrein` n'existe plus en dev).
- Le parcours, dans l'admin `/admin/fedow_core/asset/` :
  1. l'admin de `lespass` crée un asset TLF au nom unique ; le test vérifie en base que le
     signal a mis un produit « Recharge <nom> » et ses 4 tarifs (1, 5, 10, Libre) dans tous
     les points de vente CASHLESS de `lespass` ;
  2. dans l'autocomplétion des invitations, `Festival` (lieu legacy) n'est pas proposé
     (réponse de `/admin/autocomplete/` et liste déroulante) ; `le-coeur-en-or` est invité ;
  3. la colonne « Lieux fédérés » montre « Lespass », pas encore « Le Coeur en or » ;
  4. l'admin de `le-coeur-en-or` voit l'invitation et l'accepte ; en base, le lieu passe des
     invitations aux lieux fédérés ;
  5. les deux lieux voient l'asset avec les deux noms ; chez `le-coeur-en-or`, la fiche est
     en lecture seule ;
  6. l'asset est archivé : son produit de recharge est archivé avec lui (signal), et l'asset
     quitte la liste de `lespass`.
- En fin de test (réussi ou non), la fixture archive l'asset et retire ses invitations en
  attente : la caisse de `lespass` ne se remplit pas de produits de recharge.
- Vérification de départ des moteurs (`moteurs_de_depart_verifies`) et du module
  « Monnaie locale » sur les deux lieux V2 : échec explicite sinon.

/ Session 14-1 — test A: V2 federation (`fedow_core`). New E2E test porting the deleted
Playwright test (second venue: `le-coeur-en-or`). It creates a TLF asset on `lespass` (the
signal adds a top-up product with 4 prices to every CASHLESS POS), checks that `festival`
(legacy) is never offered by the invitation autocomplete, invites and accepts
`le-coeur-en-or`, checks the "federated venues" column on both venues and the read-only page
for the invited venue, then archives the asset (its top-up product is archived too). The
fixture archives the asset and clears its pending invitations at teardown, pass or fail.

### Session 14-2 — tests B et C : fédération legacy avec le vrai Fedow, et correction

- **Correction (cette branche seulement)** : chez un lieu invité, le bouton « ACCEPTER »
  des invitations d'assets legacy (`fedow_public`) postait vers l'acceptation des assets
  `fedow_core`. Les deux routes d'admin portaient le même nom,
  `staff_admin:asset-accept-invitation`, et `{% url %}` choisissait celle de `fedow_core`.
  Celle-ci refuse un lieu legacy (« Votre lieu utilise l'ancien moteur de monnaie… ») : un
  lieu du réseau CLAF ne pouvait plus accepter une fédération. La route legacy s'appelle
  maintenant `assetfedowpublic-accept-invitation`, reprise par `asset_list_before.html`.
  La route `fedow_core` garde son nom (`asset_changelist_invitations.html`). La branche
  `main` n'a pas ce nom en double : elle n'est pas concernée.
- Nouveau test de garde `tests/pytest/test_noms_de_routes_admin_uniques.py` :
  - aucun nom de route du site `staff_admin` n'est porté par deux admins différents
    (les doublons internes de django-solo restent admis) ;
  - chaque panneau d'invitations poste vers sa propre route.
- Nouveau test E2E `tests/e2e/test_federation_asset_legacy_inter_lieux.py`, un seul
  parcours (`test_parcours_monnaie_federee_entre_deux_lieux`) :
  - **B** : `lespass` crée un asset TLF legacy (relu sur le Fedow), invite `festival`
    (lieu legacy, profil CLAF) ; l'admin de `festival` accepte ; la fédération est vérifiée
    en base, sur le Fedow (`get_accepted_assets()` de `festival`) et dans la liste de
    `lespass` ;
  - **C** : un adhérent neuf adhère chez `lespass` (tarif neuf du produit
    « E2E Adhesion monnaie federee », réutilisé), reçoit 5,00 de cette monnaie sur le
    Fedow ; l'admin de `festival` crée un QR code de 1,50 (skin classic) ; l'adhérent le
    paie chez `festival` par le vrai relais de session entre lieux ; le Fedow débite 150 ;
    la vente est chez `festival` (moyen LOCAL_EURO) ; la ventilation de l'asset chez
    `lespass` montre 1,50 pour `festival`, puis 0 après la remise en banque, enregistrée
    sur le Fedow.
- Deux pièges ajoutés à `tests/PIEGES.md` : 9.115 (l'autocomplétion M2M d'Unfold 0.89 est
  le select2 de l'admin Django) et 9.116 (le Fedow de dev a un cache par processus : une
  fédération neuve est ignorée jusqu'à 120 s).

/ Session 14-2 — tests B and C, and a fix (this branch only): the legacy asset
invitation panel posted to the `fedow_core` accept route, because both admin routes shared
the name `staff_admin:asset-accept-invitation`. A legacy venue (CLAF network) could no longer
accept a federation. The legacy route is now `assetfedowpublic-accept-invitation`. `main`
does not have the duplicate name. New guard test: no `staff_admin` route name is shared by
two admins, and each invitation panel posts to its own route. New E2E journey against the
real Fedow: federation with `festival` (legacy), membership reward on `lespass`, QR code
payment at `festival` through the cross-venue session relay, per-venue breakdown and bank
deposit. Two pitfalls added (select2 autocomplete, per-process cache of the dev Fedow).

**Pourquoi / Why :** aucun test ne faisait intervenir deux lieux. L'invitation et
l'acceptation de fédération `fedow_core` n'avaient plus de test E2E depuis la suppression de
la suite Playwright (spec `TECH_DOC/SESSIONS/FEDOW_IMPORT/14-spec-tests-federation-inter-lieux.md`).
/ No test involved two venues; the `fedow_core` invitation/acceptance flow had lost its E2E
test.

### Fichiers modifiés / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `tests/e2e/test_federation_asset_fedow_core.py` | Nouveau : test A (14-1) |
| `tests/e2e/test_federation_asset_fedow_core.py` | Session « ter » (M-2 de la relecture Fable) : exige au moins un point de vente CASHLESS avant de vérifier qu'aucun n'est sans le produit de recharge (sinon `== 0` était vrai par construction) |
| `Administration/admin_tenant.py` | Route legacy `accept_invitation` renommée `assetfedowpublic-accept-invitation` (14-2) |
| `Administration/templates/admin/asset/asset_list_before.html` | Le formulaire « ACCEPTER » reprend ce nom (14-2) |
| `tests/pytest/test_noms_de_routes_admin_uniques.py` | Nouveau : test de garde des noms de routes d'admin (14-2) |
| `tests/e2e/test_federation_asset_legacy_inter_lieux.py` | Nouveau : tests B et C (14-2) |
| `tests/PIEGES.md` | Pièges 9.115 et 9.116 (14-2) |
| `CHANGELOG/2026-10-06-tests-federation-inter-lieux.md` | Nouveau |

---

## Comment tester (à la main) / Manual test

### Session 14-1 — test A

Lancement (serveur de dev qui répond, aucun autre pytest en cours) :

```bash
make e2e ARGS="tests/e2e/test_federation_asset_fedow_core.py"
```

À la main, le même parcours :
1. Admin de `lespass` → « Monnaies » → assets `fedow_core` → ajouter un asset TLF.
2. Ouvrir sa fiche, taper « Festival » dans « Invitations en attente » : aucun résultat.
   Taper « Coeur », choisir « Le Coeur en or », enregistrer.
3. Admin de `le-coeur-en-or` → même liste : le panneau d'invitations montre l'asset,
   cliquer « Accepter le partage ».
4. La liste des deux lieux montre « Lespass, Le Coeur en or » dans « Lieux fédérés ».

### Vérifs DB

```bash
docker exec -it lespass_django poetry run python /DjangoFiles/manage.py shell
```
```python
from fedow_core.models import Asset
for asset in Asset.objects.filter(name__startswith="E2E Fed V2"):
    print(asset.name, asset.archive, list(asset.federated_with.values_list("schema_name", flat=True)))
```

Chaque lancement laisse un asset `E2E Fed V2 <suffixe>` archivé, fédéré avec
`le-coeur-en-or`, et son produit « Recharge … » archivé dans la caisse de `lespass`.
Rien n'est écrit sur le Fedow distant.

### Session 14-2 — tests B et C

Lancement (seul, sur le Fedow de DEV : chaque lancement émet de la monnaie, environ 2 min 30) :

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_noms_de_routes_admin_uniques.py -q
make e2e ARGS="tests/e2e/test_federation_asset_legacy_inter_lieux.py"
```

À la main, la correction :
1. Admin de `lespass` → « Monnaies » → « Assets legacy » → ajouter un asset TLF, puis sur sa
   fiche inviter « Festival » et enregistrer.
2. Admin de `festival` → même liste : le panneau « Invitations d'actifs » montre l'asset ;
   « ACCEPTER » affiche « Invitation acceptée. » et l'asset entre dans la liste, avec
   « Festival, Lespass » dans la colonne des lieux fédérés. Avant la correction : retour à
   l'accueil de l'admin avec « Votre lieu utilise l'ancien moteur de monnaie (Fedow). Ce
   module n'est pas disponible. »
3. Sur le Fedow de dev, la fédération n'est vue par tous ses processus qu'après 2 minutes
   (piège 9.116) : attendre avant de payer chez `festival` avec cette monnaie.

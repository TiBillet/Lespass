# Rapatriement des cartes depuis l'ancien Fedow / Fetching cards from the old Fedow

**Date :** 2026-10-12
**Migration :** Non

## Resume / Summary
**Quoi / What :** une carte NFC connue de l'ancien Fedow mais absente de Lespass (chargée
par `import_cards`) est rapatriée au premier scan, comme dans LaBoutik V1 : en caisse
(écran carte primaire, identification, paiements NFC/espèces/CB/chèque, consigne,
paiement complémentaire, retour de carte, vidage), à la borne et à la tireuse. Une carte
d'un lieu encore sur l'ancien moteur, ou d'un lieu introuvable, est refusée au scan.
Fedow injoignable n'est plus confondu avec « carte inconnue ».
/ An NFC card known by the old Fedow but missing in Lespass is fetched on first scan
(POS, kiosk, tap). A card from a legacy or unknown venue is refused. An unreachable
Fedow is no longer mistaken for an unknown card.

**Pourquoi / Why :** à la-cabine, des cartes chargées dans l'ancien Fedow restaient
« inconnues » en caisse et introuvables dans l'admin des cartes primaires : rien ne
remplissait la copie locale `CarteCashless`.
/ Cards loaded in the old Fedow stayed "unknown": nothing filled the local copy.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `QrcodeCashless/services.py` | **Neuf** : `trouver_ou_rapatrier_la_carte`, `FedowInjoignable`, `CarteDUnLieuNonMigre` |
| `fedow_connect/fedow_api.py` | `NFCcardFedow.retrieve` : seul un 404 **JSON** veut dire « carte inconnue » ; un 404 du proxy est une panne |
| `laboutik/views.py` | 12 points de scan passent par le service (hors `atomic`) ; messages de refus ; `except` ajouté aux paiements espèces et CB/chèque (500 avant sur un tag inconnu) |
| `kiosk/carte.py`, `kiosk/views.py`, `kiosk/validators.py` | borne : rapatriement + message de refus |
| `controlvanne/viewsets.py` | tireuse (`authorize`) : rapatriement + refus poussé à l'écran |
| `Administration/management/commands/demo_data_v2.py` | la carte de démo « inconnue » (`DEMO_TAGID_CLIENT4`) n'est plus créée chez Fedow |
| `tests/pytest/test_rapatriement_carte_fedow.py` | **Neuf** : service et correctif 404 |
| `tests/pytest/test_rapatriement_carte_points_de_scan.py` | **Neuf** : points de scan |
| `tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py` | **Neuf** : E2E caisse (check carte → recharge → paiement NFC → rescan) |
| `tests/PIEGES.md` | 3 pièges du rapatriement |
| `tests/pytest/test_caisse_ouverture_ancien_fedow.py`, `test_kiosk_ecrans.py`, `test_wallet_carte_fedow_integration.py` | adaptés (carte inconnue en local désormais demandée à Fedow) |

Spec : `TECH_DOC/SESSIONS/QRCODECASHLESS/CHANTIER-02-rapatriement-cartes-fedow.md`.

**i18n :** 2 chaînes traduisibles neuves (msgid FR) dans `QrcodeCashless/services.py`.
Le workflow i18n est à lancer par le mainteneur.

**Changements de comportement voulus :**
- Fedow arrêté derrière son proxy (404 non JSON) : le vidage d'une carte en caisse
  répond « L'ancien Fedow n'a pas pu vider la carte… réessayez » au lieu de vider en
  local seulement ; la borne dit « La carte n'a pas pu être lue » ; l'admin des cartes
  NFC dit « Fedow injoignable ».
- Le bouton de démo « Carte inconnue » reste inconnu sur un Fedow neuf. Sur un Fedow de
  dev déjà provisionné, la carte `E85C2C6E` existe encore chez Fedow : elle sera
  rapatriée au premier clic.

---

## Comment tester (a la main) / Manual test

### Test 1 — le cas de la-cabine (carte primaire)
1. Charger une carte dans l'ancien Fedow avec `import_cards`, sur la place du lieu.
2. Sur le Sunmi (ou le simulateur), écran « scannez la carte primaire » : scanner la carte.
3. Attendu : « Carte non primaire ». En base, la `CarteCashless` existe, rattachée à une
   génération (`Detail`) du lieu.
4. Admin → Caisse → Cartes primaires → Ajouter : la carte est dans la recherche (par
   numéro ou tag). Choisir un point de vente, enregistrer.
5. Rescanner : la caisse s'ouvre.

### Test 2 — carte client jamais vue
1. Une carte chargée dans Fedow, jamais scannée dans le lieu.
2. Caisse : la scanner en paiement NFC (ou « retour de carte »).
3. Attendu : le parcours aboutit, comme pour une carte connue.

### Test 3 — refus
1. Carte d'un lieu encore sur l'ancien moteur (ou dont le domaine Lespass est inconnu).
2. La scanner en caisse : « Cette carte vient d'un lieu qui n'utilise pas encore le
   nouveau moteur TiBillet. » Rien n'est créé en base.

### Test 4 — Fedow arrêté
1. Arrêter le conteneur de l'ancien Fedow.
2. Scanner une carte inconnue en local : « Fedow injoignable : la carte n'a pas pu être
   vérifiée. Réessayez. » (et non « Carte inconnue »).

### Verifs DB
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from QrcodeCashless.models import CarteCashless
c = CarteCashless.objects.select_related('detail__origine').get(tag_id='XXXXXXXX')
print(c.number, c.uuid, c.detail.generation, c.detail.origine)
"
```

### Tests automatiques
`make test ARGS="tests/pytest/test_rapatriement_carte_fedow.py tests/pytest/test_rapatriement_carte_points_de_scan.py"`

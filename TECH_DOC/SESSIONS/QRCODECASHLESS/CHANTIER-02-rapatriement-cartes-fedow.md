# CHANTIER 02 — Rapatrier depuis Fedow les cartes inconnues en local

App `QrcodeCashless` (+ points de scan de `laboutik`, `kiosk`).

Date : 2026-10-12. Statut : **✅ livré le 2026-10-12, non commité** (décisions en § 6).
Relu deux fois par un agent Fable le 2026-10-12 : les findings des deux passes sont intégrés.

---

## 1. Le problème

Cas réel, la-cabine (2026-10-12) :

1. De nouvelles cartes sont chargées dans l'ancien Fedow avec `import_cards`
   (`../Fedow/fedow_core/management/commands/import_cards.py`). Elles existent
   dans `fedow_core.Card`.
2. Elles sont scannées sur le Sunmi, à l'écran « scannez la carte primaire ».
3. Elles restent **introuvables** dans `/admin/laboutik/carteprimaire/add/`.

Cause : Lespass a un miroir local, `QrcodeCashless.CarteCashless`, que **rien
ne remplit automatiquement** (voir `SPEC.md` § 1.1). Le formulaire de carte
primaire ne voit que ce miroir (`Administration/admin/laboutik.py`,
`formfield_for_foreignkey`). Le scan ne fait qu'une lecture locale
(`laboutik/views.py`, `_charger_carte_primaire` :
`CarteCashless.objects.get(tag_id=...)`). Si la carte n'est pas trouvée, la
réponse est « Carte inconnue » et rien n'est créé.

**Le défaut dépasse les cartes primaires.** Les mêmes cartes, utilisées comme
cartes **client**, sont aussi « inconnues » en caisse V2 : paiement NFC,
recharge, consigne, retour de carte, vidage, borne.

Le seul chemin existant pour remplir le miroir est le formulaire d'ajout de
carte NFC (`CarteCashlessAddForm`, réconciliation par `retrieve`), une carte à
la fois, à la main.

## 2. Comment faisait LaBoutik V1

V1 (`../LaBoutik`) fait un **miroir paresseux, au scan** :

- Chaque point de scan appelle d'abord Fedow : `FedowAPI().NFCcard.retrieve(tag_id)`
  (`GET card/<tag_id>/`). Exemples : `webview/views.py` `check_carte`,
  `webview/validators.py` `validate_tag_id`, `htmxview/validators.py`.
- La réponse passe dans `fedow_connect/validators.py` `CardValidator.validate()`.
  Ce validateur cherche la carte par `uuid`, et sur `DoesNotExist` il **crée** la
  carte locale (`tag_id`, `uuid_qrcode`, `number`, `origin`, `wallet`).
- Le code lit **ensuite** la carte locale : `CarteCashless.objects.get(tag_id=...)`.
- Les cartes primaires (`CarteMaitresseAdmin.get_form`,
  `administration/admin_commun.py`) se choisissent parmi les cartes locales
  **liées à un membre** (`membre__isnull=False`). En V1, une carte devenait
  donc éligible après un premier scan, puis après sa liaison à un membre.
- V1 distingue Fedow en panne (502) d'une carte inconnue (404).

Fedow n'expose **aucune route de liste** des cartes d'un lieu (`CardAPI` est un
`ViewSet` sans `list`, `../Fedow/fedow_core/views.py`). Le rapatriement se fait
donc carte par carte, par `tag_id`, en V1 comme en V2.

## 3. Ce que fait la V2 aujourd'hui

- `fedow_connect.fedow_api.NFCcardFedow.retrieve(tag_id)` renvoie
  `CardValidator.validated_data`, et lève `CarteInconnueDeFedow` sur un 404.
- Le `CardValidator` de Lespass **ne crée pas de `CarteCashless`**. Il écrit en
  revanche des miroirs locaux : `WalletValidator` fait
  `Wallet.objects.get_or_create(uuid=...)` sans `origin`, et `AssetValidator` ou
  `TransactionSimpleValidator` écrivent les leurs. C'est un effet de bord déjà
  accepté ailleurs (`laboutik/views.py`, docstring de la lecture pour vidage).
- La caisse appelle déjà `retrieve`, mais **après** avoir trouvé la carte locale
  (ouverture de caisse, vidage, solde). La borne (`kiosk/carte.py`) appelle
  `retrieve`, puis `CarteCashless.objects.get` : la carte existe chez Fedow,
  mais un `DoesNotExist` est levé.
- Le portefeuille d'une carte est miroité **au premier paiement** par
  `obtenir_wallet_carte_depuis_fedow` (`laboutik/views.py`), appelée par
  `_obtenir_ou_creer_wallet`. Elle crée le `Wallet` local avec
  `origin=connection.tenant`, et pose `wallet_ephemere` si la carte est anonyme.
  Sa docstring dit « On ne fabrique PAS la carte au scan (comme V1) » : elle
  deviendra fausse avec ce chantier, et sera mise à jour.
- **Fedow en panne est confondu avec « carte inconnue »** (`SPEC.md` § 1.5).
  Le 404 d'un reverse-proxy, quand Fedow est arrêté, tombe dans
  `CarteInconnueDeFedow`. Le vrai 404 de Fedow est une réponse JSON
  (`Response("Carte inconnue", 404)`), alors que celui du proxy est en
  `text/plain`.

## 4. Le design proposé

### 4.0 Contexte : le verrou de moteur

Le verrou de moteur (`FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md`) est appliqué
en production par le chantier 05-R. La caisse V2, la borne et la tireuse sont
**fermées aux lieux `legacy`** : `lieu_en_moteur_legacy()` est vérifié dans
`BaseBillet/permissions.py`, `kiosk/views.py` et `controlvanne/permissions.py`.
Tous les appelants du service tournent donc dans un lieu **`v2`**.

Rattacher une carte au lieu courant (`Detail.origine` = lieu v2) ne change donc
rien au verrou. Pour un lieu v2, il n'y a pas de retour possible vers legacy.

### 4.1 Un seul point d'entrée

Nouveau module `QrcodeCashless/services.py`, avec une fonction :

```python
def trouver_ou_rapatrier_la_carte(tag_id):
    """
    Renvoie la CarteCashless locale du tag. Si elle manque et que le lieu est
    relié à l'ancien Fedow, la lit chez Fedow et fabrique le miroir local.

    À appeler dans un schéma tenant (lit FedowConfig, TENANT_APPS), et JAMAIS
    dans un bloc transaction.atomic() : l'appel réseau tiendrait un verrou de
    base pendant 30 s au pire.

    :raises CarteCashless.DoesNotExist: tag invalide, carte inconnue en local ET
        chez Fedow, ou lieu non relié à l'ancien Fedow.
    :raises FedowInjoignable: Fedow ne répond pas, ou répond une fiche illisible.
    :raises CarteDUnLieuNonMigre: la carte vient d'un lieu encore sur l'ancien
        moteur (legacy), ou d'un lieu introuvable. Aucune CarteCashless ni aucun
        Detail n'est créé (les miroirs Wallet/Asset écrits par le CardValidator
        pendant retrieve restent : c'est l'effet de bord accepté du § 3).
    """
```

Flux :

1. `tag_id` nettoyé et mis en majuscules.
2. Carte locale trouvée → on la renvoie. **Aucun appel réseau** : une carte déjà
   connue n'ajoute aucune latence au scan. Cette recherche passe **avant** le
   contrôle du format : des cartes locales de test ou de démo portent un tag non
   hexadécimal (`RCTXXXXX`…), et elles doivent rester trouvées (constaté en S2 :
   23 tests existants cassaient avec l'ordre inverse).
   Ensuite seulement, le tag est comparé à `^[0-9A-F]{8}$` (regex locale, comme
   `MOTIF_HEXA_8_CARACTERES` de `QrcodeCashless/admin.py`). On n'utilise pas
   `validate_hex8` : il accepte les minuscules et lève une erreur DRF. S'il est
   invalide, on lève `DoesNotExist` **sans appel réseau**. Sans ce contrôle, un tag
   vide partirait en `GET card//`.
3. `fedow_config = FedowConfig.get_solo()`, lu une seule fois. Si le lieu n'est
   pas relié (`can_fedow()` faux, lieu 100 % moteur V2), on lève `DoesNotExist`,
   comme aujourd'hui.
4. `NFCcardFedow(fedow_config).retrieve(tag_id)`. On n'utilise pas `FedowAPI()` :
   c'est plus léger, et `NFCcardFedow.retrieve` est **la cible de mock unique** des
   tests (§ 8.1) :
   - `CarteInconnueDeFedow` → `DoesNotExist`.
   - autre erreur (réseau, statut, fiche illisible) → `FedowInjoignable`, avec un
     log. La caisse affiche alors « Fedow injoignable » au lieu de « Carte inconnue ».
5. Choix du `Detail` (§ 4.2). Si la carte vient d'un lieu legacy, ou d'un lieu
   introuvable, on lève `CarteDUnLieuNonMigre` **avant toute écriture**.
6. Fabrication du miroir :
   - `tag_id` = `first_tag_id`, `number` = `number_printed`,
     `uuid` = `qrcode_uuid`, `detail` choisi à l'étape 5.
   - **Ni `user` ni `wallet_ephemere`.** Le chemin
     `obtenir_wallet_carte_depuis_fedow` les répare au premier paiement. Effet
     connu, identique à une carte créée dans l'admin : une carte que Fedow lie à
     un utilisateur apparaît « anonyme » en caisse (`carte.user` vide) tant
     qu'elle n'est pas liée en local.
   - Le `Wallet` miroir créé par `WalletValidator` n'a pas d'`origin`. On la pose,
     sans écraser une origine existante :
     `Wallet.objects.filter(uuid=..., origin__isnull=True).update(origin=connection.tenant)`.
     Sinon, `obtenir_wallet_carte_depuis_fedow` trouverait ce `Wallet` et ne
     poserait jamais l'origine.
7. Concurrence et unicité : `CarteCashless` est en `SHARED_APPS` (schéma `public`).
   `tag_id`, `number` et `uuid` sont donc **uniques sur toutes les instances**.
   Le pattern est le suivant (le `except` reste **hors** du `atomic`, sinon la
   transaction est cassée : « current transaction is aborted ») :
   ```python
   try:
       with transaction.atomic():
           carte = CarteCashless.objects.create(...)
   except IntegrityError:
       ...
   ```
   - Même `tag_id` créé entre-temps (deux scans simultanés) : on relit la carte
     et on la renvoie.
   - Collision sur `number` ou `uuid` avec une **autre** carte locale : log
     `error` avec les trois identifiants, puis `DoesNotExist`. Pas de 500 en caisse.
8. Décision D2 : si la fiche Fedow dit `is_primary=True`, le service écrit un
   `logger.info` (« carte primaire chez Fedow, à déclarer dans l'admin »). Il ne
   crée aucune `CartePrimaire`.

**Correctif lié, dans `NFCcardFedow.retrieve`** : lever `CarteInconnueDeFedow`
seulement si le 404 est une réponse JSON (`Content-Type: application/json`).
Sinon, lever `Exception`. Le vrai 404 de Fedow est `Response("Carte inconnue",
404)`, sans renderer personnalisé, donc en `application/json` : on compare avec
`startswith`. Effets sur les autres appelants de `retrieve` :
- admin des cartes NFC (`QrcodeCashless/admin.py`) : Fedow arrêté donne enfin
  « Fedow injoignable » au lieu de « refusé » (`SPEC.md` § 1.5). C'est voulu ;
- `_verifier_carte_primaire_aupres_de_l_ancien_fedow` : aucun changement visible
  (ses deux `except` refusent déjà l'ouverture), seule la ligne de journal change ;
- `_vider_la_carte_sur_l_ancien_fedow` : un 404 du proxy **ne passe plus en
  « rien à vider chez Fedow »**. Il tombe dans le `except Exception` de
  `vider_carte` : « L'ancien Fedow n'a pas pu vider la carte. Rien n'a été fait :
  réessayez. » C'est **voulu**, et c'est le comportement actuel quand Fedow est
  injoignable. Avant ce correctif, un proxy en 404 laissait vider la carte en
  local, sans reprendre ses jetons chez Fedow ;
- `kiosk/carte.py` : passe de « carte inconnue » à « La carte n'a pas pu être
  lue ». C'est voulu.

**Limite connue** (comme en V1) : `_get` a un timeout de 30 s. Si un tag est
inconnu en local et que Fedow est en panne, le Sunmi attend jusqu'à 30 s à
chaque scan de ce tag.

### 4.2 Génération (`Detail`) de la carte rapatriée (décision D1)

La réponse Fedow porte `origin.place.uuid`, `origin.place.lespass_domain` et
`origin.generation`. On en déduit le lieu d'origine, **sans appel réseau de plus** :

| Lieu d'origine de la carte | Comment on le reconnaît | Ce qu'on fait |
|---|---|---|
| le lieu courant (toujours `v2`, § 4.0) | `str(origin.place.uuid) == str(fedow_config.fedow_place_uuid)` | `Detail` du lieu courant avec cette génération : on prend l'existant ou on le crée |
| un autre lieu **`v2`** | `lespass_domain` → `Domain` → `tenant`, puis `tenant.moteur_monnaie == v2` | `Detail` de ce lieu avec cette génération : on prend l'existant ou on le crée. Sans risque : un lieu v2 ne revient jamais en legacy |
| un autre lieu **`legacy`** | même lecture, avec `moteur_monnaie == legacy` | **refus** : `CarteDUnLieuNonMigre`, rien n'est créé |
| un lieu **introuvable** (pas de `lespass_domain`, ou domaine inconnu) | `Domain` absent | **refus**, comme pour un lieu legacy |

Pourquoi refuser une carte legacy : créer son `Detail` déclencherait la raison 6
de `raisons_qui_empechent_le_passage_en_v2()` (`Customers/bascule_vers_v2.py`).
Son lieu d'origine ne pourrait plus passer en V2 en un clic, à cause d'un scan
fait ailleurs.

Le refus ne concerne que le **rapatriement**. Une carte déjà présente en local est
renvoyée à l'étape 2, quelle que soit son origine.

**Risques acceptés par le mainteneur (D1 maintenue après la 2ᵉ relecture) :**
- `Place.lespass_domain` est écrit **une seule fois**, à la création du lieu chez
  Fedow (`../Fedow/fedow_core/validators.py`), et jamais mis à jour. Un lieu qui a
  changé de domaine principal sans garder l'ancien en `Domain` devient
  « introuvable » : toutes ses cartes sont refusées dans les autres lieux. Remède
  côté exploitation : garder l'ancien domaine en `Domain` secondaire du lieu.
- Incohérence avec `CarteCashlessAddForm` : l'admin des cartes NFC rattache au
  lieu **courant** une carte Fedow de **n'importe quelle** origine. Une carte
  refusée au scan peut donc être ajoutée à la main dans l'admin.

Règles d'écriture du `Detail` :
- « Prendre l'existant » = `Detail.objects.filter(origine=lieu, generation=g)`,
  le premier par `pk`. Pas de `get_or_create` : le couple `(origine, generation)`
  n'est pas unique.
- Le `base_url` d'un `Detail` créé est calculé à partir du domaine du lieu concerné.
  On recopie les quelques lignes de `_obtenir_la_generation_par_defaut_du_lieu`
  (`QrcodeCashless/admin.py`), et **on ne déplace pas ce helper** : sa règle est
  différente (génération la plus haute du lieu, sinon génération 1), et
  `test_carte_cashless_admin.py` l'importe depuis `QrcodeCashless.admin`.
  `services.py` n'importe pas `admin.py`, qui tire `Administration`.
- `Detail` est en SHARED_APPS : écrire le `Detail` d'un autre lieu ne demande pas
  de changer de schéma.

La carte rapatriée apparaît ensuite dans l'admin des cartes NFC de son lieu
d'origine. Si ce lieu est le lieu courant, elle apparaît aussi dans
l'autocomplétion des cartes primaires (filtrée sur `detail__origine`).

**Messages au scan** (msgid en français, sur tous les sites branchés) :
- `CarteDUnLieuNonMigre` : « Cette carte vient d'un lieu qui n'utilise pas encore
  le nouveau moteur TiBillet. »
- `FedowInjoignable` : « Fedow injoignable : la carte n'a pas pu être vérifiée.
  Réessayez. »

### 4.3 Branchement aux points de scan

Recensement du 2026-10-12 : 19 lectures de `CarteCashless` par `tag_id` hors
tests. Règle : on branche les **premiers scans hors bloc `atomic`**. Une
**relecture** (la carte a déjà été résolue plus tôt dans la même requête) garde sa
lecture locale.

**Branchés** (S2) :

| Fichier | Fonction | Note |
|---|---|---|
| `laboutik/views.py` | `CaisseViewSet.carte_primaire` | écran « scannez la carte primaire ». Le service est appelé **juste avant** `_charger_carte_primaire`, qui reste une lecture locale pure (voir ci-dessous) |
| `laboutik/views.py` | `PaiementViewSet.identifier_client` | |
| `laboutik/views.py` | `PaiementViewSet._payer_par_nfc` | premier scan au paiement |
| `laboutik/views.py` | `PaiementViewSet._payer_en_especes` | recharge. **Pas d'`except` aujourd'hui** (500 sur un tag inconnu) : on ajoute l'`except` des trois cas |
| `laboutik/views.py` | `PaiementViewSet._payer_par_carte_ou_cheque` | **pas d'`except` aujourd'hui** : idem |
| `laboutik/views.py` | `PaiementViewSet._rembourser_consigne_par_nfc` | hors transaction (documenté) |
| `laboutik/views.py` | `PaiementViewSet._executer_paiement_complementaire` (×2) | seconde carte, entre les deux `atomic` |
| `laboutik/views.py` | `CaisseViewSet._identifier_adherent` | ce n'est **pas** toujours une relecture : en espèces ou en chèque sans recharge, la carte n'est pas résolue avant. Appelée hors `atomic` (`_resoudre_adherent_hors_atomic`). Les trois cas d'erreur gardent le comportement actuel (log et repli sur l'email) |
| `laboutik/views.py` | `PaiementViewSet.retour_carte` | « check carte » |
| `laboutik/views.py` | `PaiementViewSet.vider_carte_preview`, `vider_carte` | |
| `kiosk/carte.py` | `lire_la_carte_pour_la_borne` | les **deux** appelants (`kiosk/views.py` et `kiosk/validators.py`) attrapent `(DoesNotExist, CarteInconnueDeFedow)` puis `Exception` : il faut leur ajouter la branche `CarteDUnLieuNonMigre`, sinon elle tombe dans « La carte n'a pas pu être lue ». Pour une carte inconnue en local, il y aura **deux** `retrieve` (le service, puis la lecture du solde) : c'est accepté |
| `controlvanne/viewsets.py` | `authorize` (badge posé sur la tireuse) | décision D4. Hors `atomic`. `.filter().first()` : `DoesNotExist` donne `None` (« Carte non reconnue », inchangé) ; un refus est poussé à l'écran de la tireuse. Le `select_related("user")` est conservé en relisant la carte trouvée |

Pour chaque site, il faut vérifier, au moment du branchement, qu'il n'est **pas**
appelé depuis un bloc `atomic` (test 42).

**Non branchés** (lecture locale conservée) :

| Fichier | Fonction | Raison |
|---|---|---|
| `laboutik/views.py` | `_charger_carte_primaire` | appelée par `_operateur_de_la_caisse`, **dans** des blocs `atomic` (vidage, ouverture de vente, paiements). Brancher ici tiendrait un verrou de base pendant un appel réseau. Tous ses appelants, sauf l'écran carte primaire, exigent une `CartePrimaire`, donc une carte déjà locale |
| `laboutik/views.py` | `_creer_billets_depuis_panier` | appelée **dans** le bloc `atomic` du paiement (sa docstring l'exige) ; relecture |
| `laboutik/views.py` | `CaisseViewSet._rendre_popup_paiement_client_identifie` | relecture |
| `laboutik/views.py` | `recharge_carte` (`get_object_or_404`) | relecture après `retour_carte` |
| `BaseBillet/views.py` | `QrCodeScanPay.process_with_nfc` | **N'a pas besoin du miroir : ce paiement fonctionne en production.** Le débit se fait chez Fedow par le tag (`to_place_from_qrcode`). La carte locale ne sert qu'à remplir `carte` sur la ligne de vente, et `None` y est accepté. Cette lecture a lieu **après** le débit, dans un `try` qui met la ligne en échec : un appel réseau à cet endroit risquerait de transformer un paiement réussi en incident |
| `kiosk/views.py` | `acces_admin` | exige une `CartePrimaire`, donc une carte déjà locale |

Sémantique conservée : un site en `.filter(...).first()`, qui tolère une carte
absente, attrape `DoesNotExist` et garde son `None`.

### 4.4 Ce qui ne change pas

- Le formulaire de carte primaire reste sans bouton « + » (fait le 2026-10-12,
  `CHANGELOG/2026-10-12-carte-primaire-sans-creation-de-carte.md`).
- La déclaration de la carte primaire à Fedow (`set_primary`) reste dans
  `CartePrimaireAdminForm.clean()`. Si Fedow répond `208` « déjà déclarée », c'est
  accepté.
- Le moteur local `fedow_core` n'est pas touché. Le service ne lit et n'écrit que
  `CarteCashless`, `Detail` et `Wallet`.
- Un lieu sans `FedowConfig` complet (`can_fedow()` faux, comme tous les schémas
  `test_*`) garde exactement son comportement actuel, sans appel réseau.

**Changement lié (démo, décision D5)** : `demo_data_v2.py` ne crée plus la carte
`DEMO_TAGID_CLIENT4` (bouton « Carte inconnue » des simulateurs de caisse, de
borne et de tireuse) chez l'ancien Fedow. Elle reste ainsi inconnue partout, et
le bouton garde son sens. Le commentaire de
`test_wallet_carte_fedow_integration.py`, qui la décrit comme « jamais
référencée », est corrigé en conséquence.

## 5. Parcours gestionnaire après le chantier

1. `import_cards` dans l'ancien Fedow (inchangé).
2. Scanner la carte **une fois** sur le Sunmi (écran carte primaire, ou retour de
   carte). Elle est rapatriée. L'écran répond « Carte non primaire ». Pas de
   commande de rattrapage en lot (décision D3).
3. Admin → Cartes primaires → Ajouter : la carte est dans la recherche.
4. Rescanner : la caisse s'ouvre.

## 6. Décisions du mainteneur (2026-10-12)

**D1 — Origine de la carte rapatriée** (reconfirmée le 2026-10-12, après le
constat du conflit avec la raison 6 du verrou de moteur) :
- lieu courant ou autre lieu **v2** → on rattache la carte à son `Detail`, en le
  créant s'il manque ;
- lieu **legacy** ou **introuvable** → la carte est **refusée au scan**
  (`CarteDUnLieuNonMigre`), et rien n'est créé.
Détail au § 4.2.

**D2 — Fedow dit `is_primary=True` sans `CartePrimaire` locale** : **on ne crée
rien**, on écrit un `logger.info`. L'écran garde « Carte non primaire ». Le
gestionnaire la déclare dans l'admin, et le `208` de Fedow est accepté.

**D3 — Pas de commande de rattrapage en lot.** Dès qu'une carte est inconnue en
local, on la demande à l'ancien Fedow, à chaque scan, pour les cartes primaires
comme pour les cartes client. C'est le modèle V1.
Constat vérifié le 2026-10-12 : ce n'est **pas** le comportement actuel de la V2.
`identifier_client`, `_payer_par_nfc` et `retour_carte` répondent « Carte inconnue »
sans appel à Fedow. `obtenir_wallet_carte_depuis_fedow` interroge Fedow, mais
seulement **après** avoir trouvé la carte locale.

**D4 — La tireuse connectée (`controlvanne`) est branchée** (§ 4.3).

**D5 — Carte de démo « inconnue »** : `demo_data_v2.py` ne la crée plus chez
l'ancien Fedow (§ 4.4).

## 7. Plan en sessions

| # | Contenu | Tests |
|---|---|---|
| S1 | `QrcodeCashless/services.py` : `trouver_ou_rapatrier_la_carte`, `FedowInjoignable`, `CarteDUnLieuNonMigre`, `Detail` (§ 4.2) ; correctif 404 JSON dans `NFCcardFedow.retrieve` | § 8.2 et § 8.3 ; suite pytest complète (le correctif 404 touche d'autres appelants) |
| S2 | Branchement des sites du § 4.3 (caisse, borne, tireuse) + messages + docstring de `obtenir_wallet_carte_depuis_fedow` + démo D5 + tests existants à adapter (§ 8.7) | § 8.4 et § 8.5 ; suites complètes pytest et E2E |
| S3 | CHANGELOG, `INDEX.md`, pièges éventuels dans `tests/PIEGES.md` | — |

Les tests sont détaillés au § 8.

**Avancement (2026-10-12)** :
- S1 livrée : 37 tests (`test_rapatriement_carte_fedow.py`). 20 mutations, toutes
  détectées. Suite complète : 3817 passés, 0 échec.
- S2 livrée : 60 tests (`test_rapatriement_carte_points_de_scan.py`) et les tests 29
  et 30 (`test_caisse_ouverture_ancien_fedow.py`). 24 mutations : toutes détectées,
  sauf la carte 1 du complément (§ 8.4, test 36).
- E2E livré (§ 8.5) : vert deux fois de suite, et il échoue sur une mutation.
- Suites complètes : pytest **3879 passés**, 1 xfail, 0 échec (référence avant le
  chantier : 3781). E2E : 141 passés. Les 4 échecs repassent un par un, isolés : ce
  sont des instabilités de chargement, sans lien avec le chantier. Les 9 erreurs
  viennent de `stripe listen`, absent.

## 8. Tests — un test par cas d'usage

Consigne du mainteneur (2026-10-12) : des tests solides, qui couvrent **tous** les
cas d'usage. Chaque ligne ci-dessous donne **un test atomique**, avec un nom verbeux.

### 8.1 Pièges à respecter (lire `tests/PIEGES.md` avant d'écrire)

- `CarteCashless` est en SHARED_APPS : pas de `FastTenantTestCase` (piège 9.30).
- Le service lit `connection.tenant` (moteur, origine du `Wallet`, `Detail`). Il faut
  donc `tenant_context(vrai_client)`, **jamais** `schema_context` (piège 9.1). Sous
  `FakeTenant`, `lieu_en_moteur_legacy()` répond legacy et la caisse est fermée.
- `tag_id` et `number` sont uniques en base : il faut des valeurs neuves à chaque
  run (piège 11.10). Utiliser un générateur hexadécimal aléatoire, et nettoyer les
  cartes, `Detail` et `Wallet` créés.
- L'ancien Fedow est **mocké** par `patch.object(fedow_connect.fedow_api.NFCcardFedow,
  "retrieve", ...)` (et par `_get` pour le correctif du 404). Le service ne passe
  **pas** par `laboutik.views.FedowAPI` ni par `kiosk.carte.FedowAPI`, que 54 tests
  existants patchent : ces mocks-là ne le couvrent pas. Aucun test ne dépend d'un
  Fedow réel.
- Le fichier du chantier porte une **garde autouse** qui fait échouer tout appel à
  `fedow_connect.fedow_api._get` / `_post` non mocké (modèle :
  `tests/pytest/test_caisse_vider_carte_deux_fedow.py`, garde « Fedow interdit »).
  `tests/pytest/conftest.py` n'a aucun bloqueur réseau.
- Sous `django_db`, chaque test tourne **déjà** dans un `atomic` :
  `connection.in_atomic_block` est toujours vrai. Pour savoir si un site appelle le
  service dans un `atomic` **de la vue**, on compare `len(connection.savepoint_ids)`
  au moment de l'appel avec sa valeur au début du test (un `atomic` imbriqué ajoute
  un savepoint).
- **Vérification par mutation** (règle du projet) : chaque test doit être vu
  **échouer** sur une mutation volontaire du service avant d'être livré. Cela
  vaut notamment pour la création du miroir, le refus legacy, le contrôle hex et
  le `except IntegrityError`. Aucun `pytest.skip` silencieux.

### 8.2 Service `trouver_ou_rapatrier_la_carte` (S1, `tests/pytest/test_rapatriement_carte_fedow.py`)

| # | Cas | Attendu |
|---|---|---|
| 1 | carte présente en local | renvoyée ; `retrieve` **jamais appelé** |
| 2 | tag en minuscules ou avec des espaces | normalisé, puis trouvé en local |
| 3 | tag vide, de 7 caractères, ou non hexadécimal | `DoesNotExist` ; **0 appel** réseau |
| 3 bis | carte **locale** au tag non hexadécimal | trouvée ; 0 appel réseau |
| 4 | lieu non relié (`can_fedow()` faux) | `DoesNotExist` ; 0 appel |
| 5 | carte inconnue de Fedow (404 JSON) | `DoesNotExist` ; 0 écriture `CarteCashless` |
| 6 | Fedow en panne (exception réseau, 500, 502) | `FedowInjoignable` ; 0 écriture |
| 7 | fiche Fedow illisible (validation en échec) | `FedowInjoignable` |
| 8 | carte du lieu courant, `Detail` de cette génération existant | carte créée avec les **3 identifiants Fedow** et ce `Detail` ; aucun `Detail` en plus |
| 9 | carte du lieu courant, aucun `Detail` de cette génération | `Detail` créé (`origine` = lieu courant, bonne génération, `base_url` renseigné) |
| 10 | plusieurs `Detail` pour la même génération du lieu | le premier par `pk` ; pas de `MultipleObjectsReturned` |
| 11 | carte d'un autre lieu **v2** qui a le `Detail` | rattachée à ce `Detail` ; aucun `Detail` créé |
| 12 | carte d'un autre lieu **v2** sans le `Detail` | `Detail` créé pour **ce** lieu |
| 13 | carte d'un lieu **legacy** | `CarteDUnLieuNonMigre` ; 0 `CarteCashless`, 0 `Detail` |
| 14 | carte sans `lespass_domain` | `CarteDUnLieuNonMigre` ; 0 écriture |
| 15 | `lespass_domain` inconnu en base | `CarteDUnLieuNonMigre` ; 0 écriture |
| 16 | refus legacy : la raison 6 du lieu legacy **ne bouge pas** | `Detail.objects.filter(origine=lieu_legacy).count()` identique avant et après (c'est exactement ce que lit la raison 6 ; `raisons_qui_empechent_le_passage_en_v2` exige d'être dans le contexte du lieu) |
| 17 | second appel avec le même tag | renvoie la même carte ; `retrieve` appelé **une seule fois** en tout |
| 18 | `Wallet` miroir sans `origin` | `origin` = lieu courant après le rapatriement |
| 19 | `Wallet` miroir qui a déjà une `origin` | `origin` **inchangée** |
| 20 | `user` et `wallet_ephemere` | restent vides sur la carte créée |
| 21 | double scan : `IntegrityError` sur `tag_id` (carte créée entre-temps) | renvoie la carte existante ; pas d'exception |
| 22 | collision sur `number` avec une **autre** carte locale | `DoesNotExist` + log `error` ; la carte existante n'est pas modifiée |
| 23 | collision sur `uuid` (QR) avec une autre carte locale | idem 22, et **après** l'appel une requête ORM passe encore : le test tourne déjà dans un `atomic` (`django_db`), ce qui prouve que le savepoint protège la transaction englobante |
| 24 | D2 : fiche Fedow `is_primary=True` | log `info` « carte primaire chez Fedow » ; **aucune** `CartePrimaire` créée |

### 8.3 Correctif `NFCcardFedow.retrieve` (S1, même fichier ou `test_carte_cashless_admin.py`)

| # | Cas | Attendu |
|---|---|---|
| 25 | 404 avec `Content-Type: application/json` | `CarteInconnueDeFedow` |
| 26 | 404 `text/plain` / `text/html` (proxy, Fedow arrêté) | `Exception`, **pas** `CarteInconnueDeFedow` |
| 27 | non-régression de l'admin des cartes NFC : Fedow arrêté | message « Fedow injoignable » au lieu de « refusé » (`SPEC.md` § 1.5) |
| 28 | `_vider_la_carte_sur_l_ancien_fedow` : 404 du proxy | `vider_carte` répond « L'ancien Fedow n'a pas pu vider la carte… » et **rien** n'est vidé en local (comportement voulu, § 4.1) |

### 8.4 Points de scan (S2) — une carte connue **seulement** de Fedow

Pour **chaque** site branché du § 4.3, trois tests : (a) la carte est rapatriée et
le parcours aboutit, (b) le refus legacy affiche son message, (c) Fedow en panne
affiche « Fedow injoignable ». Fichiers existants à compléter quand ils couvrent
déjà le site (`test_carte_primaire_ancien_fedow.py`, `test_retour_carte_recharge.py`,
`test_pos_vider_carte.py`, `test_pos_retour_consigne.py`, `test_pos_paiement_cheque.py`,
`test_kiosk_flow.py`, `test_controlvanne_api.py`), sinon un fichier neuf.

| # | Site | Parcours qui doit aboutir |
|---|---|---|
| 29 | `CaisseViewSet.carte_primaire` | scan d'une carte non primaire → rapatriée, réponse « Carte non primaire » ; elle apparaît ensuite dans l'autocomplétion de l'admin des cartes primaires. Dans `test_caisse_ouverture_ancien_fedow.py` (§ 8.7) |
| 30 | `CaisseViewSet.carte_primaire` | carte inconnue de Fedow → « Carte inconnue », un seul appel à `retrieve` |
| 30 bis | `_identifier_adherent` | adhésion payée en espèces, sans recharge, avec une carte connue seulement de Fedow → la carte rapatriée est portée jusqu'à l'adhésion et liée à l'adhérent·e (chez Fedow et en local). Une carte rapatriée n'a jamais de `user` (§ 4.1, étape 6) : l'adhérent·e vient de l'email saisi |
| 31 | `identifier_client` | client identifié (carte anonyme) |
| 32 | `_payer_par_nfc` | paiement NFC abouti |
| 33 | `_payer_en_especes` (recharge) | recharge aboutie |
| 34 | `_payer_par_carte_ou_cheque` | paiement abouti |
| 35 | `_rembourser_consigne_par_nfc` | consigne remboursée |
| 36 | `_executer_paiement_complementaire` | seconde carte connue de Fedow seulement → complément abouti. **La carte 1 n'est pas testée** : au moment du complément, elle a déjà été scannée par `_payer_par_nfc`, donc rapatriée. Une mutation sur la carte 1 survit, et c'est un choix assumé |
| 37 | `retour_carte` | fiche de la carte affichée |
| 38 | `vider_carte_preview` / `vider_carte` | aperçu, puis vidage |
| 39 | borne `lire_la_carte_pour_la_borne` | solde affiché ; refus legacy affiché par **les deux** appelants (`kiosk/views.py`, `kiosk/validators.py`), pas le message générique |
| 40 | tireuse `authorize` | service autorisé ; prénom du titulaire toujours envoyé (`select_related("user")` préservé) |
| 41 | sites **non branchés** (§ 4.3) | `retrieve` **jamais appelé** : non-régression, surtout `process_with_nfc` (paiement QR) |
| 42 | aucun site branché dans un `atomic` | le service est patché par un espion qui note `len(connection.savepoint_ids)` ; ce nombre doit égaler celui du début du test (§ 8.1) |
| 43 | sites qui n'avaient pas d'`except` (`_payer_en_especes`, `_payer_par_carte_ou_cheque`) | tag hex inconnu partout → message « Carte inconnue », **plus de 500** |
| 44 | démo D5 | `demo_data_v2` ne crée plus `DEMO_TAGID_CLIENT4` chez Fedow (`create` / `create_cards` mocké : le tag n'est pas dans la liste envoyée) |

### 8.5 E2E (Playwright)

Un seul parcours, à la caisse : scan simulé d'une carte connue seulement de Fedow,
puis paiement NFC abouti, puis rescan, qui doit aboutir aussi. (L'absence d'appel
à Fedow au rescan n'est pas observable depuis Playwright : elle est prouvée par le
test 17.) Fixture : la carte est créée chez le Fedow de dev par
`FedowAPI().NFCcard.create_cards` sous `tenant_context(lespass)` (l'E2E utilise déjà
`FedowAPI`, `tests/e2e/conftest.py`). C'est le **tag neuf à chaque run** qui rend
le parcours rejouable. Après une vente, la `CarteCashless` ne peut **pas** être
supprimée : `Vente.carte`, `LigneArticle.carte` et `Transaction.card` la protègent
(`PROTECT`), et supprimer ces lignes, ce serait supprimer de la comptabilité. Le
teardown tente donc `delete()` et garde la carte sur `ProtectedError`. Chaque run
réussi laisse en base de dev une carte, un portefeuille miroir et deux petites
ventes. On suit les pièges Playwright cross-tenant du projet.

Livré : `tests/e2e/test_caisse_carte_rapatriee_depuis_fedow.py` (familles `caisse`
et `monnaie`). Parcours : CHECK CARTE (rapatriement), recharge de 10 € en espèces
depuis la fiche, Coca à 3 € payé par NFC, nouveau CHECK CARTE (7,00 €), puis
vérification en base (`detail.origine` = lespass).

### 8.6 Suites complètes

À la fin de S2 et de S3 : `manage.py check`, puis les suites **complètes** pytest et
E2E (`make test`, `make e2e`), pas seulement les fichiers du chantier. On les
compare à la **référence** relevée avant le chantier (2026-10-12) : aucun test vert
avant ne doit passer au rouge.

### 8.7 Tests existants à adapter (non-régression)

| Test | Pourquoi il change | Action |
|---|---|---|
| `test_caisse_ouverture_ancien_fedow.py` `test_ouverture_carte_inconnue_en_local_n_interroge_pas_l_ancien_fedow` | sa fiche factice répond pour tout tag : après S2, la carte est rapatriée | le scinder en deux tests : 29 et 30 |
| `test_kiosk_ecrans.py` `test_lecture_carte_inconnue_revient_a_l_etape_1_avec_erreur` | tag hex « FFFFFFFF » sur un lieu relié : le service ferait un **vrai** appel réseau | ajouter `patch.object(NFCcardFedow, "retrieve", side_effect=CarteInconnueDeFedow(...))` |
| `test_wallet_carte_fedow_integration.py` (carte CLIENT4) | « jamais référencée » devient faux, ou l'est déjà selon D5 | ajuster le commentaire et le seed |
| tests à tag **non hexadécimal** (`test_caisse_navigation.py`, `test_controlvanne_api.py`, `test_retour_carte_recharge.py`, `test_pos_vider_carte.py`, `test_paiement_especes_cb.py`) | le contrôle hex coupe avant tout appel réseau | aucun changement. Ils ne couvrent plus le chemin « tag hex inconnu » : ce sont les tests 3, 5 et 43 qui le couvrent |
| `test_caisse_vider_carte_deux_fedow.py` | les cartes sont locales avant le scan, et une garde y interdit `_get` | aucun changement (le test 20f simule `CarteInconnueDeFedow` et reste vert) |
| `test_carte_cashless_admin.py` | importe `_obtenir_la_generation_par_defaut_du_lieu` depuis `QrcodeCashless.admin` | aucun changement : le helper n'est pas déplacé |

**Migration : non.**

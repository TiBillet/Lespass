# CHANTIER 02 — Rapatrier depuis Fedow les cartes inconnues en local

App `QrcodeCashless` (+ points de scan de `laboutik`, `kiosk`, `BaseBillet`).

Date : 2026-10-12. Statut : **à valider** (questions ouvertes en § 6).

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
cartes **client**, sont aussi « inconnues » partout en caisse V2 : paiement NFC,
recharge, adhésion, retour de carte, vidage, borne, paiement par QR code.

Le seul chemin existant pour remplir le miroir est le formulaire d'ajout de
carte NFC (`CarteCashlessAddForm`, réconciliation par `retrieve`), une carte à
la fois, à la main.

## 2. Comment faisait LaBoutik V1

V1 (`../LaBoutik`) fait un **miroir paresseux, au scan** :

- Chaque point de scan appelle d'abord Fedow : `FedowAPI().NFCcard.retrieve(tag_id)`
  (`GET card/<tag_id>/`). Exemples : `webview/views.py` `check_carte`,
  `webview/validators.py` `validate_tag_id`, `htmxview/validators.py`.
- La réponse passe dans `fedow_connect/validators.py` `CardValidator.validate()`.
  Ce validateur fait `CarteCashless.objects.get(id=uuid)`, et sur
  `DoesNotExist` il **crée** la carte locale (`tag_id`, `uuid_qrcode`, `number`,
  `origin`, `wallet`).
- Le code lit **ensuite** la carte locale : `CarteCashless.objects.get(tag_id=...)`.
- Les cartes primaires (`CarteMaitresseAdmin`, `administration/admin_commun.py`)
  se choisissent parmi les cartes locales. Une carte arrive donc dans l'admin
  après avoir été scannée une fois.

Fedow n'expose **aucune route de liste** des cartes d'un lieu (`CardAPI` est un
`ViewSet` sans `list`). La V1 ne pouvait donc pas, et la V2 ne peut pas non plus,
tout synchroniser d'un coup : le rapatriement se fait carte par carte, par
`tag_id`.

## 3. Ce que fait la V2 aujourd'hui

- `fedow_connect.fedow_api.NFCcardFedow.retrieve(tag_id)` existe : il renvoie
  `CardValidator.validated_data` et lève `CarteInconnueDeFedow` sur un 404.
  Le `CardValidator` de Lespass **ne crée rien** en base, contrairement à celui
  de V1. C'est voulu (pas d'écriture cachée dans un validateur), et on le garde.
- La caisse appelle déjà `retrieve`, mais **après** avoir trouvé la carte locale
  (ouverture de caisse, vidage, solde). La borne (`kiosk/carte.py`) appelle
  `retrieve`, puis `CarteCashless.objects.get` : la carte existe chez Fedow,
  mais un `DoesNotExist` est levé.

## 4. Le design proposé

### 4.1 Un seul point d'entrée

Nouveau module `QrcodeCashless/services.py`, avec une fonction :

```python
def trouver_ou_rapatrier_la_carte(tag_id):
    """
    Renvoie la CarteCashless locale du tag. Si elle manque et que le lieu est
    relié à l'ancien Fedow, la lit chez Fedow et fabrique le miroir local.
    :raises CarteCashless.DoesNotExist: carte inconnue en local ET chez Fedow,
        ou lieu non relié à l'ancien Fedow.
    :raises FedowInjoignable: Fedow ne répond pas (à distinguer de « inconnue »).
    """
```

Flux :

1. `tag_id` en majuscules, nettoyé.
2. Carte locale trouvée → on la renvoie. **Aucun appel réseau** : un lieu qui
   tourne n'ajoute pas de latence à chaque scan.
3. Lieu non relié (`FedowConfig.get_solo().can_fedow()` faux, lieu 100 % moteur
   V2) → `DoesNotExist`, comme aujourd'hui.
4. `NFCcardFedow.retrieve(tag_id)` :
   - `CarteInconnueDeFedow` → `DoesNotExist`.
   - autre erreur → `FedowInjoignable` (logguée), pour que la caisse puisse
     afficher « Fedow injoignable » au lieu de « Carte inconnue ».
5. Fabrication du miroir :
   - `tag_id` = `first_tag_id`, `number` = `number_printed`,
     `uuid` = `qrcode_uuid`.
   - `detail` : voir § 4.2.
   - **Ni `user` ni `wallet_ephemere`** : sur le segment legacy, le portefeuille
     vit chez Fedow et la caisse le lit en direct. On ne copie pas d'état qui
     divergerait.
6. Concurrence et unicité : `CarteCashless` est en `SHARED_APPS` (schéma
   `public`), donc `tag_id`, `number` et `uuid` sont **uniques sur toutes les
   instances**. Création dans `transaction.atomic()`. Sur une `IntegrityError` :
   - même `tag_id` créé entre-temps (deux scans simultanés) → on relit la
     carte et on la renvoie ;
   - collision sur `number` ou `uuid` avec une **autre** carte locale → log
     `error` avec les trois identifiants, puis `DoesNotExist`. Pas de 500 en
     caisse.

### 4.2 Génération (`Detail`) de la carte rapatriée

La réponse Fedow porte `origin.place.uuid` et `origin.generation`.

- `origin.place.uuid == FedowConfig.get_solo().fedow_place_uuid` (carte du lieu
  courant) → `Detail` du lieu courant **avec cette génération** : le premier
  par `pk` s'il existe, sinon on le crée. Pas de `get_or_create` : le couple
  `(origine, generation)` n'est pas unique (cf.
  `_obtenir_la_generation_par_defaut_du_lieu`, `QrcodeCashless/admin.py`).
- Carte d'un **autre lieu** → voir la question Q1.

La carte rapatriée apparaît alors dans l'admin des cartes NFC et dans
l'autocomplétion des cartes primaires (filtrées sur `detail__origine`).

### 4.3 Branchement aux points de scan

Remplacer la lecture locale par `trouver_ou_rapatrier_la_carte()` aux 16 endroits
recensés le 2026-10-12 :

| Fichier | Fonction |
|---|---|
| `laboutik/views.py` | `_charger_carte_primaire` |
| `laboutik/views.py` | `CaisseViewSet._rendre_popup_paiement_client_identifie`, `_identifier_adherent`, `_creer_billets_depuis_panier` |
| `laboutik/views.py` | `PaiementViewSet._payer_par_carte_ou_cheque`, `_payer_en_especes`, `_rembourser_consigne_par_nfc`, `_payer_par_nfc`, `identifier_client`, `_executer_paiement_complementaire` (×2), `retour_carte`, `vider_carte_preview`, `vider_carte` |
| `kiosk/carte.py` | `lire_la_carte_pour_la_borne` |
| `BaseBillet/views.py` | `QrCodeScanPay.process_with_nfc` |

Priorité : les **points d'entrée** d'abord (carte primaire, `identifier_client`,
`retour_carte`, borne), car une carte y est scannée en premier. Les autres
relisent le plus souvent une carte déjà vue dans la même transaction, mais on
les branche quand même, pour qu'aucun chemin ne réponde « Carte inconnue » sur
une carte que Fedow connaît.

Sémantique conservée : les sites en `.filter(...).first()` (qui tolèrent une
carte absente) attrapent `DoesNotExist` et gardent leur `None`.

### 4.4 Ce qui ne change pas

- Le `CardValidator` de `fedow_connect` reste un validateur pur.
- Le formulaire de carte primaire reste sans bouton « + » (fait le 2026-10-12,
  `CHANGELOG/2026-10-12-carte-primaire-sans-creation-de-carte.md`).
- La déclaration de la carte primaire à Fedow (`set_primary`) reste dans
  `CartePrimaireAdminForm.clean()`.

## 5. Parcours gestionnaire après le chantier

1. `import_cards` dans l'ancien Fedow (inchangé).
2. Scanner la carte **une fois** sur le Sunmi (écran carte primaire, ou retour de
   carte). Elle est rapatriée. L'écran répond « Carte non primaire ».
3. Admin → Cartes primaires → Ajouter : la carte est dans la recherche.
4. Rescanner : la caisse s'ouvre.

## 6. Questions ouvertes (à trancher par le mainteneur)

**Q1 — Carte d'un autre lieu** (`origin.place` ≠ lieu courant), par exemple la carte
d'un festivalier venue d'un autre lieu de la fédération.
- (a) *recommandé* : on la rapatrie avec un `Detail` **sans origine**
  (`origine=None`). Elle marche en caisse, mais elle n'apparaît dans l'admin d'aucun
  lieu et ne peut pas devenir carte primaire ici.
- (b) on retrouve le tenant d'origine (`origin.place.lespass_domain` → `Domain` →
  `Client`) et on rattache le `Detail` à ce tenant. C'est plus juste, mais il y a une
  requête de plus et il faut gérer le cas où le tenant est introuvable.

**Q2 — Fedow dit `is_primary=True` pour ce lieu, mais il n'existe pas de
`CartePrimaire` locale.** C'est le cas d'un lieu qui passe de V1 à V2 : ses
cartes primaires sont déjà déclarées dans Fedow.
- (a) *recommandé* : on ne crée rien automatiquement (une carte primaire sans
  point de vente n'ouvre rien). Le message de l'écran devient « Carte primaire
  chez Fedow, à configurer dans l'admin ».
- (b) on crée la `CartePrimaire` sans point de vente.

**Q3 — Rattrapage en lot.** Une commande
`manage.py rapatrier_cartes_fedow --schema <lieu> <fichier.csv>` lirait le
**même CSV** que `import_cards` (colonne 3 = `tag_id`) et appellerait
`trouver_ou_rapatrier_la_carte()` pour chaque ligne. Les cartes arriveraient
dans l'admin sans être scannées. Elle se fait en une session de plus, et la
recommandation est **oui** : c'est elle qui débloque la-cabine tout de suite.

## 7. Plan en sessions

| # | Contenu | Tests |
|---|---|---|
| S1 | `QrcodeCashless/services.py` : `trouver_ou_rapatrier_la_carte`, `FedowInjoignable`, `Detail` (§ 4.2) | pytest, `NFCcardFedow.retrieve` mocké : carte locale (0 appel réseau), rapatriement, inconnue, Fedow en panne, lieu non relié, double scan concurrent, collision `number` |
| S2 | Branchement des 4 points d'entrée + message « Fedow injoignable » | pytest des vues : scan d'une carte connue de Fedow seulement → la caisse répond normalement |
| S3 | Branchement des 12 autres sites | suite `laboutik` complète |
| S4 | (si Q3 = oui) commande `rapatrier_cartes_fedow` | pytest sur un CSV de 3 lignes, une inconnue |
| S5 | CHANGELOG, `INDEX.md`, pièges éventuels dans `tests/PIEGES.md` | — |

Vérification par mutation (règle du projet) : chaque test de S1 doit être vu
échouer quand on retire la création du miroir.

**Migration : non.**

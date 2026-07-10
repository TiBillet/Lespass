# SPEC — Formulaire d'ajout de carte NFC dans l'admin Unfold

App `QrcodeCashless`. Ajout d'un formulaire de création unitaire de carte NFC
dans l'admin, avec **Fedow (`../Fedow`) comme source de vérité**.

Date : 2026-07-09. Statut : validé.

---

## 1. Contexte et état des lieux

### 1.1 La source de vérité est aujourd'hui coupée en deux

| | Fedow standalone | Lespass |
|---|---|---|
| Modèle | `fedow_core.Card` (`../Fedow/fedow_core/models.py:1052`) | `QrcodeCashless.CarteCashless` |
| Écrit par | `POST /card/`, `import_cards.py` | rien, hors fixtures de démo |

Constats issus de l'audit du 2026-07-09 :

- `QrcodeCashless/views.py` (666 lignes) ne contient **aucun code exécutable** :
  tout le fichier est une suite de chaînes triple-quote. `urls.py` a ses deux
  `path()` commentés.
- L'ancien importeur `ApiBillet.Loadcardsfromdict` (`ApiBillet/views.py:415`),
  qui peuplait `CarteCashless`, est **entièrement commenté**.
- Le seul `CarteCashless.objects.get_or_create()` hors tests est dans
  `laboutik/management/commands/create_test_pos_data.py:1098` (fixtures).
- `fedow_core.CarteService` (`fedow_core/services.py:1264`) écrit en local
  (`wallet_ephemere`, `user`) **sans prévenir Fedow**, et n'est appelé par
  aucune vue : seuls les tests l'utilisent.
- `fedow_core.Transaction.card` et `.primary_card` sont des **FK locales** vers
  `CarteCashless` (`fedow_core/models.py:526` et `:540`).

**Décision** : Fedow reste maître. `CarteCashless` est un miroir local. Toute
création de carte passe d'abord par Fedow.

### 1.2 Correspondance des champs

| Fedow `Card` | Lespass `CarteCashless` |
|---|---|
| `uuid` (PK) | `id` auto + `uuid` (nullable, unique) |
| `first_tag_id` | `tag_id` |
| `qrcode_uuid` | `uuid` |
| `number_printed` | `number` |
| `origin` → `Origin(place, generation)` | `detail` → `Detail(origine, generation, base_url, img)` |
| `primary_places` (M2M) | `laboutik.CartePrimaire` |
| `complete_tag_id_uuid` | *absent* |
| `wallet_ephemere` | `wallet_ephemere` |

### 1.3 Deux défauts du client `fedow_connect`

1. `NFCcardFedow.create()` (`fedow_connect/fedow_api.py:847`) code en dur
   `"generation": 1`. Avec un `Detail` par génération, toutes les cartes
   atterriraient dans l'`Origin` génération 1 côté Fedow. Les deux bases
   divergeraient en silence.

   Elle **est** appelée, contrairement à une première lecture :
   `Administration/management/commands/demo_data_v2.py:464` et
   `tests/pytest/test_wallet_carte_fedow_integration.py:95`. Ces deux appelants
   ne fournissent que les trois identifiants d'une carte.

2. `create()` et `create_cards()` (ligne 901) font le même `POST /card/`.
   Duplication. Seule `create_cards()` laisse passer la génération.

**Correctif** : `create(cartes, generation=1)` devient une façade sur
`create_cards()`. Le hardcode devient un défaut explicite, les deux appelants
existants sont préservés, et l'admin appelle `create_cards()` directement avec
la génération du `Detail` choisi.

### 1.4 Le `409 CONFLICT` de Fedow est mort

`../Fedow/fedow_core/views.py:397` ne renvoie `409` que si
`card_serializer.errors[0].get('uuid')` porte le code `unique`.

Or `Card.uuid` est la clé primaire (`primary_key=True, default=uuid4`). DRF
marque automatiquement les PK en `read_only` : aucun validateur d'unicité ne
s'y applique, cette clé d'erreur n'apparaît jamais.

Un doublon réel porte sur `first_tag_id`, `qrcode_uuid` ou `number_printed`, et
produit un **`400`**. Les deux méthodes du client qui traitent le `409` traitent
donc un cas mort. On ne peut pas bâtir la réconciliation dessus.

En revanche `NFCcardFedow.retrieve(tag_id)` (ligne 822) existe et renvoie la
carte complète (`CardSerializer`), `number_printed` et `qrcode_uuid` compris.

---

## 2. Périmètre

**Dans le périmètre** : création d'une carte **à l'unité** depuis l'admin.

**Hors périmètre** : import CSV par lot, modification et suppression de carte
depuis Lespass (Fedow est maître), branchement de `CarteService` sur des vues.

---

## 3. Architecture

Tout tient dans `QrcodeCashless/admin.py`, en suivant le pattern `add_form`
déjà employé trois fois dans `Administration/admin_tenant.py` (lignes 1745,
3152, 3772).

### 3.1 `DetailAdmin` (nouveau)

Enregistré sur `staff_admin_site`, mais **`has_module_permission()` renvoie
`False`** : le modèle disparaît de l'index et de la sidebar, tout en gardant ses
vues accessibles. Seul effet visible : le bouton « + » à côté du select
`detail` du formulaire carte, greffé automatiquement par Django
(`RelatedFieldWidgetWrapper`) dès qu'une FK pointe vers un modèle enregistré sur
le même admin site.

- Formulaire de la popup : `generation`, `base_url`, `img`.
- `origine` exclu du formulaire, forcé à `connection.tenant` dans `save_model()`.
- `get_queryset()` filtre sur `origine=connection.tenant`. **Obligatoire** :
  `Detail` est en `SHARED_APPS`, il n'y a pas d'isolation automatique.

### 3.2 `CarteCashlessAddForm` (nouveau)

`ModelForm` sur `CarteCashless`.

`tag_id`, `number` et `uuid` sont déclarés comme champs de **formulaire**
(`forms.CharField`, `forms.UUIDField`), **pas** comme champs de modèle. Django
ne les confronte donc jamais au `editable=False` du modèle, et **aucune
migration n'est nécessaire**. Le flag continue de protéger les champs partout
ailleurs. C'est exactement ce que fait `MembershipAddForm` avec `email` et
`contribution`.

`detail` reste un champ de modèle : `ModelChoiceField` valide nativement la
valeur postée contre le queryset restreint par `formfield_for_foreignkey()`. Un
`pk` forgé pointant vers la génération d'un autre lieu est rejeté sans code
supplémentaire.

### 3.3 `CarteCashlessAdmin` (modifié)

- `has_add_permission` : `False` → `TenantAdminPermissionWithRequest(request)`.
- `add_form = CarteCashlessAddForm` + `get_form()` (`if obj is None`).
- `formfield_for_foreignkey()` restreint le select `detail` au tenant courant.
- `has_change_permission` et `has_delete_permission` **restent à `False`** :
  Fedow est maître.

#### Piège : `fields=None` dans `get_form()`

`ModelAdmin._changeform_view()` appelle `get_form()` en passant **explicitement**
`fields=flatten_fieldsets(self.get_fieldsets(...))`, soit
`["detail", "tag_id", "number", "uuid"]`. `modelform_factory` reçoit cette liste
et refuse les champs `editable=False` :

```
FieldError: 'tag_id' cannot be specified for CarteCashless model form
as it is a non-editable field.
```

Le correctif est de forcer `defaults["fields"] = None` **après**
`defaults.update(kwargs)` — sinon la valeur passée par `_changeform_view` écrase
la nôtre. `modelform_factory` retombe alors sur le `Meta.fields = ["detail"]` du
formulaire et conserve ses champs déclarés. Les `fieldsets` continuent de piloter
l'affichage.

Le pattern `MembershipAddForm` ne rencontre pas ce problème : ses champs custom
(`email`, `price`) n'existent pas du tout sur le modèle.

#### `Detail.__str__` renvoyait `base_url`, qui est `null=True`

Dans un `<select>`, Django appelle `str(obj)` : un `None` lève
`TypeError: __str__ returned non-string`. Corrigé en
`f"Génération {generation} — {base_url}"`. `__str__` n'étant pas un champ,
**aucune migration**.

### 3.4 Logique métier

En **fonctions module-level**, au-dessus des classes. Jamais en méthodes du
`ModelAdmin` : Unfold wrappe les méthodes de classe via son système `@action` et
leur passe `object_id` au lieu des vrais arguments (piège documenté dans
`tests/PIEGES.md`).

### 3.5 `fedow_connect/fedow_api.py` (modifié)

- Nouvelle exception `CarteInconnueDeFedow(Exception)`, levée par `retrieve()`
  sur un `404` à la place de l'`Exception` générique.
  Elle hérite d'`Exception` : les `except Exception` de `kiosk/validators.py:52`
  et `kiosk/views.py:153` se comportent à l'identique. **Zéro régression.**
- `create(cartes, generation=1)` devient une façade sur `create_cards()` :
  plus de duplication, plus de `"generation": 1` en dur.
- `create_cards()` : la gestion du `409` fantôme est remplacée par une gestion
  du `400`. Fedow renvoie une liste (une entrée par carte) de dicts
  `{champ: [messages]}` ; on en extrait les phrases, sinon l'admin afficherait
  un objet `bytes` brut :
  `b'[{"number_printed":["Un objet card avec ce champ number printed..."]}]'`.

### 1.5 Limite connue : Fedow down peut se présenter comme un `404`

Si le reverse-proxy Fedow est arrêté, Traefik répond `404` et non une erreur de
connexion. `retrieve()` interprète alors ce `404` comme « carte inconnue » et le
flux part en création. Le `POST` échoue à son tour, donc **aucune carte n'est
créée en local** — l'invariant tient — mais le message affiché est
« Fedow a refusé la création » au lieu de « Fedow est injoignable ».

Vérifié en dev le 2026-07-09. Non bloquant : la sûreté est préservée, seule la
formulation de l'erreur est imprécise.

---

## 4. Le formulaire

### 4.1 Champs

| Champ | Type | Requis | Note |
|---|---|---|---|
| `detail` | `ModelChoiceField` | oui | Filtré au tenant. Bouton « + ». |
| `tag_id` | `CharField(min=8, max=8)` | **oui** | UID physique de la puce. |
| `number` | `CharField` | non | Numéro imprimé. |
| `uuid` | `UUIDField` | non | UUID du QR code. |

`clean_tag_id()` passe en majuscules et valide `^[0-9A-F]{8}$` — même regex que
Fedow applique dans `card_tag_id_retrieve`. `clean_number()` normalise en
majuscules.

`tag_id` est obligatoire : c'est l'identifiant gravé en usine, il ne peut pas
être deviné. Créer une carte sans lui produirait une carte scannable en QR mais
pas en NFC, ce qui n'a pas d'intérêt.

### 4.2 Dérivation des identifiants

Une seule invariante : **`number == uuid.hex[:8].upper()`**.

| `number` | `uuid` | Résultat |
|---|---|---|
| vide | vide | `uuid4()` tiré, puis `number = uuid.hex[:8].upper()` |
| saisi | vide | `uuid = UUID(number.lower() + uuid4().hex[8:])` |
| vide | saisi | `number = uuid.hex[:8].upper()` |
| saisi | saisi | Vérifié. Si divergence → `ValidationError` |

Préfixer un `uuid4` par 8 caractères choisis reste un UUID v4 formel : les bits
de version et de variant vivent aux positions hex 12 et 16, hors de la zone
remplacée.

Cette convention est celle du CSV historique de Fedow
(`../Fedow/example_csv_cards_list.csv`) : dans
`.../qr/b194aeb9-0f77-…,B194AEB9,A24B043F`, `number` (`B194AEB9`) est le préfixe
de l'`uuid`, et `tag_id` (`A24B043F`) est indépendant.

### 4.3 Bloc d'aide

Via `'description': mark_safe(...)` sur le `fieldset` (mécanisme Django
standard, rendu par Unfold en tête de formulaire). Contenu :

> Les cartes sont créées d'abord chez Fedow, qui en est la source de vérité,
> puis enregistrées ici. Le **Tag ID** est l'identifiant physique de la puce
> NFC, gravé en usine : il est obligatoire et ne peut pas être deviné. Pour le
> lire, utilisez l'application libre **Mifare Classic Tool**, disponible sur
> F-Droid et sur le Play Store. Le **numéro imprimé** et l'**UUID du QR code**
> peuvent être laissés vides : ils seront générés, le numéro imprimé reprenant
> toujours le début de l'UUID.

Textes sous `_()`, source en français.

---

## 5. Flux d'exécution

### 5.1 Pourquoi les appels Fedow sont dans `clean()`

`save_model()` ne peut pas lever de `ValidationError` : Django ne l'attrape pas
et l'admin renvoie une 500. Seule une erreur levée depuis `clean()` s'affiche en
tête de formulaire avec les valeurs saisies conservées.

Écrire depuis un `clean()` est inhabituel, mais `is_valid()` n'est appelé qu'une
fois par `_changeform_view` et il n'y a pas de formset : pas de double
exécution.

### 5.2 `clean()`, dans l'ordre

1. **Lieu appairé à Fedow ?** `FedowConfig.get_solo().fedow_place_admin_apikey`
   non vide, sinon `ValidationError` explicite. Le singleton existe toujours,
   mais ses champs sont `null=True` : un tenant qui n'a jamais fait son
   handshake tomberait sur un `TypeError` illisible dans `_post`.

2. **Dérivation** des identifiants (§ 4.2).

3. **Unicité locale, explicitement.** `tag_id`, `number` et `uuid` n'étant pas
   des champs de modèle du formulaire, `ModelForm.validate_unique()` **ne les
   contrôle pas**. Sans ces trois `exists()`, un doublon irait jusqu'à
   l'`IntegrityError` PostgreSQL, soit une 500.

   `CarteCashless` vivant dans le schéma `public`, l'unicité est **globale à
   toutes les instances** : une carte appartenant à un autre lieu déclenche le
   conflit tout en restant invisible dans le changelist. Le message d'erreur
   doit le dire, sinon c'est indébuggable.

4. **`NFCcard.retrieve(tag_id)`** :
   - **carte trouvée** → *réconciliation*. On écrase `number` et `uuid` par les
     valeurs de Fedow (`number_printed`, `qrcode_uuid`), on pose un
     `messages.info` « carte récupérée depuis Fedow ». Aucun POST.
   - **`CarteInconnueDeFedow`** → *création*. `create_cards([{first_tag_id,
     qrcode_uuid, number_printed, generation: detail.generation,
     is_primary: False}])`. `201` passe ; `400` → `ValidationError` portant le
     message de Fedow ; erreur réseau → `ValidationError` « Fedow injoignable ».

5. `save_model()` recopie les quatre valeurs validées sur l'objet et appelle
   `super()`. **Plus aucun appel réseau.**

### 5.3 Idempotence

L'étape 3 s'exécute avant l'étape 4 : si la carte existe chez Fedow **et** en
local, on tombe sur le doublon sans interroger Fedow.

Si l'écriture locale plante après un POST réussi, la carte existe chez Fedow et
pas en local. Rejouer l'ajout passe l'étape 3, trouve la carte à l'étape 4, et
la miroite. **Le formulaire est auto-réparant.** C'est aussi le chemin de
récupération de l'état de désynchronisation actuel de l'instance.

---

## 6. Tests

Tout en pytest DB-only. Aucun JavaScript, donc pas d'E2E.
Base : `tests/pytest/test_carte_cashless_admin.py` (existant).

`FedowAPI` est mocké, comme dans `tests/pytest/test_kiosk_flow.py:111`.

Cas couverts :

- les quatre lignes de la matrice de dérivation (§ 4.2) ;
- rejet quand `number` et `uuid` saisis divergent ;
- rejet d'un `tag_id` non hexadécimal, ou de longueur ≠ 8 ;
- mise en majuscules de `tag_id` et `number` ;
- les trois conflits d'unicité locale ;
- réconciliation : Fedow connaît la carte, le local l'ignore → création locale
  avec les valeurs de Fedow, **aucun POST** ;
- `400` de Fedow remonté en `ValidationError` ;
- lieu non appairé à Fedow ;
- filtrage du select `detail` par tenant.

**Piège** (`tests/PIEGES.md`) : `CarteCashless` étant en `SHARED_APPS`, sa table
n'existe pas dans le schéma de test d'un `FastTenantTestCase`. Passer par
`schema_context('lespass')` et l'`APIClient`.

---

## 7. Fichiers touchés

| Fichier | Changement |
|---|---|
| `QrcodeCashless/admin.py` | `DetailAdmin`, `CarteCashlessAddForm`, `CarteCashlessAdmin` modifié, fonctions module-level (~150 lignes) |
| `fedow_connect/fedow_api.py` | `CarteInconnueDeFedow`, `retrieve()` 404, suppression de `create()`, `create_cards()` gère le `400` |
| `tests/pytest/test_carte_cashless_admin.py` | Nouveaux tests |

**Migration : non.** `tag_id`, `number` et `uuid` restent `editable=False` sur
le modèle ; ils ne sont manipulés que comme champs de formulaire.

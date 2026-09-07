# Le wallet du user est déclaré à Fedow, au lieu d'hériter du wallet anonyme de la carte / User wallet declared to Fedow instead of inheriting the card's anonymous wallet

**Date :** 2026-09-05
**Migration :** Non

## Resume / Summary

**Quoi / What :** `aligner_wallet_user_sur_fedow` (seed de démo) fusionnait dans le mauvais
sens : il attribuait au user l'uuid du **wallet éphémère** de sa carte. Il déclare désormais
le user auprès de Fedow (`wallet/get_or_create`, qui transmet sa clé publique), puis demande
à Fedow de fusionner le wallet éphémère **dans** celui du user (`wallet/linkwallet_card_number`).
/ The demo seed merged the wrong way round, giving the user the uuid of their card's
**ephemeral wallet**. It now declares the user to Fedow (passing their public key), then has
Fedow merge the ephemeral wallet **into** the user's.

**Pourquoi / Why :** Un wallet éphémère n'a **pas** de clé publique — côté Fedow,
`wallet_creator()` n'en stocke une que si on la lui passe, et `Card.get_wallet()` ne lui en
passe aucune. Le user Lespass se retrouvait donc avec un wallet que Fedow ne peut pas
authentifier. Toute requête signée en son nom cassait sur `wallet.public_key()`
(`AttributeError: 'NoneType' object has no attribute 'encode'`, HTTP 500 côté Fedow sur
`/wallet/retrieve_by_signature/`).
/ An ephemeral wallet has NO public key, so Fedow could not authenticate anything signed on
behalf of that user.

**Le symptôme était silencieux côté POS**, donc plus dangereux qu'un plantage :
`lire_depensable_fed_frais` (`laboutik/views.py:1145-1149`) attrape l'exception et renvoie
`(0, False)`. Le solde FED des cartes clientes était donc lu comme **0**, et le cran legacy
de la cascade ne pouvait jamais les débiter — sans aucune erreur visible à la caisse.

Périmètre : uniquement les cartes **liées à un user** via cet alignement (CLIENT1/CLIENT2).
Une carte réellement anonyme n'emprunte pas ce chemin — son solde est lu par
`obtenir_wallet_carte_depuis_fedow`, avec la clé de place et sans signature user.

Bug antérieur au banc V1/V2 : introduit le 2026-06-25 par `b0d7425f`, soit 5 jours avant le
câblage du banc. Il ne pouvait pas être attrapé par les tests, qui mockent Fedow — il faut un
Fedow réel pour le déclencher.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `Administration/management/commands/demo_data_v2.py` | `aligner_wallet_user_sur_fedow` réécrite : déclaration du user (`get_or_create_wallet`) → liaison de la carte (`linkwallet_card_number`) → migration locale du solde et de l'historique. Garde `can_fedow()` ajoutée, et restitution du wallet local si Fedow échoue. |
| `tests/pytest/test_demo_wallet_alignment.py` | Réécrit : le mock porte désormais sur `FedowAPI` (le contrat réel) et non plus sur `obtenir_wallet_carte_depuis_fedow`, qui n'est plus appelé. 6 tests, mock **strict** (`create_autospec`). |
| `laboutik/management/commands/create_test_pos_data.py` | Les **trois** créations de `CarteCashless` (primaire, clients 1-2, client 3 jetable) posent un uuid déterministe via `_qrcode_uuid_depuis_tag`, au lieu d'un `uuid4()` aléatoire. |
| `Administration/management/commands/demo_data_v2.py` | **Suite à relecture** : l'échec de `linkwallet_card_number` est toléré et journalisé. Fedow n'accepte que des cartes libres (`Card.objects.filter(user__isnull=True)`, `Fedow/fedow_core/serializers.py:636`), donc un second passage du seed renvoie 400 — état attendu, pas une anomalie. Sans cette tolérance, la fonction levait **avant** la migration du solde : le user pointait son wallet Fedow pendant que son solde restait sur le wallet local orphelin, soit 0 € au point de vente, sans message. |

### A savoir / Worth knowing

Côté Fedow, `wallet.public_key()` était appelé sans vérifier que `public_pem` existe → **500
au lieu d'un 403**, ce qui rendait le diagnostic pénible (une traceback masquant un simple
refus d'authentification). **Corrigé par le mainteneur** dans le repo Fedow :
`fedow_core/permissions.py:100` et `:181` portent désormais la garde.

### Ce que le flush réel a corrigé en plus / What the real flush caught

Le premier cycle complet sur le banc a révélé deux défauts que les tests ne pouvaient pas voir.

**1. Appel sur la mauvaise classe.** L'étape 2 appelait
`fedowAPI.wallet.linkwallet_card_number`, or cette méthode vit sur `NFCcardFedow`
(`fedow_connect/fedow_api.py:997`), donc `fedowAPI.NFCcard`. Symptôme dans les logs du flush :
`'WalletFedow' object has no attribute 'linkwallet_card_number'`. Les users étaient bien
déclarés à Fedow (étape 1 réussie, plus de 500), mais les **cartes n'étaient pas liées** :
`user=None`, `ephemere=True`. Le solde d'une carte serait allé sur son wallet éphémère, pas
sur celui du user.

**Le test ne pouvait pas l'attraper** : un `mock.MagicMock()` accepte n'importe quel attribut,
donc `api.wallet.linkwallet_card_number` « existait » dans le test et validait l'appel fautif.
Le mock est désormais **strict** — `mock.create_autospec(WalletFedow)` et
`create_autospec(NFCcardFedow)` — et un appel hors contrat lève `AttributeError`. Vérifié par
mutation : remettre l'appel d'origine fait échouer `test_aligner_declare_le_user_a_fedow`.

**2. Une troisième création de carte oubliée.** `create_test_pos_data` crée les cartes à
**trois** endroits ; seuls deux avaient été alignés sur le qrcode_uuid déterministe. La carte
client 3 (« jetable », utilisée par les tests Playwright) gardait un `uuid4()` aléatoire, donc
son QR code restait inutilisable pour la liaison. Corrigée.

---

## Comment tester (a la main) / Manual test

### Test 1 — automatique

```bash
docker exec lespass_django poetry run pytest tests/pytest/test_demo_wallet_alignment.py -q
```

Attendu : **6 passed**.

Les tests ont été validés par mutation (un test qui n'échoue jamais ne prouve rien) :
- retirer l'appel `linkwallet_card_number` → 1 échec ;
- reproduire le bug d'origine (ne pas déclarer le user, garder le wallet de la carte) → **3 échecs**, dont `test_aligner_declare_le_user_a_fedow` ;
- retirer la tolérance sur l'échec de liaison → 1 échec (`test_aligner_migre_le_solde_meme_si_la_liaison_de_carte_echoue`).

### Test 2 — le wallet porte bien une clé publique après un flush

Après un cycle complet Fedow → Lespass → LaBoutik :

```bash
docker exec fedow_django bash -c "cd /home/fedow/Fedow && poetry run python manage.py shell -c \"
from fedow_core.models import Card
for tag in ['52BE6543','33BC1DAA']:
    c = Card.objects.filter(first_tag_id=tag).first()
    w = c.get_wallet()
    print(tag, 'user=', c.user, 'public_pem=', 'OUI' if w.public_pem else 'NON', 'ephemere=', c.is_wallet_ephemere())
\""
```

Attendu, pour les deux cartes : `user=` renseigné, `public_pem= OUI`, `ephemere= False`.

**Avant le correctif** : `user= None`, `public_pem= NON`, `ephemere= True`.
**Obtenu sur le banc (2026-09-05)** : `52BE6543 user=client1@test.loc public_pem=OUI
ephemere=False`, idem pour `33BC1DAA`. La carte primaire `A49E8E2A` reste anonyme — c'est
voulu, elle n'a pas de porteur.

Preuve que le chemin qui plantait fonctionne, via `lire_depensable_fed_frais` :
`52BE6543 FED=0 centimes disponible=True`. **`disponible=True` est la preuve** : ce booléen
ne passe à `True` que si l'appel Fedow signé a abouti (`laboutik/views.py:1144`) ; toute
exception le forçait à `False`. `FED=0` est normal, aucun FED n'a encore été chargé.

### Rejouer l'alignement sans re-flusher

L'alignement est idempotent et rejouable à chaud, utile après une correction :

```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django.conf import settings
from django_tenants.utils import tenant_context
from Customers.models import Client
from QrcodeCashless.models import CarteCashless
from Administration.management.commands.demo_data_v2 import aligner_wallet_user_sur_fedow
with tenant_context(Client.objects.get(schema_name='lespass')):
    for tag in [settings.DEMO_TAGID_CLIENT1, settings.DEMO_TAGID_CLIENT2]:
        carte = CarteCashless.objects.filter(tag_id=tag).first()
        print(tag, '->', aligner_wallet_user_sur_fedow(carte) if carte else 'ABSENTE')
"
```

### Test 3 — plus de 500 au scan

1. Ouvrir `https://lespass.tibillet.localhost/laboutik/caisse/` (connecté en `jturbeaux@pm.me`,
   admin du tenant `lespass`).
2. Ouvrir la caisse avec la carte primaire, puis scanner la carte client 1 (`52BE6543`) via
   l'input `#nfc-simu-manual-input`.
3. Dans les logs Fedow : plus aucun `AttributeError` ni `500` sur `/wallet/retrieve_by_signature/`.
   La requête doit répondre **200**.
4. Le solde FED affiché doit être réel (et non 0 par dégradation silencieuse).

### Test 4 — non-régression du périmètre

```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_wallet_carte_fedow.py \
  tests/pytest/test_wallet_carte_fedow_integration.py \
  tests/pytest/test_caisse_navigation.py \
  tests/pytest/test_controlvanne_review_fixes.py -q
```

Attendu : **22 passed**.

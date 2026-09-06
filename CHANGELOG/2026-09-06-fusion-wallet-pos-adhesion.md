# Fusion du wallet éphémère au POS V2 (adhésion) / Ephemeral wallet merge at the V2 POS

**Date :** 2026-09-06
**Migration :** Non

## Resume / Summary

**Quoi / What :** au point de vente V2, une adhésion payée en espèces ou par CB avec une
carte NFC anonyme ne liait la carte qu'en local. Le membre est désormais déclaré au réseau
Fedow et la carte y est rattachée **avant** le bloc transactionnel, comme le fait déjà le
parcours web `/qr/`.
/ At the V2 POS, a cash/card membership paid with an anonymous NFC card only linked the card
locally. The member is now declared to the Fedow network and the card attached there
**before** the transaction block, like the existing `/qr/` web path.

**Pourquoi / Why :** sans déclaration, le membre recevait un portefeuille local à uuid
aléatoire, inconnu du réseau. Fedow authentifie chaque requête signée par l'en-tête
`Wallet: <uuid>` : ce porteur ne pouvait plus rien signer, son solde fédéré devenait
invisible au comptoir, et toute déclaration ultérieure échouait sur « Wallet and member
mismatch », définitivement.
/ Without that declaration the member got a random-uuid local wallet the network could not
authenticate: their federated balance became invisible at the counter and any later
declaration failed permanently.

**Le paiement NFC est corrigé aussi / The NFC flow is fixed too :** une adhésion réglée
avec la carte elle-même prenait `carte.user` comme membre. Sur une carte anonyme cela
valait `None` : le portefeuille était débité, la ligne de vente créée, et **aucune adhésion
enregistrée**. Le client payait pour rien, sans message. L'identification est désormais
vérifiée **avant tout débit**, et la vente est refusée si elle manque.
/ An NFC-paid membership used `carte.user` as the member. On an anonymous card that was
`None`: the wallet was debited, the sale line created, and **no membership recorded**.
Identification is now checked **before any debit**.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `laboutik/views.py` | `_identifier_adherent()`, `_declarer_adherent_au_reseau()`, `_resoudre_adherent_hors_atomic()` et `_fedow_a_deja_lie_la_carte()` (neufs) ; `_creer_adhesions_depuis_panier()` ne fait plus d'appel réseau et passe par `CarteService.lier_a_user` ; recharges exécutées **avant** les adhésions ; `_payer_par_nfc()` : garde d'identification avant tout débit, déclaration réseau juste avant la transaction, fusion locale après les débits ; avertissements caissier au contexte |
| `fedow_connect/services.py` | **Neuf** — `declarer_wallet_user_a_fedow()` : déclare le membre, et réaligne un portefeuille local divergent en déplaçant sa valeur par `Transaction(FUSION)` |
| `fedow_core/services.py` | `fusionner_wallet_ephemere` lève `WalletUserAbsent` au lieu de fabriquer un portefeuille local ; lecture des Tokens sous `select_for_update` ; garde `qrcode_uuid` vide et repli `carte.detail` dans `lier_a_user` |
| `fedow_core/exceptions.py` | `WalletUserAbsent` |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Bandeau « Carte non rattachée » |
| `BaseBillet/triggers.py` | Retrait du push de l'adhésion vers Fedow |
| `fedow_connect/fedow_api.py` | Retrait de la classe `MembershipFedow` |
| `QrcodeCashless/` | Retrait du code mort : `views.py`, `urls.py`, templates et statics `html5up-dimension/` |
| `TiBillet/settings.py`, `TiBillet/urls_tenants.py` | Retrait des références au code supprimé |

**Décisions actées :** Fedow devient une dépendance dure (`can_fedow()` faux → vente
refusée, aucun repli local) ; le POS réutilise `CarteService.lier_a_user` au lieu d'une
seconde implémentation de la fusion ; un portefeuille local divergent est réaligné à la
volée. Aucune commande de réparation : la V2 n'est pas en production.

**Traductions :** cette modification ajoute 6 chaînes traduisibles (messages caissier et
bandeau). **Le workflow i18n est à lancer par le mainteneur.**

---

## Comment tester (a la main) / Manual test

Prérequis : le Fedow de dev tourne, le tenant a une place Fedow (`can_fedow()` vrai), une
carte NFC anonyme provisionnée et **chargée** en monnaie locale.

### Test 1 — scénario nominal
1. Au POS, ouvrir un point de vente qui porte un produit adhésion.
2. Mettre une adhésion au panier, payer en **espèces**.
3. À l'écran d'identification : scanner la **carte anonyme chargée**, saisir un email neuf.
4. Attendu : écran de succès sans avertissement.
5. Vérifier en base que le membre porte le portefeuille du réseau, pas un uuid local :
```bash
docker exec lespass_django poetry run python /DjangoFiles/manage.py shell -c "
from django_tenants.utils import tenant_context
from Customers.models import Client
from AuthBillet.models import TibilletUser
from QrcodeCashless.models import CarteCashless
from fedow_connect.fedow_api import FedowAPI
tenant = Client.objects.get(schema_name='lespass')
with tenant_context(tenant):
    u = TibilletUser.objects.get(email='<email saisi>')
    c = CarteCashless.objects.get(tag_id='<TAG>')
    print('carte.user       :', c.user)
    print('wallet ephemere  :', c.wallet_ephemere)
    print('wallet du membre :', u.wallet.uuid)
    print('wallet chez Fedow:', FedowAPI().NFCcard.card_tag_id_retrieve('<TAG>')['wallet_uuid'])
"
```
`carte.user` = le membre, `wallet ephemere` = None, et **les deux derniers uuid doivent être
identiques**. C'est l'assertion qui compte : elle prouve que le réseau et Lespass sont
d'accord sur le propriétaire.

### Test 2 — adhésion ET recharge dans le même panier
1. Même geste, en ajoutant une recharge de 10 € au panier.
2. Attendu : le solde du membre = solde de la carte **+ 10 €**.
   Avant ce correctif, les 10 € étaient encaissés puis perdus sur le portefeuille éphémère
   détaché.

### Test 3 — cas limites
- **Membre possédant déjà une carte** : scanner une seconde carte anonyme. Attendu :
  l'adhésion est enregistrée, la carte n'est **pas** rattachée, bandeau « Carte non
  rattachée ». Le solde de la carte scannée est intact.
- **Réseau injoignable** : arrêter le conteneur Fedow, refaire le test 1. Attendu : la vente
  est **refusée** avec « Le reseau TiBillet ne repond pas », et **rien** n'est écrit — ni
  ligne de vente, ni adhésion.
- **Ni carte ni email** : valider une adhésion sans identification. Attendu : message
  « Identification du membre obligatoire », en 400 (auparavant : une erreur 500).

### Test 4 — adhésion réglée avec la carte elle-même (NFC)
1. Panier : une adhésion. Scanner la carte anonyme chargée. Payer **par NFC**.
2. Sans saisir d'email : attendu **refus**, message « Identification du membre obligatoire »,
   et le solde de la carte **inchangé**. Avant ce correctif, le solde était débité et aucune
   adhésion n'était créée.
3. Avec l'email : attendu succès, adhésion enregistrée, carte rattachée, et solde restant
   = solde initial **moins** le prix de l'adhésion.

### Tests automatiques
```bash
docker exec lespass_django poetry run pytest \
  tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py \
  tests/pytest/test_scan_qr_carte_v2.py -v
```
11 tests couvrent ce chantier, chacun validé par mutation (le correctif cassé volontairement
doit faire échouer son test).

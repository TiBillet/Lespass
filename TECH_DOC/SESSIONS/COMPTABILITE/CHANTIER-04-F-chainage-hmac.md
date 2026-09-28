# Chantier 04-F — Anti-rejeu QR, chaînage HMAC (tireuse, QR/NFC, vider carte), verrou, archive

> **Statut** : 📋 SPEC RÉDIGÉE — relue par Fable (×2) et Opus, corrigée (2026-09-27)
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décisions : D21 à D26, D28 — Dépend de : A (montants justes), B (`total_ht` juste)
> Effort estimé : 3 j (3 sessions, §7)

---

## 1. Le principe, simplement

Pour la certification LNE (exigence 8), chaque ligne de vente reçoit une
**empreinte** (HMAC) calculée à partir de ses données **et de l'empreinte de la
ligne précédente**. Les lignes forment une chaîne : si quelqu'un modifie une ligne
après coup, la chaîne casse et la vérification le montre.

Aujourd'hui, seules les lignes créées par les deux fonctions de vente de la caisse
sont chaînées. La **tireuse** (dans le ticket Z), le **paiement QR/NFC** et le
**« vider carte »** de la caisse (dans le ticket Z) n'ont pas d'empreinte. Et
l'**archive fiscale** n'exporte pas la tireuse.

Cette fiche corrige aussi un **défaut d'argent** trouvé en rédigeant : le paiement
par QR code peut **débiter deux fois** le même client (§3). Il est livré en premier.

## 2. Le mécanisme actuel (vérifié le 2026-09-27)

`laboutik/integrity.py` :

| Fonction | Rôle |
|---|---|
| `calculer_hmac(ligne, cle, previous_hmac)` (l.28-70) | HMAC-SHA256 sur `uuid, datetime, amount, total_ht, qty (%.6f), vat (%.2f), payment_method, status, sale_origin, weight_quantity, previous_hmac` |
| `obtenir_previous_hmac(sale_origin)` (l.73-95) | dernière empreinte de la chaîne, triée `(-datetime, -pk)`. **Une chaîne par tenant et par `sale_origin`** |
| `verifier_chaine(queryset, cle)` (l.98-164) | recalcule la chaîne triée `(datetime, pk)`, en partant de `""`. **Saute sans erreur** les lignes sans empreinte |
| `calculer_total_ht(ttc, taux)` (l.167) | HT d'un TTC |

- Blocs de chaînage actuels (copies identiques) : `laboutik/views.py` ~l.5124-5156
  (`_creer_lignes_articles`) et ~l.5434-5460 (`_creer_lignes_articles_cascade`).
- `datetime` d'une `LigneArticle` est posé à l'INSERT (`auto_now_add`,
  `BaseBillet/models.py` ~l.3667) ; `pk` est un **UUID aléatoire** (pas un compteur :
  deux lignes à la même microseconde ont un ordre imprévisible).
- `verify_integrity.py` (l.52) ne vérifie que `LABOUTIK`. En dev : 20 lignes LABOUTIK
  chaînées sur 235 (chaîne valide) ; 0 sur TIREUSE, QRCODE_MA, NFC_MA.
- `laboutik/archivage.py` (~l.135) n'exporte que `sale_origin=LABOUTIK`.

## 3. Anti-rejeu du paiement QR (session F-1, livrée en premier)

### 3.1 Le défaut

`valid_payment` (`BaseBillet/views.py` ~l.2107) charge la ligne par son uuid **sans
filtre de statut**, puis débite chez Fedow (`to_place_from_qrcode`, ~l.2146). La garde
« déjà payé » n'existe qu'à l'écran de scan (GET, ~l.2062, et seulement `== VALID`)
et dans le validateur NFC (`BaseBillet/validators.py` ~l.1373, `status=CREATED`,
lecture non atomique avec le débit). Un double clic sur « Valider », ou un POST direct
sur un QR code déjà payé, **débite le client une deuxième fois**. Le test existant
`test_un_qrcode_deja_paye_ne_peut_pas_etre_rejoue` (~l.292) ne teste que le GET.

Fedow n'a pas de clé d'idempotence sur ce débit (`fedow_connect/fedow_api.py`
~l.1056-1098 : exception sur toute réponse ≠ 201).

### 3.2 Le correctif

Une « réservation » atomique de la ligne avant tout appel réseau, sans verrou tenu
pendant l'appel Fedow :

```python
# On reserve la ligne AVANT de debiter : une seule requete passe de CREATED a
# UNPAID (« paiement en cours »). Un double clic ou un rejeu trouve 0 ligne a
# reserver et s'arrete, sans jamais appeler Fedow.
# / Reserve the line BEFORE debiting: only one request moves it from CREATED
#   to UNPAID. A double click or a replay finds nothing and stops.
nombre_reserve = LigneArticle.objects.filter(
    uuid=ligne_article_uuid, status=LigneArticle.CREATED,
).update(status=LigneArticle.UNPAID)
if nombre_reserve == 0:
    ... « Ce paiement a déjà été traité. »
```

`.update()` ne déclenche pas le signal de transitions de statut
(`BaseBillet/signals.py` ~l.333-350, ~l.400-430) : voulu. Les lecteurs de `UNPAID`
(Stripe, crowds, booking, panier, comptabilité en ligne, filtre api_v2) ne touchent
jamais une ligne QR (vérifié).

| Ce qui arrive ensuite | Statut de la ligne d'origine |
|---|---|
| Fedow **refuse** explicitement (réponse ≠ 201 : solde, validation) | remise à `CREATED` : le QR reste payable |
| **Erreur réseau ou délai dépassé** sur `to_place_from_qrcode` (on ne sait pas si Fedow a débité) | `FAILED` + contexte journalisé : plus jamais payable, vérification manuelle dans Fedow |
| Débit fait, puis échec d'une étape suivante (§5.3) | `FAILED`, `metadata["transactions"]` conservé (même format chaîne JSON que l'existant) |
| Tout réussit | supprimée et remplacée par les lignes de paiement (§5.3) |

- `process_with_nfc` passe par le même mécanisme.
- La garde GET de l'écran de scan (~l.2062) passe de `== VALID` à `!= CREATED` : une
  ligne réservée ou en échec n'affiche plus l'écran de paiement.
- `process_with_nfc` ~l.2005 fait `raise f"..."` (lever une chaîne = `TypeError`,
  erreur 500) : remplacé par une réponse d'erreur explicite, nécessaire pour les
  nouveaux chemins d'échec.

## 4. Chaînage : une fonction partagée, verrou et horodatage (session F-2)

Le bloc existe en deux copies ; on va en avoir six. On le déplace une seule fois :

```python
def chainer_lignes(lignes_a_chainer, sale_origin):
    """
    Pose datetime, total_ht, previous_hmac et hmac_hash sur des lignes deja creees.
    / Sets datetime, total_ht, previous_hmac and hmac_hash on created lines.

    LOCALISATION : laboutik/integrity.py

    A appeler DANS la transaction qui a cree les lignes.
    / Must be called INSIDE the transaction that created the lines.

    Une chaine par sale_origin : toutes les lignes doivent avoir cette origine.
    / One chain per sale_origin.
    """
    # Un seul chainage a la fois par chaine. Le verrou est libere au COMMIT.
    # / One chaining at a time per chain; released at COMMIT.
    with connection.cursor() as curseur:
        curseur.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [f"hmac-{connection.schema_name}-{str(sale_origin)}"],
        )

    # L'heure de la ligne est reposee SOUS le verrou. verifier_chaine() trie par
    # (datetime, pk) : si l'heure restait celle de la creation (avant le verrou),
    # deux encaissements simultanes seraient chaines dans un ordre et verifies
    # dans l'autre, et la verification signalerait une falsification inexistante.
    # / datetime is reset UNDER the lock so chain order == verification order.
    maintenant = timezone.now()
    previous_hmac = obtenir_previous_hmac(sale_origin=sale_origin)
    for ligne in lignes_a_chainer:
        ligne.datetime = maintenant
        ...  # total_ht (fiche B), previous_hmac, hmac_hash
        ligne.save(update_fields=["datetime", "total_ht", "hmac_hash", "previous_hmac"])
        previous_hmac = ligne.hmac_hash
```

- Toutes les lignes d'un même appel ont la même heure : leur ordre relatif suit
  `pk` (UUID aléatoire), **pas** l'ordre de la boucle. Pour que la vérification
  relise la chaîne dans l'ordre d'écriture, on **trie `lignes_a_chainer` par `pk`**
  avant la boucle.
- `total_ht` : formule de la fiche B.
- Les deux blocs de `laboutik/views.py` appellent `chainer_lignes`.
- Verrou d'idempotence existant (`laboutik/views.py` ~l.4331, de session) pris avant ;
  verrou de chaîne (de transaction) après : même ordre partout, pas d'inter-blocage.
- `test_stock_visuel_pos.py:401` appelle `_creer_lignes_articles` hors `atomic` : ne
  pas ajouter de garde `in_atomic_block` qui lèverait ; le verrou y est sans effet
  mais inoffensif.
- Les sauvegardes `update_fields` passent par le signal de statut en VALID → VALID
  (`no_change`) : sans effet.

## 5. Les nouveaux points de chaînage (session F-2 et F-3)

### 5.1 Tireuse et « vider carte »

| Endroit | Changement |
|---|---|
| `controlvanne/billing.py` `facturer_tirage()` | `chainer_lignes(lignes_creees, SaleOrigin.TIREUSE)` après la boucle, dans l'`atomic` existant (~l.223). Import local. |
| `fedow_core/services.py` `rembourser_en_especes()` | `chainer_lignes(lignes_creees, SaleOrigin.LABOUTIK)` dans son `atomic` existant (import local `laboutik`, déjà pratiqué ~l.681-686) |

### 5.2 Archive fiscale

`laboutik/archivage.py` (~l.135) : `sale_origin__in=ORIGINES_ENCAISSEES_PAR_LE_LIEU`
(LABOUTIK et TIREUSE, le périmètre du Z) au lieu de `LABOUTIK` seul.

### 5.3 QR/NFC : réseau d'abord, puis une transaction

Après la réservation (§3) et le débit :

```python
# Tous les appels reseau AVANT de toucher a la base.
# / All network calls BEFORE touching the database.
categories_par_asset = {}
for transaction_fedow in transactions:
    asset_uuid = str(transaction_fedow["asset"])
    if asset_uuid not in categories_par_asset:
        categories_par_asset[asset_uuid] = fedowAPI.asset.retrieve(asset_uuid)["category"]
# (echec ici : ligne d'origine -> FAILED, §3.2)

with db_transaction.atomic():
    ligne_article.delete()
    lignes_creees = []
    for index, transaction_fedow in enumerate(transactions):
        ...  # moyen de paiement, amount/qty (fiche A), create
    chainer_lignes(lignes_creees, SaleOrigin.QRCODE_MA)   # NFC_MA dans process_with_nfc
    for ligne in lignes_creees:
        # Synchro vers l'ancien LaBoutik, APRES l'enregistrement definitif.
        # / Sync to legacy LaBoutik, AFTER the final commit.
        db_transaction.on_commit(
            lambda uuid_ligne=ligne.uuid: send_sale_to_laboutik.delay(uuid_ligne)
        )
```

TVA de ces lignes : taux par défaut du lieu, inchangé (D26).

### 5.4 La vérification

`verify_integrity.py` boucle sur **chaque** origine chaînée (LABOUTIK, TIREUSE,
NFC_MA, QRCODE_MA) et appelle `verifier_chaine()` **une fois par origine**, sur la
chaîne complète.

Commentaire de contrainte dans le code : ne jamais passer à `verifier_chaine()` un
queryset qui mélange plusieurs origines, ni un sous-ensemble filtré (la fonction
repart de `""`).

**Trous** (D24) : pour chaque origine, `verify_integrity` liste en **avertissement**
les lignes **`VALID`** sans empreinte créées après la première ligne chaînée de cette
origine. Les lignes en attente, réservées ou en échec ne sont pas des trous. Les
lignes du webhook `Membership_fwh` y apparaîtront : attendu (tronc §6).

## 6. Tests

Schéma de test dédié (D28) : une ligne chaînée cassée par un autre test (ou une
mutation) sur la base partagée ferait échouer la vérification de la chaîne complète.
`TestPayerParQrCode` est déjà un `FastTenantTestCase` (~l.83) :
`captureOnCommitCallbacks` est disponible. Pièges `tests/PIEGES.md` §9.56-9.58.

| # | Scénario | Assertion (rouge aujourd'hui sauf mention) |
|---|---|---|
| F1 | `valid_payment` POST sur une ligne déjà `VALID` | refus, `to_place_from_qrcode` **jamais appelé** |
| F2 | deux POST `valid_payment` successifs sur la même ligne `CREATED` | un seul appel à `to_place_from_qrcode` |
| F3 | Fedow refuse le débit (exception de réponse ≠ 201) | ligne remise à `CREATED` |
| F4 | `to_place_from_qrcode` lève `ConnectionError` | ligne en `FAILED`, nouveau POST refusé sans appel Fedow |
| F5 | `asset.retrieve.side_effect = [{"category": "TLF"}, Exception(...)]` (deux uuids d'asset distincts) | ligne d'origine en `FAILED` avec `metadata["transactions"]`, aucune ligne de paiement |
| F6 | GET de l'écran de scan sur une ligne `UNPAID` | message « déjà traité » |
| F7 | `process_with_nfc` : erreur Fedow | réponse d'erreur explicite, pas de `TypeError` |
| F8 | tirage réel via `facturer_tirage()` | `hmac_hash` non vide ; `verifier_chaine(TIREUSE)` valide |
| F9 | deux tirages successifs | `ligne2.previous_hmac == ligne1.hmac_hash` |
| F10 | tirage réparti TNF + TLF (2 lignes) | lignes chaînées entre elles, chaîne valide |
| F11 | `valid_payment` et `process_with_nfc` répartis | lignes QRCODE_MA / NFC_MA chaînées, chaînes valides |
| F12 | « vider carte » à la caisse | lignes LABOUTIK chaînées, chaîne valide |
| F13 | chaînage de deux lots simulant l'ordre « créé avant, chaîné après » (datetime de création antérieure forcée) | `verifier_chaine` valide (horodatage sous verrou) |
| F14 | altération : `amount` d'une ligne TIREUSE modifié après coup | `verifier_chaine(TIREUSE)` invalide |
| F15 | `verify_integrity` | un résultat par origine ; un trou `VALID` créé à la main est signalé ; une ligne QR `CREATED` ne l'est pas |
| F16 | `send_sale_to_laboutik` (mock) après `valid_payment` | appelé une fois par ligne, dans les callbacks `on_commit` |
| F17 | archive fiscale | contient une ligne TIREUSE |
| F18 | `chainer_lignes` (curseur espionné) | exécute `pg_advisory_xact_lock` avant `obtenir_previous_hmac` |

Le verrou n'a pas de vrai test de concurrence (base partagée, pas de
`transaction=True`) : F13 couvre l'ordre, F18 la prise du verrou ; la limite est
documentée dans `tests/PIEGES.md`, avec la correction du piège 9.58 (`pk` est un UUID,
pas un compteur).

### Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| réservation `CREATED → UNPAID` retirée | F1, F2 |
| `ConnectionError` traitée comme un refus (→ `CREATED`) | F4 |
| `asset.retrieve` remis dans la transaction, après `delete()` | F5 |
| garde GET remise à `== VALID` | F6 |
| appel `chainer_lignes` retiré de `facturer_tirage` | F8, F9 |
| appel retiré de `rembourser_en_especes` | F12 |
| `ligne.datetime = maintenant` retiré | F13 |
| `previous_hmac` forcé à `""` | F9, F10 |
| `amount` retiré de `calculer_hmac` | F14 (et `test_integrity_hmac.py::test_hmac_detecte_modification`, attendu) |
| `on_commit` retiré | F16 |
| archive remise à `LABOUTIK` seul | F17 |
| verrou retiré | F18 |

## 7. Découpage en sessions

| Session | Contenu | Tests |
|---|---|---|
| F-1 | Anti-rejeu QR : réservation, refus / erreur réseau / échec, garde GET, `raise f"..."` | F1-F7 |
| F-2 | `chainer_lignes` (verrou, horodatage), blocs caisse, tireuse, vider carte, archive | F8-F10, F12-F14, F17, F18 |
| F-3 | QR/NFC : réseau d'abord + transaction + chaînage + `on_commit` ; `verify_integrity` par origine et trous | F11, F15, F16 |

## 8. Fichiers touchés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | réservation, statuts d'échec, garde GET, réseau d'abord, `atomic`, `chainer_lignes`, `on_commit`, `raise` (×2 vues) |
| `laboutik/integrity.py` | `chainer_lignes()` avec verrou et horodatage |
| `laboutik/views.py` | 2 blocs remplacés par `chainer_lignes()` |
| `controlvanne/billing.py` | appel `chainer_lignes` |
| `fedow_core/services.py` | appel `chainer_lignes` |
| `laboutik/archivage.py` | périmètre LABOUTIK + TIREUSE |
| `laboutik/management/commands/verify_integrity.py` | boucle par origine + trous signalés |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | F1-F7, F11, F16 |
| `tests/pytest/test_chainage_hmac_origines.py` (nouveau) | F8-F10, F12-F15, F17, F18 |
| `tests/PIEGES.md` | limite du test de concurrence ; piège 9.58 corrigé (`pk` UUID) ; « une origine par vérification » |

Pas de migration.

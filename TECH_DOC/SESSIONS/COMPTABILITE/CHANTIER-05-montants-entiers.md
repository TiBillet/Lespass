# Chantier 05 — Montants entiers : Vente, articles, règlements (tronc commun)

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — en attente des relectures Fable + Opus
> **Branche** : `main-fedow-import`
> **Contexte** : environnement de **dev uniquement**. Aucune donnée historique à
> rattraper, aucune ligne existante à migrer. Le format HMAC peut être redéfini.
> **Diagnostic** : [`CHANTIER-05-diagnostic.md`](CHANTIER-05-diagnostic.md)
> **Remplace** : la règle d'or « `total = amount × qty` » du chantier 04 (§2 du tronc 04)
> et les fiches 04-F-2 / 04-F-3 (chaînage ligne par ligne).

Ce fichier est le **tronc commun**. Chaque fiche (`CHANTIER-05-0`, puis `A` à `H`)
se livre et se teste seule, dans l'ordre du §6.

---

## 1. Objectif

**Aucun cas limite possible sur un centime.**

Aujourd'hui, une seule table (`LigneArticle`) porte à la fois **l'article vendu** et
**le règlement**. Un article payé avec deux moyens est coupé en quantités
fractionnaires (1,428571 + 1,571429), puis chaque lecteur recalcule l'argent par
`amount × qty`, avec son propre arrondi. Résultat : des centimes perdus ou inventés
selon l'écran (diagnostic §1-2), deux clôtures, deux plans comptables, deux FEC
déséquilibrés (diagnostic §3).

Or l'argent exact, en centimes entiers, est **connu au moment de la vente** : la
cascade NFC débite des entiers, Stripe encaisse des entiers, la caisse encaisse des
entiers. On le **garde**.

Le chantier fait trois choses :

1. **Séparer** la vente, ses articles et ses règlements, comme toutes les caisses
   certifiées et les ERP (Odoo : `pos.order` / `pos.order.line` / `pos.payment`).
2. **Figer** l'argent en entiers au moment de la vente, puis ne faire que des sommes.
3. **Un seul moteur** : une clôture par lieu, un rapport, un plan comptable, un FEC
   équilibré.

Et le back-office reste **simple** : une fiche « Vente » lisible par un bénévole
(les articles, puis les règlements), pas une usine à gaz.

## 2. La règle d'or (remplace « `total = amount × qty` »)

> **L'argent n'est jamais recalculé.**
> Il est écrit **une seule fois**, en centimes entiers, au moment de la vente,
> puis il est seulement **additionné**.

| Où | Ce qui est figé (entiers) |
|---|---|
| Article vendu (`LigneArticle`) | total catalogue, part offerte, net vendu (TTC), HT, TVA, prix d'achat unitaire |
| Règlement (`Reglement`) | montant |
| Vente (`Vente`) | les sommes des articles (stockées, vérifiées) |

**Les deux égalités, vraies pour TOUTE vente (sans exception) :**

```
Σ règlements                    = Σ totaux catalogue des articles
Σ règlements hors « offert »    = Σ nets vendus des articles
```

(voir §4 D8 pour ce qu'est un règlement « offert »).

**Calcul d'un article — une seule fonction dans tout le projet**
(`calculer_montants_article`, fiche A) :

```
total_catalogue = arrondi_demi_haut(prix_unitaire × quantité)
net_vendu       = total_catalogue − part_offerte
total_ht        = arrondi_demi_haut(net_vendu × 100 / (100 + taux_tva))
total_tva       = net_vendu − total_ht
```

`arrondi_demi_haut` = `Decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP)`.
Jamais `round()` (arrondi au pair), jamais `int()` (troncature), jamais `Round()` SQL
sur un produit. Un rapport fait `Sum()` sur des champs entiers, rien d'autre.

**Interdit après le chantier** : toute expression `amount * qty`, `F("amount") *
F("qty")`, `int(...amount...)` pour obtenir de l'argent. Un test de garde le vérifie
(fiche H).

## 3. Le modèle

```
Vente ─┬─ n × LigneArticle (article vendu)
       └─ n × Reglement
```

### 3.1 `Vente` (nouvelle table, `BaseBillet`)

| Champ | Sens |
|---|---|
| `uuid` | clé |
| `numero` | entier, **séquence sans trou par lieu**, posé à l'encaissement sous verrou. Vide tant que la vente n'est pas réglée |
| `nature` | `VENTE`, `AVOIR`, `RECHARGE`, `VIDAGE_CARTE`, `CORRECTION` |
| `statut` | `EN_ATTENTE`, `REGLEE`, `ANNULEE` |
| `origine` | `SaleOrigin` existant (caisse, tireuse, QR, NFC, en ligne, admin, API…) |
| `unite` | `EUR`, ou l'uuid de la monnaie de points (une seule monnaie par vente, D4 du chantier 04) |
| `point_de_vente`, `operateur`, `client` (user), `carte` | contexte, tous facultatifs |
| `vente_liee` | la vente d'origine d'un avoir ou d'une correction |
| `total_catalogue`, `total_offert`, `total_ttc` (net), `total_ht`, `total_tva` | sommes des articles, **stockées** |
| `datetime_creation`, `datetime_encaissement` | l'heure d'encaissement est posée sous verrou |
| `hmac_hash`, `previous_hmac` | empreinte chaînée (D17) |
| `idempotency_key` | anti double clic (reprend celle des lignes) |
| `metadata` | JSON libre |

### 3.2 `LigneArticle` (gardée : c'est la table « article vendu »)

Elle **n'est pas renommée** (18 producteurs, la machine à statuts des billets et
adhésions, des FK entrantes : diagnostic, second avis Fable). Elle reçoit :

| Champ ajouté | Sens |
|---|---|
| `vente` | FK vers `Vente` (nullable pendant la transition, obligatoire en fiche H) |
| `total_catalogue` | prix unitaire × quantité, arrondi une fois |
| `part_offerte` | centimes offerts sur cet article (0 par défaut) |
| `source_offert` | `OFFRIR` (bouton gérant) ou `JETONS` (monnaie cadeau des bénévoles), vide sinon |
| `total_ttc` | net vendu = catalogue − offert |
| `total_tva` | TVA de la ligne (`total_ht` existe déjà, recalculé par la même fonction) |
| `prix_achat_unitaire` | prix d'achat **figé** à la vente, dans l'unité de vente (kg, L, pièce) |
| `hors_chiffre_affaires` | **figé** à la vente : vrai pour une recharge cashless (D10), faux sinon. Le rapport ne recalcule pas cette règle depuis le produit |

Champs gardés avec leur sens : `amount` = prix unitaire TTC, `qty` = **vraie
quantité** (0,350 kg ; −2 pour un avoir), `vat` = taux, `pricesold`, `reservation`,
`membership`, `booking`, `status` (machine à statuts inchangée), `weight_quantity`.

Champs **retirés en fiche H** (ils passent sur `Vente` ou `Reglement`) :
`payment_method`, `asset`, `carte`, `wallet`, `uuid_transaction`,
`hmac_hash`, `previous_hmac`, `idempotency_key`, `point_de_vente`.
Gardés (R4) : `paiement_stripe` (lien technique vers le checkout) et `sale_origin`.

### 3.3 `Reglement` (nouvelle table, `BaseBillet`)

| Champ | Sens |
|---|---|
| `vente` | FK |
| `moyen` | `PaymentMethod` existant (CA, CC, CH, TR, LE, LG, SF, NM, FREE, Stripe…) |
| `montant` | centimes **entiers, signés**, **copiés** de la source (transaction Fedow, paiement Stripe, somme encaissée) |
| `asset` | uuid de la monnaie (cashless), vide sinon |
| `carte`, `wallet` | pour le cashless |
| `fedow_transaction_uuid` | uuid de la `fedow_core.Transaction` (pas de FK : SHARED_APPS ↔ TENANT_APPS) |
| `paiement_stripe` | FK vers `Paiement_stripe` (qui reste le détail technique Stripe) |
| `reference_externe` | id de remboursement Stripe, numéro de chèque… |
| `datetime` | |

**Un règlement par transaction Fedow, par paiement Stripe, par encaissement caisse.**
Le montant n'est jamais calculé : il est copié.

### 3.4 Ce qui ne change pas de rôle

- `Paiement_stripe` : détail technique d'un règlement Stripe (session, payment intent).
- `Commande` (`BaseBillet/models.py` ~l.1614) : le **panier** en ligne (intention
  d'achat). Elle reçoit une FK `vente` quand l'achat est encaissé.
- `CommandeSauvegarde` (commandes de table, `laboutik/models.py` ~l.1058) : reçoit une
  FK `vente` au paiement de la table.
- `Reservation`, `Membership`, `Booking` : objets **livrés**. L'article garde ses FK.

## 4. Décisions (mainteneur, 2026-09-28)

### 4.1 Modèle

| # | Décision |
|---|---|
| D1 | Séparer vente / articles / règlements pour **toutes** les ventes : caisse, tireuse, QR/NFC, en ligne, admin, API, crowds, booking. Pas de double moteur. |
| D2 | `LigneArticle` est **gardée** comme table article, non renommée. Nouvelles tables `Vente` et `Reglement` (§3). |
| D3 | Chaque vente reçoit un **numéro sans trou par lieu**, toutes natures et origines confondues, posé **à l'encaissement** sous verrou. |
| D4 | Un règlement par transaction Fedow / paiement Stripe / encaissement ; montant **copié**, jamais recalculé. |
| D5 | Règle d'or et deux égalités du §2, vérifiées par le service à l'encaissement (refus sinon, rien n'est écrit). |
| D6 | **TVA calculée par ligne**, puis additionnée par taux (pratique des caisses certifiées ; EN 16931 ne concerne pas la caisse B2C). Formule unique du §2. |

### 4.2 Classement des opérations

| # | Décision |
|---|---|
| D7 | **Monnaie locale** (LE) et **fédérée** (SF) : règlements (titres de paiement, L311-5 CMF). Un bon cadeau acheté en euros **est** de la monnaie locale. |
| D8 | **Monnaie cadeau (LG) = jetons offerts par le lieu** (bénévoles). Ce n'est pas de l'argent : c'est de l'**offert**, comme le bouton OFFRIR. Sur l'article : `part_offerte` (+ `source_offert`), **hors chiffre d'affaires, hors TVA** (petits cadeaux, art. 257 CGI). Pour garder la trace (carte, transaction Fedow), un **règlement « offert »** est écrit aussi (moyen `LG` pour les jetons, `FREE` pour OFFRIR) : il compte dans la 1ʳᵉ égalité, pas dans la 2ᵉ, ni dans les encaissements. ⚠ *Précision de rédaction, à confirmer en relecture* : le mainteneur a validé « LG = offert, part offerte sur l'article » ; le règlement « offert » ne sert qu'à la trace. |
| D9 | **Points** (NM) : la vente a `unite` = la monnaie de points ; articles en centièmes de points, TVA 0 ; règlement NM. Hors chiffre d'affaires (décisions D1-D17 du chantier 04 inchangées). |
| D10 | **Recharge cashless** : vente `RECHARGE`, un article « recharge » **hors chiffre d'affaires, TVA 0** (dette envers le porteur, compte 4191), réglé en espèces / CB / chèque. Le chiffre d'affaires naît à la **consommation**. Plus de double comptage. Recharge cadeau : même article, **entièrement offert** (`part_offerte` = total, `source_offert = OFFRIR`, net 0), règlement `FREE` (« cadeau émis ») — sinon la 2ᵉ égalité serait rompue. |
| D11 | **Consigne** : vente **classique, dans le chiffre d'affaires**. **Retour de consigne = remboursement** : vente `AVOIR` (sans vente liée : le gobelet est anonyme), article consigne en quantité négative, règlement négatif (espèces ou carte). Le Z affiche une ligne « Retours consigne ». |
| D12 | **Vider une carte** : vente `VIDAGE_CARTE` **sans article** ; règlements qui s'annulent (+ jetons repris par monnaie, − espèces rendues). Remplace l'article « Refund » actuel. |
| D13 | **Avoir / remboursement** : nouvelle vente `AVOIR` liée à la vente d'origine ; **quantité négative, prix unitaire positif** (prix catalogue) ; règlements négatifs au montant **réellement** remboursé (Stripe : montant du refund). |
| D14 | **Correction de moyen de paiement** : nouvelle vente `CORRECTION` liée, sans article, règlements `−ancien moyen` / `+nouveau moyen`. On ne modifie **plus jamais** une vente encaissée. |
| D15 | **Poids / volume** : `qty` = quantité réelle (0,350 kg ; 0,50 L), `amount` = prix au kg / au litre, total figé une fois au centime. Vaut pour la caisse et la tireuse. |
| D16 | **Paiement en ligne** : vente `EN_ATTENTE` dès le checkout ; numéro et empreinte posés **à l'encaissement** (webhook) ; paiement expiré → `ANNULEE`, jamais numérotée. « Un ticket n'existe qu'une fois réglé. » |
| D17 | **Adhésion payée avec plusieurs moyens** : un seul article adhésion, N règlements. |

### 4.3 Chaînage, clôture, comptabilité

| # | Décision |
|---|---|
| D18 | **On chaîne la Vente**, pas les lignes : HMAC-SHA256 d'un JSON canonique versionné (vente + articles + règlements), **une seule chaîne par lieu**, ordonnée par `numero`. Clé : `LaboutikConfiguration.hmac_key` (inchangée). `verifier_chaine` : aucune exception tolérée (les corrections sont de nouvelles ventes). |
| D19 | **Une seule clôture par lieu**, toutes origines. Niveaux **jour, semaine, mois, année gardés** (la semaine reste une clôture officielle). Le Z est lui aussi chaîné. Tout ce qui est imprimé est **stocké** ; seul le rapport X (temps réel) recalcule. |
| D20 | Le Z montre **deux totaux distincts** : le **chiffre d'affaires** (articles, par taux, par catégorie, par origine, par point de vente) et les **règlements** (par moyen et par monnaie : argent, cashless, hors argent). |
| D21 | **Marge brute** (pas « bénéfice ») = CA HT − Σ (quantité servie × prix d'achat figé). La quantité servie compte tout : vendu, offert, points ; retours de consigne en négatif. |
| D22 | **Un seul plan comptable** : base = celui de la caisse (le plus complet : nature, taux de TVA), rangé dans « Ventes & comptabilité », rendu lisible. Enrichi : un compte par taux de TVA (existe), un compte de trésorerie **par moyen et par monnaie**, un **journal FEC par point de vente** (et « WEB », « TIREUSE »…). Les virements entre lieux restent au TODO `COMPTABILITE-inter-tenants.md`. |
| D23 | **Un seul FEC**, **équilibré par construction** (débits = crédits vérifiés, refus d'export sinon). |
| D24 | Envoi vers **l'ancien serveur LaBoutik** (`send_sale_to_laboutik`) : **gardé**, adapté au minimum (il lit le moyen dans la vente). Sa suppression est un autre chantier. |
| D25 | Menu : les deux rapports actuels rangés sous « Ventes & comptabilité » dès la fiche 0. |

### 4.4 Choix de rédaction (à valider en relecture)

| # | Choix | Raison |
|---|---|---|
| R1 | `Vente` et `Reglement` vivent dans **`BaseBillet`**, à côté de `LigneArticle` et `Paiement_stripe`. Le service dans `BaseBillet/services_vente.py` (comme `services_panier.py`). | Pas de nouvelle dépendance circulaire entre apps ; une seule app de migrations pour les trois tables. |
| R2 | La clôture et le rapport vivent dans **`comptabilite/`**. Le modèle survivant est `comptabilite.ClotureCaisse` (séquence globale, perpétuel repris de la dernière J), enrichi des champs utiles de `laboutik.ClotureCaisse`. Le **plan comptable reste dans les tables `laboutik`** (déjà reliées aux catégories et au FEC caisse), seulement affiché dans le menu « Ventes & comptabilité » (fiche E). | L'app porte déjà le nom du menu ; la séquence globale est celle que la loi attend (une numérotation continue) ; déplacer des tables entre apps coûte une migration sans gain. |
| R3 | Transition en **« parts entières »** (§5) : pendant les fiches B à G, une ligne reste coupée par moyen de paiement, mais **chaque part porte ses montants entiers**. La fiche H fusionne en une ligne par article. | Les anciens lecteurs continuent de marcher pendant que les nouveaux lisent les entiers : aucune fiche ne casse les suites. |
| R4 | `LigneArticle` **garde** `paiement_stripe` (lien technique vers le checkout, utilisé par la machine à statuts Stripe) et `sale_origin` (filtres et déclencheurs) : ce ne sont pas des montants. Retirés en H : `payment_method`, `asset`, `carte`, `wallet`, `uuid_transaction`, `hmac_*`, `idempotency_key`, `point_de_vente`. | Retirer `paiement_stripe` réécrirait tout le flux Stripe pour zéro gain comptable. |

## 5. La transition, en clair

On ne casse rien d'un coup. Trois temps :

1. **Écrire deux fois** (fiches B, C, D) : chaque producteur continue d'écrire ses
   lignes comme aujourd'hui (les anciens rapports marchent), **et** écrit la `Vente`,
   ses `Reglement`, et les nouveaux champs entiers sur ses lignes.

   Pendant ce temps, une ligne payée avec deux moyens reste coupée en deux « parts »,
   mais **chaque part porte l'argent réel de sa part**, copié du tuple de la cascade :

   | Part | `amount` | `qty` | `total_catalogue` | `total_ttc` | `total_ht` | `total_tva` |
   |---|---|---|---|---|---|---|
   | LE | 350 | 1,428571 | **500** | **500** | 417 | 83 |
   | CB | 350 | 1,571429 | **550** | **550** | 458 | 92 |
   | Vente | | | 1050 | 1050 | 875 | 175 |

   Règlements : LE 500, CB 550. Les deux égalités tiennent au centime.

2. **Lire le nouveau** (fiches E, F, G) : plan comptable, rapport unique, puis tous les
   lecteurs basculent sur les champs entiers et les règlements.

3. **Retirer l'ancien** (fiche H) : une ligne par article (plus de parts ni de
   quantités partielles), champs de règlement retirés de `LigneArticle`, deuxième
   clôture, deuxième plan comptable, deuxième FEC, `CorrectionPaiement`, HMAC par ligne.

## 6. Les fiches, dans l'ordre de livraison

| Fiche | Sujet | Effort | Dépend de |
|---|---|---|---|
| [0](CHANTIER-05-0-menu-rapports.md) | Ranger les deux rapports sous « Ventes & comptabilité » | 0,25 j | — |
| [A](CHANTIER-05-A-vente-reglement.md) | Tables `Vente`, `Reglement`, champs entiers de l'article ; service de vente (égalités, numéro sous verrou, empreinte) ; fabrique de test | 1,5 j | — |
| [B](CHANTIER-05-B-caisse.md) | La caisse écrit aussi le nouveau modèle (cascade, complément, 2ᵉ carte, recharges, consigne, vider carte, offert et jetons, points, adhésion, commandes de table, poids/mesure, correction de moyen) | 3 j | A |
| [C](CHANTIER-05-C-tireuse-qr.md) | Tireuse et paiement QR/NFC écrivent aussi le nouveau modèle | 1 j | A, 04-F-1 |
| [D](CHANTIER-05-D-en-ligne-avoirs.md) | En ligne, admin, API, crowds, booking : vente en attente puis encaissée ; avoirs et remboursements = ventes `AVOIR` | 2,5 j | A |
| [E](CHANTIER-05-E-plan-comptable.md) | Plan comptable unique : comptes par moyen et par monnaie, journal par point de vente | 1,5 j | — |
| [F](CHANTIER-05-F-rapport-unique.md) | Moteur de rapport unique, clôture unique J/H/M/A, Z chaîné, marge brute, FEC équilibré ; test de comparaison avec les anciens rapports | 3 j | B, C, D, E |
| [G](CHANTIER-05-G-lecteurs.md) | Bascule des lecteurs : archive LNE, exports, tickets imprimés, fiche « Vente » dans l'admin, totaux client, vérification d'intégrité, API, ancien LaBoutik | 2,5 j | F |
| [H](CHANTIER-05-H-retrait.md) | Une ligne par article ; retrait de l'ancien modèle et des doublons ; test de garde « pas de `amount × qty` » | 3 j | G |

**Total estimé : 18 à 19 jours.** B, C et D touchent des fichiers différents mais
tous passent par le service de la fiche A : pas en parallèle tant que A n'est pas
stable. B et C touchent la cascade et `controlvanne/billing.py` que le chantier 04
(E, F-1) a modifiés : vérifier l'état du working tree avant de commencer.

## 7. Relation avec le chantier 04

| Fiche 04 | Sort |
|---|---|
| A (paiement réparti QR/tireuse), B (HT × qty) | livrées, **remplacées** par les champs entiers ; leurs tests restent verts jusqu'à la fiche H, qui les réécrit |
| C (ticket imprimé regroupé), D (hors argent, OFFRIR), E (vente en points) | livrées ; leur **sémantique** passe telle quelle dans `Reglement.moyen` et `part_offerte` |
| **F-1 (anti-rejeu QR)** | **gardée** : à livrer **avant 05-C** (mêmes fonctions QR/NFC) |
| **F-2, F-3 (chaînage par ligne, verrou, archive TIREUSE)** | **arrêtées** : remplacées par le chaînage de la Vente (D18, fiche A) et l'archive de la fiche G |

## 8. Méthode de travail (chaque fiche)

Reprise du chantier 04 (§5 du tronc 04), inchangée :

1. **Le test d'abord, vu rouge** sur le code actuel ; sortie d'échec notée dans le
   CHANGELOG de la fiche.
2. Le correctif, puis le test passe.
3. **Mutations** du code de production pour chaque assertion structurante (script
   `muter.py` : remplacer, attendre un 200 du serveur, lancer, restaurer dans un
   `finally` par Edit inverse — jamais git —, vérifier `sha256sum` avant/après).
   Compter seulement les lignes `FAILED ` / `ERROR tests/`.
4. Aucun `pytest.skip`, aucun `if ... count() > 0`, aucune assertion toujours vraie.
   Un test d'argent compare des **entiers exacts** (pas « à un centime près »).
5. Tests par `make`, dans le conteneur, **jamais deux pytest en parallèle**
   (`docker exec lespass_django pgrep -af pytest`). Base partagée : `django_db`.
   Un test qui lit un **rapport ou une chaîne** (tout le lieu) tourne dans un **schéma
   dédié** (`FastTenantTestCase`, D28 du chantier 04). Après une migration, migrer ou
   supprimer les schémas `test_*` (skill `tibillet-test`).
6. Pas de `ruff format` ni de `ruff check --fix` sur un fichier existant.
7. Commentaires FALC bilingues FR/EN, au présent. `_()` en français. Pas de
   `makemessages` / `compilemessages` : lister les nouvelles chaînes dans le CHANGELOG.
8. Un fichier `CHANGELOG/2026-MM-JJ-montants-entiers-<fiche>.md` par fiche, avec le
   tableau des mutations jouées.
9. Suite complète (`make test`, et `make e2e` quand la caisse ou l'admin changent)
   en fin de fiche. Départ : `make test` 2070 passed, `make e2e` 116 passed.

**Test transversal, présent dès la fiche A et enrichi à chaque fiche** :
`tests/pytest/test_montants_entiers_egalites.py` — pour chaque vente encaissée par
le scénario de la fiche, les deux égalités du §2 tiennent, et
`Vente.total_* = Σ articles`.

## 9. Hors de ce chantier

| Sujet | Où |
|---|---|
| Virements bancaires entre lieux, comptes 165/467 par émetteur | `TODO/COMPTABILITE-inter-tenants.md` |
| Suppression de l'envoi vers l'ancien LaBoutik et du webhook `Membership_fwh` | chantier futur |
| Table des moyens de paiement modifiable en base (façon `pos.payment.method`) | pas demandé ; le mapping par moyen et par monnaie (D22) suffit |
| Tireuse, solde insuffisant (D27 du chantier 04) | inchangé |
| API v2, rechargement de points en unité brute (D16 du chantier 04) | fiche à part, avant production |
| `crowds` vue `allocate` (cagnotte + recharges cashless) | inchangé |

## 10. Vérifications communes

```bash
docker exec lespass_django pgrep -af pytest          # rien ne doit tourner
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
make test ARGS="tests/pytest/<fichier_de_la_fiche>.py"
make test                                             # suite complète en fin de fiche
```

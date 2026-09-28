# Chantier 05 — Montants entiers : Vente, articles, règlements (tronc commun)

> **Statut** : 📋 SPEC RÉDIGÉE (2026-09-28) — relue par Fable et Opus, corrigée, décisions D26-D33 prises le même jour
> **Branche** : `main-fedow-import`
> **Contexte** : environnement de **dev uniquement**. Aucune donnée historique à
> rattraper, aucune ligne existante à migrer. Le format HMAC peut être redéfini.
> **Diagnostic** : [`CHANTIER-05-diagnostic.md`](CHANTIER-05-diagnostic.md)
> **Machine à états** : [`CHANTIER-05-machine-a-etats.md`](CHANTIER-05-machine-a-etats.md) (statuts, transitions, parcours P1-P17, trous T1-T22, tests de caractérisation)
> **Suivi** : [`CHANTIER-05-SUIVI.md`](CHANTIER-05-SUIVI.md)
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
| Article vendu (`LigneArticle`) | total catalogue, part offerte, net vendu (TTC), HT, TVA, coût d'achat |
| Règlement (`Reglement`) | montant |
| Vente (`Vente`) | les sommes des articles (stockées, vérifiées) |

**Les deux égalités, vraies pour TOUTE vente (sans exception) :**

```
Σ règlements                    = Σ totaux catalogue des articles
Σ règlements hors « offert »    = Σ nets vendus des articles
```

(voir §4 D8 pour ce qu'est un règlement « offert »). **Aucun règlement de montant 0
n'est jamais écrit** : une vente gratuite n'a pas de règlement (0 = 0).

**Article « offert » à montant non nul** (moyen historique `FREE` avec un prix > 0 :
billet offert dans l'admin, adhésion gratuite API, réservation gratuite API à tarif non
nul…) : toujours `part_offerte = total_catalogue`, `source_offert = OFFRIR`, et un
règlement `FREE` du même montant. La règle est posée **une fois**, dans le service
(fiche A), pas producteur par producteur.

**Calcul d'un article — une seule fonction dans tout le projet**
(`calculer_montants_article`, fiche A) :

```
total_catalogue = arrondi_demi_haut(prix_unitaire × quantité)
net_vendu       = total_catalogue − part_offerte
total_ht        = arrondi_demi_haut(net_vendu × 100 / (100 + taux_tva))
total_tva       = net_vendu − total_ht
cout_achat      = arrondi_demi_haut(quantité_réelle × prix_achat)   (vide si prix_achat = 0 : inconnu, D21)
```

`quantité_réelle` = la quantité servie dans l'unité du prix d'achat (pièces, kg, L).
Pendant la transition (fiches B à G), `qty` d'une ligne n'est pas toujours cette
quantité (vente au poids : `qty = 1` ; part de cascade ou de tirage : fraction) : le
producteur la passe à part (`quantite_pour_cout`, fiche A).

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
| `source_offert` | `OFFRIR` (bouton gérant), `JETONS` (monnaie cadeau des bénévoles) ou `CADEAU` (recharge cadeau émise), vide sinon |
| `total_ttc` | net vendu = catalogue − offert |
| `total_tva` | TVA de la ligne (`total_ht` existe déjà, recalculé par la même fonction) |
| `prix_achat_unitaire` | prix d'achat **figé** à la vente, dans l'unité de vente (kg, L, pièce) ; 0 = inconnu |
| `cout_achat` | coût d'achat **figé** en centimes entiers (quantité × prix d'achat, arrondi une fois) ; vide si le prix d'achat est inconnu. La marge brute ne fait que `Sum("cout_achat")` |
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
  Il reçoit `montant_encaisse` (centimes, renvoyé par Stripe) : c'est la source du
  montant du règlement (fiche D). Il reçoit aussi une FK **`vente`** (nullable) : la
  **vente d'origine**, posée à l'ouverture du checkout. **Un paiement Stripe = une vente
  d'origine, plus ses avoirs éventuels** (R5) : les lignes d'avoir Stripe gardent le
  même `paiement_stripe` (`PaiementStripe/utils.py` ~l.88), mais appartiennent à des
  ventes `AVOIR` ; on ne retrouve donc jamais la vente d'origine par les lignes.
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
| D8 | **Monnaie cadeau (LG) = jetons offerts par le lieu** (bénévoles). Ce n'est pas de l'argent : c'est de l'**offert**, comme le bouton OFFRIR. Sur l'article : `part_offerte` (+ `source_offert`), **hors chiffre d'affaires, hors TVA** (petits cadeaux, art. 257 CGI). Pour garder la trace (carte, transaction Fedow), un **règlement « offert »** est écrit aussi (moyen `LG` pour les jetons, `FREE` — code `NA` en base — pour OFFRIR) : il compte dans la 1ʳᵉ égalité, pas dans la 2ᵉ, ni dans les encaissements. *Règlement « offert » de trace (« un débit = un règlement ») : en attente de validation du mainteneur (SUIVI §5).* |
| D9 | **Points** (NM) : la vente a `unite` = la monnaie de points ; articles en centièmes de points, TVA 0 ; règlement NM. Hors chiffre d'affaires (décisions D1-D17 du chantier 04 inchangées). |
| D10 | **Recharge cashless** : vente `RECHARGE`, un article « recharge » **hors chiffre d'affaires, TVA 0** (dette envers le porteur, compte 4191), réglé en espèces / CB / chèque. Le chiffre d'affaires naît à la **consommation**. Plus de double comptage. Recharge cadeau : même article, **entièrement offert** (`part_offerte` = total, `source_offert = CADEAU`, net 0), règlement `FREE` (« cadeau émis ») — sinon la 2ᵉ égalité serait rompue. La section « Offerts » du Z ne lit que les articles du chiffre d'affaires : la recharge cadeau et sa consommation en jetons ne sont pas comptées deux fois. |
| D11 | **Consigne** : vente **classique, dans le chiffre d'affaires**. **Retour de consigne = remboursement** : vente `AVOIR` (sans vente liée : le gobelet est anonyme), article consigne en quantité négative, règlement négatif (espèces ou carte). Le Z affiche une ligne « Retours consigne ». Le produit « Retour de consigne » (`methode_caisse = CR`) reçoit un lien **`consigne_remboursee`** vers le produit consigne vendu : le retour reprend **son prix et son taux de TVA**, il annule exactement la vente, TVA comprise (les gobelets gardés restent taxés : TVA payée tôt, total juste — à faire confirmer par le comptable d'un lieu). |
| D12 | **Vider une carte** : vente `VIDAGE_CARTE` **sans article** ; règlements qui s'annulent (un règlement par transaction de remboursement de jetons, − espèces rendues ; un jeton cadeau brûlé sans argent rendu n'a pas de règlement). Remplace l'article « Refund » actuel. |
| D13 | **Avoir / remboursement** : nouvelle vente `AVOIR` liée à la vente d'origine ; **quantité négative, prix unitaire positif** (prix catalogue) ; règlements négatifs au montant **réellement** remboursé (Stripe : montant du refund). |
| D14 | **Correction de moyen de paiement** : nouvelle vente `CORRECTION` liée, sans article, règlements `−ancien moyen` / `+nouveau moyen`. On ne modifie **plus jamais** une vente encaissée. |
| D15 | **Poids / volume** : `qty` = quantité réelle (0,350 kg ; 0,50 L), `amount` = prix au kg / au litre, total figé une fois au centime. Vaut pour la caisse et la tireuse. **Appliqué en fiche H** (en B et C, cette forme changerait les anciens rapports : R6). |
| D16 | **Paiement en ligne** : vente `EN_ATTENTE` dès le checkout ; numéro et empreinte posés **à l'encaissement** (webhook) ; paiement expiré → `ANNULEE`, sans numéro ; un paiement arrivé après l'expiration la **rouvre** et l'encaisse (fiche D). `EN_ATTENTE` = paiement pas encore constaté, **abandon compris** (sans numéro, sans effet comptable) ; `ANNULEE` seulement quand Stripe l'a dit. « Un ticket n'existe qu'une fois réglé. » |
| D17 | **Adhésion payée avec plusieurs moyens** : un seul article adhésion, N règlements. |

### 4.3 Chaînage, clôture, comptabilité

| # | Décision |
|---|---|
| D18 | **On chaîne la Vente**, pas les lignes : HMAC-SHA256 d'un JSON canonique versionné (vente + articles + règlements), **une seule chaîne par lieu**, ordonnée par `numero`. Clé : `LaboutikConfiguration.hmac_key` (inchangée). `verifier_chaine` : aucune exception tolérée (les corrections sont de nouvelles ventes). |
| D19 | **Une seule clôture par lieu**, toutes origines. Niveaux **jour, semaine, mois, année gardés** (la semaine reste une clôture officielle). Le Z est lui aussi chaîné. Tout ce qui est imprimé est **stocké** ; seul le rapport X (temps réel) recalcule. |
| D20 | Le Z montre **deux totaux distincts** : le **chiffre d'affaires** (articles, par taux, par catégorie, par origine, par point de vente) et les **règlements** (par moyen et par monnaie : argent, cashless, hors argent). |
| D21 | **Marge brute** (pas « bénéfice ») = CA HT − Σ `cout_achat` (figé par ligne). Tout ce qui est servi compte : vendu, offert, points ; retours de consigne en négatif. **Prix d'achat 0 = inconnu** (champ inchangé, pas de migration) : la ligne n'a pas de coût et la marge est signalée « incomplète ». Le prix d'achat est dans l'**unité de vente** (au kilo, au litre, à la pièce) ; l'admin affiche l'unité à côté du champ. |
| D22 | **Un seul plan comptable** : base = celui de la caisse (le plus complet : nature, taux de TVA), rangé dans « Ventes & comptabilité », rendu lisible. Enrichi : un compte par taux de TVA (existe), un compte de trésorerie **par moyen et par monnaie**, un **journal FEC par point de vente** (et « WEB », « TIREUSE »…). Les virements entre lieux restent au TODO `COMPTABILITE-inter-tenants.md`. |
| D23 | **Un seul FEC**, **équilibré par construction** (débits = crédits vérifiés, refus d'export sinon). |
| D24 | Envoi vers **l'ancien serveur LaBoutik** (`send_sale_to_laboutik`) : **gardé**, adapté au minimum (il lit le moyen dans la vente). Sa suppression est un autre chantier. |
| D25 | Menu : les deux rapports actuels rangés sous « Ventes & comptabilité » dès la fiche 0. |
| D26 | **Stripe encaisse un montant différent des articles** (prorata, remise, arrondi) : la vente est **encaissée quand même, au montant Stripe**. L'écart devient automatiquement un article « **Écart d'encaissement** » (TVA 0, hors chiffre d'affaires, compte 758 si reçu en plus, 658 si reçu en moins) + alerte (Sentry et badge dans l'admin). |
| D27 | **Avoir fait dans l'admin** : achat **hors Stripe** → l'admin choisit **« Remboursé par : espèces / CB / chèque / virement »**, pré-rempli avec le moyen d'origine. Achat **payé par Stripe** → **comportement actuel gardé** : aucun appel à Stripe ; règlement négatif au moyen Stripe d'origine, et un message prévient l'admin de rembourser depuis son tableau de bord Stripe. Même règle pour l'annulation d'adhésion. |
| D28 | **La journée du Z** = depuis le Z précédent jusqu'au moment de la clôture : bouton de la caisse en fin de service, et **Z automatique à l'heure de fermeture du lieu + 2 h** si personne ne l'a fait (nouveau champ `Configuration.heure_de_fermeture`, défaut 02:00 → Z à 4 h, heure locale du lieu). Semaine, mois et année restent **calendaires**, calculés directement sur les ventes. |
| D29 | Le Z automatique **n'annule pas** les commandes de table ouvertes et ne libère pas les tables ; seul le bouton de clôture le fait (comme aujourd'hui). |
| D30 | **Annulation d'adhésion** : un seul avoir, pour le **dernier paiement** (la période en cours), pas pour les renouvellements passés. |
| D31 | **Annulation par l'utilisateur** d'un achat payé **hors Stripe** : aucun avoir, aucun remboursement (l'argent reste acquis ; si le lieu rembourse, l'admin fait un avoir). |
| D32 | **Billet offert dans l'admin** : écrit comme un offert de la caisse (prix catalogue, part offerte totale, `OFFRIR`, vente d'origine `ADMIN`, règlement `FREE`). |
| D33 | Bug actuel T13 (le rejeu `PAID → PAID` repasse les avoirs en `PAID`) : **corrigé dans un autre chantier**, figé par un test de caractérisation ici. |

### 4.4 Choix de rédaction (en attente de validation du mainteneur, SUIVI §5)

| # | Choix | Raison |
|---|---|---|
| R1 | `Vente` et `Reglement` vivent dans **`BaseBillet`**, à côté de `LigneArticle` et `Paiement_stripe`. Le service dans `BaseBillet/services_vente.py` (comme `services_panier.py`). | Une seule app de migrations pour les trois tables. |
| R2 | La clôture et le rapport vivent dans **`comptabilite/`**. Le modèle survivant est `comptabilite.ClotureCaisse` (séquence globale, perpétuel repris de la dernière J), enrichi des champs utiles de `laboutik.ClotureCaisse`. Le **plan comptable reste dans les tables `laboutik`** (déjà reliées aux catégories et au FEC caisse), seulement affiché dans le menu « Ventes & comptabilité » (fiche E). | L'app porte déjà le nom du menu ; la séquence globale est celle que la loi attend (une numérotation continue) ; déplacer des tables entre apps coûte une migration sans gain. |
| R3 | Transition en **« parts entières »** (§5) : pendant les fiches B à G, une ligne reste coupée par moyen de paiement, mais **chaque part porte ses montants entiers**. La fiche H fusionne en une ligne par article. | Les anciens lecteurs continuent de marcher pendant que les nouveaux lisent les entiers : aucune fiche ne casse les suites. |
| R4 | `LigneArticle` **garde** `paiement_stripe` (lien technique vers le checkout, utilisé par la machine à statuts Stripe) et `sale_origin` (filtres et déclencheurs) : ce ne sont pas des montants. Retirés en H : `payment_method`, `asset`, `carte`, `wallet`, `uuid_transaction`, `hmac_*`, `idempotency_key`, `point_de_vente`. | Retirer `paiement_stripe` réécrirait tout le flux Stripe pour zéro gain comptable. |
| R5 | **Un paiement Stripe = une vente d'origine, plus ses avoirs éventuels.** La vente d'origine est ouverte par l'orchestrateur (`CommandeService`, API) et transmise aux producteurs (billets, booking, adhésions d'un même panier). Elle est rangée dans `Paiement_stripe.vente` (FK, fiche A). Les remboursements sont des ventes `AVOIR` liées. | Un panier réunit plusieurs producteurs sous un seul paiement : une vente par producteur casserait l'égalité avec le montant Stripe. |
| R6 | La nouvelle forme `qty` / `amount` du poids et de la tireuse (D15) est appliquée en **fiche H**, pas en B / C. | En B / C elle change les anciens rapports (`Round(Sum)` sur deux pesées, `int(qty)` du coût, `floatformat:0`, total de tirage réduit). |

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

   ⚠ Le HT d'une part peut différer de ±1 centime du HT de l'article entier
   (3 parts de 33 à 20 % : 3 × 28 = 84, alors que HT(99) = 83). Entre les fiches B et
   H, la TVA du Z peut donc bouger de ±1 centime par rapport à la valeur finale. Les
   tests de transition n'assertent que les **totaux de la Vente** et les égalités.

2. **Lire le nouveau** (fiches E, F, G) : plan comptable, rapport unique, puis tous les
   lecteurs basculent sur les champs entiers et les règlements.

3. **Retirer l'ancien** (fiche H) : une ligne par article (plus de parts ni de
   quantités partielles), forme poids / tireuse de D15, champs de règlement retirés de `LigneArticle`, deuxième
   clôture, deuxième FEC, `CorrectionPaiement`, HMAC par ligne. (Le deuxième plan
   comptable, lui, est retiré dès la fiche E.)

## 6. Les fiches, dans l'ordre de livraison

| Fiche | Sujet | Effort | Dépend de |
|---|---|---|---|
| [0](CHANTIER-05-0-menu-rapports.md) | Ranger les deux rapports sous « Ventes & comptabilité » | 0,25 j | — |
| [A](CHANTIER-05-A-vente-reglement.md) | Tables `Vente`, `Reglement`, champs entiers de l'article, `Paiement_stripe.vente` ; service de vente (égalités, numéro sous verrou, empreinte) ; fabrique de test | 2,25 j | — |
| [A′](CHANTIER-05-A2-caracterisation.md) | Tests de caractérisation : figer la logique métier actuelle (statuts, e-mails, billets, adhésions, appels Stripe / Fedow, envois LaBoutik) avant d'y toucher | 1,5 j | — (avant B) |
| [B](CHANTIER-05-B-caisse.md) | La caisse écrit aussi le nouveau modèle (cascade, complément, 2ᵉ carte, recharges, consigne, vider carte, offert et jetons, points, adhésion, commandes de table, correction de moyen, consigne reliée) | 4 j | A, A′ |
| [C](CHANTIER-05-C-tireuse-qr.md) | Tireuse et paiement QR/NFC écrivent aussi le nouveau modèle ; QR/NFC restructuré « réseau d'abord, puis une transaction » (repris de 04-F §5.3) | 2 j | A, 04-F-1 |
| [D](CHANTIER-05-D-en-ligne-avoirs.md) | En ligne, admin, API, crowds, booking : une vente d'origine par paiement Stripe, en attente puis encaissée au montant Stripe (écart d'encaissement) ; avoirs et remboursements = ventes `AVOIR` | 4,5 j | A |
| [E](CHANTIER-05-E-plan-comptable.md) | Plan comptable unique : comptes par catégorie **ou** par type de produit, par moyen et par monnaie, journal par point de vente | 2 j | — |
| [F](CHANTIER-05-F-rapport-unique.md) | Moteur de rapport unique, clôture unique J/H/M/A, Z chaîné, marge brute, FEC équilibré ; test de comparaison avec les anciens rapports ; tests existants réécrits | 4 j | B, C, D, E |
| [G](CHANTIER-05-G-lecteurs.md) | Bascule des lecteurs : archive LNE, exports, tickets imprimés, fiche « Vente » dans l'admin, totaux client, vérification d'intégrité, garde « correction après clôture », FK de clôture (stock, impressions), API, ancien LaBoutik | 5 j | F |
| [H](CHANTIER-05-H-retrait.md) | Une ligne par article, forme poids / tireuse (D15), avoir sur un article ; retrait de l'ancien modèle et des doublons ; test de garde « pas de `amount × qty` » | 6 j | G |

**Total estimé : 32 à 35 jours** (somme des fiches : 31,5 j). B, C et D touchent des fichiers différents mais
tous passent par le service de la fiche A : pas en parallèle tant que A n'est pas
stable. B et C touchent la cascade et `controlvanne/billing.py` que le chantier 04
(E, F-1) a modifiés : vérifier l'état du working tree avant de commencer.

## 7. Relation avec le chantier 04

| Fiche 04 | Sort |
|---|---|
| A (paiement réparti QR/tireuse), B (HT × qty) | livrées, **remplacées** par les champs entiers ; leurs tests restent verts jusqu'à la fiche H, qui les réécrit |
| C (ticket imprimé regroupé), D (hors argent, OFFRIR), E (vente en points) | livrées ; leur **sémantique** passe telle quelle dans `Reglement.moyen` et `part_offerte` |
| **F-1 (anti-rejeu QR)** | **gardée** : à livrer **avant 05-C** (mêmes fonctions QR/NFC). Elle ne pose que la réservation `CREATED → UNPAID` ; la restructuration « réseau d'abord, puis `atomic`, puis `on_commit` » (04-F §5.3) est **reprise dans 05-C** |
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
   (`docker exec lespass_django pgrep -af pytest`). Base partagée : la marque
   `django_db` **annule** la transaction à la fin du test (PIEGES 13.1) ; sous la marque,
   `transaction.on_commit` ne part pas : utiliser `django_capture_on_commit_callbacks`
   quand le test en dépend. Un test sans la marque, lui, laisse ses ventes en base
   (PIEGES 9.45). Un test qui lit un **rapport, une clôture, la numérotation ou la
   chaîne**, ou qui **altère** une vente, tourne dans un **schéma dédié**
   (`FastTenantTestCase`, D28 du chantier 04) ; y créer à la main le singleton
   `LaboutikConfiguration` (PIEGES 9.86), sinon la clé HMAC échoue. Après une
   migration, migrer ou supprimer les schémas `test_*` (skill `tibillet-test`).
6. Pas de `ruff format` ni de `ruff check --fix` sur un fichier existant.
7. Commentaires FALC bilingues FR/EN, au présent. `_()` en français. Pas de
   `makemessages` / `compilemessages` : lister les nouvelles chaînes dans le CHANGELOG.
8. Un fichier `CHANGELOG/2026-MM-JJ-montants-entiers-<fiche>.md` par fiche, avec le
   tableau des mutations jouées.
9. Suite complète (`make test`, et `make e2e` quand la caisse ou l'admin changent)
   en fin de fiche. Départ : `make test` 2082 passed, `make e2e` 116 passed.
10. Chaque fiche liste ses **tests existants à réécrire** : une fiche qui change un
    lecteur ou retire un module réécrit ses tests dans la même fiche (`make test` vert
    en fin de fiche).

**Tests de caractérisation (fiche A′)** : verts sur le code actuel, ils doivent rester verts **sans modification** à chaque fiche (sauf la liste fermée de A′ §4). Un test de caractérisation qui tombe = une logique métier changée sans le vouloir : arrêt et question au mainteneur.

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
| `crowds` vue `allocate` (cagnotte + recharges cashless) | logique inchangée ; seul son calcul de montant passe sur `total_ttc` (fiche G) |
| Recharges par la **borne** (`kiosk`, TPE Stripe, crédit par Fedow distant) : aucune ligne de vente locale aujourd'hui | hors chantier ; conséquence : ces recharges n'apparaissent ni dans le Z ni dans le FEC du lieu (à traiter avec le TODO inter-tenants) |
| Recrédit d'une carte cashless depuis un avoir admin (D27) | chantier futur |
| Crowds « marquer payée » (`admin_paid`) : n'écrit ni ligne ni vente (argent reçu ailleurs, non enregistré) | hors chantier, comportement inchangé (T17) |
| Bug actuel T13 : un rejeu `PAID → PAID` repasse les lignes d'avoir en `PAID` (`BaseBillet/signals.py` ~l.42) | hors chantier ; figé par un test de caractérisation (A′), signalé au mainteneur |

## 10. Vérifications communes

```bash
docker exec lespass_django pgrep -af pytest          # rien ne doit tourner
docker exec lespass_django poetry run python /DjangoFiles/manage.py check
docker exec lespass_django poetry run python /DjangoFiles/manage.py makemigrations --check --dry-run
make test ARGS="tests/pytest/<fichier_de_la_fiche>.py"
make test                                             # suite complète en fin de fiche
```

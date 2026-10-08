# Chantier 05-R — Reprise des ventes existantes, la nuit de la mise en production

> **Statut** : 🔎 PRÊTE À RELIRE (Fable) — réécrite le 2026-10-06.
> Sources intégrées : décisions **Q-R1 à Q-R19** (`CHANTIER-05-SUIVI.md` §5) ; constats
> de la relecture Fable de cohérence (`CHANTIER-05-briefs/05-R-relecture-fable-2026-10-04.md` :
> B-1 à B-3, I-1 à I-12, cas non couverts, ordre de la nuit) ; conséquences de H-1 et du
> verrou moteur (ancien §11, fondu dans les sections, trace au §16).
> Tronc : [`CHANTIER-05-montants-entiers.md`](CHANTIER-05-montants-entiers.md) — D1, D8 bis,
> D13, D16, R5.
> Copie de la production : [`CHANTIER-05-R-copie-prod.md`](CHANTIER-05-R-copie-prod.md)
> (LA procédure ; §3.5 = cases du moteur de monnaie et du réseau CLAF, qui reprennent
> `FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md` §8).
> Ordre du chantier (mainteneur) : H-1 faite → **R** → mise en production → H-4, H-2, H-3.
> **Migrations : non.** La reprise est une commande. Elle n'ajoute aucun champ.
>
> **Règle absolue sur la copie de la production** : aucune lecture de donnée
> personnelle. Comptages agrégés seulement (`COUNT`, `SUM`, `GROUP BY` sur statuts,
> moyens, origines, dates, montants). Jamais de `SELECT` qui ramène un mail, un nom, une
> adresse, un numéro de carte, un tag NFC, ni le texte de `metadata` (il contient des
> mails et des tags). Jamais de tests ni de worker sur la copie. Claude n'ouvre jamais
> l'écran de Mailpit. À recopier en tête de chaque brief qui touche la copie.

Notation : `main:` = le code de la production (`origin/main`, `a7734099`). Sans
préfixe = le code de la branche. Les numéros de ligne sont approximatifs (« ~l. »).

## 1. Le besoin

En production, chaque lieu a des années de `LigneArticle` écrites par l'ancien code.
Elles n'ont **ni `Vente`, ni `Reglement`, ni montants entiers** (`total_catalogue`,
`part_offerte`, `total_ttc`, `total_ht`, `total_tva` à 0).

Sans reprise :

- **les rapports mentent** : depuis F et G, rapports, exports, totaux client et
  remboursements lisent les ventes et les montants entiers (Q-G5 : aucun repli sur
  l'ancien calcul). L'historique d'un lieu serait vide ;
- **H-2 bloquera** : sa migration de vérification refuse toute ligne sans vente.

La reprise donne à **chaque ancienne ligne** sa vente, ses montants entiers et ses
règlements. Elle ne change **aucun centime** de ce qui a été vendu. Elle ne déclenche
rien : ni mail, ni Fedow, ni ancien LaBoutik, ni Stripe.

**Anciennes clôtures (B-1, Q-R16).** La production fait déjà des clôtures
`comptabilite.ClotureCaisse` avec l'ancien calcul : Celery beat les lance chaque jour
depuis mai 2026 (`main:TiBillet/celery.py` ~l.89-109, `main:comptabilite/tasks.py`
~l.115-199). Elles ne sont pas chaînées comme les nouvelles. **Décision** : la nuit de
la bascule, elles sont **exportées en JSON hors de la base, puis supprimées**. La J
« reprise », le total perpétuel et le rattrapage partent de zéro. R-0 les compte.

## 2. Le principe

1. **On ne crée aucun article.** Les anciennes lignes restent. La reprise les
   **rattache** à une vente et **remplit** leurs colonnes de montants par `.update()`.
   Aucun `save()` sur une ligne : aucun signal, aucune transition de statut, aucune
   tâche Celery.
2. Les montants viennent de **la seule formule** du projet,
   `calculer_montants_article` (`BaseBillet/services_vente.py` ~l.140). La reprise
   n'appelle **pas** `ajouter_article` : il crée une ligne (I-2). Elle refait donc
   elle-même, avec les mêmes règles, la règle « offert à montant non nul » (règlement
   FREE, `part_offerte`, `source_offert`) et `hors_chiffre_affaires` (§6).
3. Les règlements sont **déduits des lignes** (moyen, monnaie, montant). L'ancien code
   ne gardait pas d'autre trace de l'argent reçu.
4. Chaque vente réglée reprise est **numérotée et chaînée comme une vente
   d'aujourd'hui**, dans l'ordre chronologique, à sa **date d'origine**.
5. La reprise tourne **une fois**, la nuit de la bascule, **tous les lieux fermés**
   (Q-R1), **avant** toute nouvelle vente.

## 3. Ce qu'il y a en production (formes réelles de `main`)

Vérifié dans `main:`. La reprise ne connaît que ces formes ; une autre forme vue en
passage à blanc est une **anomalie** (§9).

| Forme | Producteur sur `main` | Signe distinctif |
|---|---|---|
| Billet, adhésion, panier payés en ligne | Stripe Checkout | `paiement_stripe` posé ; moyen `SN`, `SP`, `SR` ou vide (API v1) |
| Abonnement (facture) | webhook facture | `Paiement_stripe.source = I` (INVOICE), moyen `SR` |
| Remboursement Stripe total | `main:BaseBillet/models.py` ~l.2380-2418 | paiement passé en `R` ; lignes d'origine laissées `V` ; une ligne `R` (REFUNDED) par ligne, `qty` négative, `paiement_stripe` recopié, `metadata.original_lignearticle_uuid` |
| Remboursement Stripe d'un billet | `main:BaseBillet/models.py` ~l.2470-2510 | paiement resté `V` ; ligne `R`, `qty` −1 |
| Avoir admin | `main:BaseBillet/models.py` ~l.2343-2366, `main:Administration/admin_tenant.py` ~l.2072, `main:BaseBillet/views.py` ~l.3619 | statut `N` (CREDIT_NOTE), `credit_note_for` posé, `qty` négative, `paiement_stripe` recopié s'il existait |
| Paiement QR / NFC | `main:BaseBillet/views.py` ~l.1297-1335 | origine `QR` / `NF` ; une ligne par transaction Fedow (une par monnaie) ; part dans `amount`, fraction dans `qty` (`dround`, 2 décimales) ; même texte JSON dans `metadata` (liste `transactions`) ; moyen `SF` ou `LE` |
| QR généré jamais payé | idem | ligne `O` (CREATED) restée seule (la ligne payée la remplace, ~l.1313) |
| Recharge API v2 (temps, points, cadeau) | `main:api_v2/views.py` ~l.786-844 | moyen `NA` (offert), `asset` posé ; `O` puis `V` seulement si Fedow répond |
| Réservation gratuite | API v2, billetterie | moyen `NA`, statut `F` (FREERES), `amount` parfois > 0 |
| Adhésion admin | admin | moyen choisi (espèces, chèque…) ou **vide** ; jamais Stripe |
| Adhésion payée par portefeuille (webhook Fedow) | webhook | origine `LB`, moyen `UK`, statut `V` |

Codes de `main` : statuts de ligne `C` annulée, `R` remboursée, `O` créée, `U` non payée,
`P` payée, `F` réservation gratuite, `V` validée, `D` échouée, `N` avoir ; offert = `NA`
(`PaymentMethod.FREE`). Statuts de `Paiement_stripe` : `N O W E F P V S C R` (pas de `H`
sur `main`). **`main` n'a ni `uuid_transaction` ni `point_de_vente` sur les lignes** : la
caisse V2 n'a jamais tourné en production (G-1d). Les formes « caisse V2 » (cascade en
parts, tireuse, pesées, retours de consigne) n'existent pas en production : la reprise
ne les traite pas.

## 4. Le regroupement : une vente = un encaissement d'origine

Règles appliquées **dans cet ordre**. Une ligne entre dans un seul groupe.

| # | Ancienne ligne | Vente reprise | Clé du groupe |
|---|---|---|---|
| 1 | avoir (`credit_note_for` posé ou statut `N`), remboursement (statut `R`), ou toute ligne de **quantité négative** | **une vente AVOIR par ligne** (Q-R5) | uuid de la ligne |
| 2 | origine `QR` ou `NF` | **une vente par paiement QR / NFC** : les parts qui ont le **même texte `metadata`** (Q-R10) | uuid le plus petit des parts du groupe |
| 3 | `paiement_stripe` posé | **une vente par paiement** (R5) | uuid du paiement |
| 4 | toute autre ligne (admin, API, gratuit, webhook Fedow) | **une vente par ligne** | uuid de la ligne |

La règle 1 passe **en premier** : l'ancien code recopiait `paiement_stripe` sur les
lignes négatives. Sans cet ordre, un remboursement tomberait dans la vente d'origine.

**Le lien d'un avoir (Q-R14).** La vente liée (`vente_liee`) est la vente de la ligne
d'origine : `credit_note_for`, sinon `metadata.original_lignearticle_uuid`. Le champ
`metadata` est **un dict OU un texte JSON** selon le producteur : on lit les deux (I-9).
Quand l'origine vient de `metadata`, la reprise pose aussi
`credit_note_for` par `.update()` : sinon un avoir fait après la bascule pourrait
rembourser deux fois (`quantite_restante_de_la_ligne_sous_verrou`, ~l.1142, ne lit que
`credit_notes`). Origine introuvable → **anomalie signalée, la reprise continue**
(l'avoir est repris sans vente liée).

**Le client de la vente** : voir question ouverte QO-3.

## 5. Le statut de la vente reprise

### 5.1 Vente d'un paiement Stripe (règle 3) — le statut suit le paiement

| `Paiement_stripe.status` | Vente | Décision |
|---|---|---|
| `P`, `V`, `S` (payé) | **REGLEE**, numérotée, chaînée | Q-R8 |
| `R` (remboursé) | **REGLEE** à sa date ; ses lignes `R` deviennent des avoirs (règle 1) | Q-R17 |
| `N` (lien jamais généré) | **ANNULEE**, quel que soit l'âge | Q-R18 |
| `O`, `W` (ouvert, SEPA en cours), `order_date` à **moins de 30 jours** du moment de la reprise | **EN_ATTENTE**, reliée au paiement (`Paiement_stripe.vente`) ; le webhook l'encaissera après la bascule | Q-R8 |
| `O`, `W` plus vieux, ou `E`, `F`, `C` | **ANNULEE** | Q-R8 |

L'âge se lit **toujours** sur `order_date` (`auto_now_add`), jamais sur `datetime` ni
`last_action` (`auto_now`, déplacés par tout enregistrement) (I-6, Q-R18).

Les lignes du paiement doivent aller avec son statut : paiement payé ou remboursé →
lignes `V`, `P`, `F` ; sinon → anomalie (§9).

### 5.2 Vente hors Stripe (règles 2 et 4) — le statut suit les lignes

| Lignes du groupe | Vente | Décision |
|---|---|---|
| toutes `V`, `P`, `F` | **REGLEE**, numérotée, chaînée | fiche d'origine |
| `O` (créée) : QR jamais payé, recharge API v2 jamais créditée, adhésion admin bloquée | **ANNULEE**, sans numéro | Q-R7, Q-R19 |
| `C`, `D`, `U` | **ANNULEE**, sans numéro | fiche d'origine |
| statuts mélangés dans un groupe | **anomalie** (§9) | fiche d'origine |

### 5.3 Vente AVOIR (règle 1)

Statuts `N` (avoir) et `R` (remboursement) → **REGLEE**, nature AVOIR, numérotée,
chaînée. Une ligne négative d'un autre statut → anomalie.

### 5.4 Les lignes des ventes annulées ou en attente

Elles reçoivent **aussi** leurs montants et leur vente (I-5). Sinon,
`encaisser_vente_stripe` (~l.2130) ferait de tout le paiement un écart « reçu en plus »
au moment du webhook (il compare le montant reçu à Σ `total_catalogue` des articles).

## 6. Les montants de chaque article

`calculer_montants_article(prix_unitaire=amount, quantite=qty, taux_tva=…,
part_offerte=…, part_en_jetons=…, total_catalogue_impose=…)`, puis `.update()` de la
ligne avec `vente`, `total_catalogue`, `part_offerte`, `source_offert`,
`part_en_jetons`, `total_ttc`, `total_ht`, `total_tva`, `hors_chiffre_affaires`.

**Taux de TVA (Q-R11)** : le taux **écrit sur la ligne** (`vat`), jamais relu sur le
tarif actuel. Taux 0 pour une recharge (hors chiffre d'affaires), une vente en temps
ou en points. Un offert et des jetons sont à TVA 0 par la formule elle-même (net 0 ;
part en jetons hors TVA).

**Part offerte** (règles d'aujourd'hui, `ajouter_article` ~l.502-523, refaites par la
reprise, I-2) :

- moyen `NA` (offert) à montant non nul → `part_offerte` = total catalogue, source
  `OFFRIR`, et un **règlement FREE** du même montant (§7) ;
- réservation gratuite API v2 (`NA`, `F`, `amount` > 0) → même règle (cas 4) ;
- sinon `part_offerte` = 0.

**Jetons cadeau** (moyen `LG`, D8 bis, Q-H1) : vente ordinaire ;
`part_en_jetons` = le net de la ligne (sinon les lecteurs d'après H-1 ne la
reconnaissent plus comme payée en jetons) ; règlement `LG`.

**Parts QR / NFC (Q-R10)** : l'argent réel de chaque part est son `amount`, jamais
`amount × qty`. Donc `total_catalogue_impose = amount`. Les quantités fractionnaires
sont gardées. Leur somme peut valoir 0,99 ou 1,01 (`dround` à 2 décimales,
`main:BaseBillet/views.py` ~l.1328) : **information**, pas anomalie (I-8). Voir QO-1
pour l'anomalie « Σ des parts ≠ montant du QR ».

**Hors chiffre d'affaires** : calculé comme `ajouter_article` (~l.548-555) : produit de
catégorie recharge (`RECHARGE_CASHLESS`, `RECHARGE_CASHLESS_FED`) ou `methode_caisse`
dans `METHODES_CAISSE_HORS_CHIFFRE_AFFAIRES` (~l.83).

**Coût d'achat (Q-R12)** : aucun. `cout_achat` reste vide (« inconnu »).

**Unité de la vente (Q-R11)** : `"EUR"`, sauf une recharge en temps ou en points
(monnaie `TIME` ou `FIDELITY` de `fedow_public.AssetFedowPublic`, lue par
`ligne.asset`) : l'uuid de la monnaie, comme `api_v2/views.py` ~l.1026-1041. Monnaie
introuvable sur une recharge validée → **anomalie, la reprise continue** (Q-R19).

**Avoirs** : `qty` négative, `amount` positif : la formule donne des totaux négatifs.

**H-1 (trace)** : `total_catalogue_impose` reste dans `calculer_montants_article`
(H-1 l'a retiré des producteurs seulement) ; la reprise s'en sert pour les parts QR.

## 7. Les règlements de chaque vente

- **Un règlement par couple (moyen, monnaie)** présent dans la vente. Montant = Σ des
  **nets** (`total_ttc`) des articles payés par ce moyen, déjà arrondis : les égalités
  tiennent par construction. Carte et portefeuille recopiés quand toutes les lignes du
  couple ont les mêmes ; sinon vides.
- **Part offerte** : un règlement `FREE` égal à Σ des parts offertes (première égalité
  d'`encaisser_vente` : Σ règlements = Σ totaux catalogue).
- **Jetons** : un vrai règlement `LG` (D8 bis), compté comme les autres moyens.
- **Moyen vide (Q-R9)** : ligne reliée à un paiement Stripe → `SN` (Stripe carte) ;
  adhésion admin à 0 € → offert ; adhésion admin avec un montant → `UK` (inconnu). Les
  ventes QR ont toujours leur moyen (`SF` / `LE`).
- **Vente Stripe** : un règlement au moyen du paiement (`Paiement_stripe.moyen`, posé
  ci-dessous), relié au paiement. **Pas d'écart d'encaissement** : le montant reçu par
  Stripe n'a pas été gardé.
- **`Paiement_stripe.montant_encaisse` (Q-R4)** = total des articles du paiement, posé
  par `.update()` sur les paiements payés ou remboursés (`P V S R`) : c'est le plafond
  des remboursements futurs. Aucun appel à Stripe. Un paiement en attente le recevra
  du webhook (`BaseBillet/models.py` ~l.4191).
- **`Paiement_stripe.moyen` (B-3)**, par `.update()`, sinon un avoir futur échoue quand
  H retirera `payment_method` : `SP` si une ligne porte `SP` ; `SR` si
  `source = I` (INVOICE) ou si une ligne porte `SR` ; sinon `SN`. Un paiement en attente
  le recevra du webhook (~l.4122-4198). Une ligne d'un paiement Stripe avec un autre
  moyen (`SF`, `LE`, `CA`…) → anomalie (QO-7).
- **Vente AVOIR** : règlement négatif au moyen de la ligne d'avoir.
  **`reference_externe = "reprise"`** pour **tout** ancien avoir relié à un paiement
  Stripe : remboursement Stripe automatique et avoir admin (Q-R6). Sinon le rapport les
  compterait « remboursements Stripe à faire à la main » (`comptabilite/rapport.py`
  ~l.1718 : règlement Stripe négatif à référence vide). Avoir hors Stripe : référence
  vide.
- **Vente à 0** (gratuite) : aucun règlement (`ajouter_reglement` refuse 0).

Les règlements passent par `ajouter_reglement` (~l.1718) : moyens et montants vérifiés.

## 8. Numéro, date, chaîne, marque

- **Date (Q-R14, I-7)** : la date d'une vente reprise est la **date de création de ses
  lignes** : `max(LigneArticle.datetime)` du groupe (`auto_now_add` sur `main`). Un SEPA
  compte au mois de sa commande ; un avoir à la date de sa propre ligne (la date du
  remboursement, Q-R17).
- **`encaisser_vente` reçoit la date (I-1)** : nouveau paramètre facultatif
  `datetime_encaissement=None` (~l.1802, ~l.1932). `None` = `timezone.now()`, comme
  aujourd'hui : le comportement des ventes d'aujourd'hui ne change pas. Même verrou,
  mêmes égalités, même empreinte. La date doit entrer **avant** l'empreinte :
  `datetime_encaissement` fait partie du message (`laboutik/integrity.py` ~l.253-260).
- **Après** l'encaissement, par `.update()` : `Vente.datetime_creation` et
  `Reglement.datetime` (tous deux `auto_now_add`) reçoivent la même date. Ces deux
  champs ne sont **pas** dans l'empreinte : la chaîne reste valide. Même chose pour les
  ventes annulées et en attente.
- **Numéro** : 1, 2, 3… dans l'ordre chronologique du lieu (`encaisser_vente` prend le
  plus grand numéro + 1). Tri sur la date ci-dessus ; à date égale, un avoir passe
  après sa vente liée. Un avoir daté **avant** sa vente liée → anomalie (QO-8).
- **Empreinte** : `calculer_hmac_vente` (`laboutik/integrity.py` ~l.174), avec la clé du
  lieu lue en base (`LaboutikConfiguration.get_or_create_hmac_key`, clé créée dans
  chaque lieu par `laboutik 0002`). Elle relit articles et règlements **en base** :
  tout `.update()` des lignes se fait **avant** `encaisser_vente`.
  `verifier_chaine_ventes` (~l.290) passe à la fin de chaque lieu.
- **Marque de reprise, sans migration** : `Vente.idempotency_key = "reprise-<clé du
  groupe>"` (§4). Elle distingue une vente reprise et rend la reprise **rejouable** :
  un groupe déjà repris est sauté. `ouvrir_vente` rend déjà la vente existante pour une
  clé connue (~l.318-392).
- **Une transaction par vente** : ouvrir, `.update()` des lignes, règlements,
  encaisser (ou annuler), dates. Une coupure se reprend en relançant.
- **Aucun signal** : `Vente` n'a ni signal ni garde sur `.update()` ; la garde
  d'immutabilité de `LigneArticle.save()` (`BaseBillet/models.py` ~l.4590) n'est pas
  appelée par `.update()`. Les contraintes de base de `LigneArticle` (~l.4518-4555 :
  net = catalogue − offert ; HT + TVA = net dès qu'une vente est posée ; part en jetons
  bornée, 0 hors chiffre d'affaires) s'appliquent : le `.update()` pose tous les
  montants en une fois.

## 9. Les anomalies

**La commande ne devine rien.** Une anomalie est signalée dans le rapport du passage à
blanc, avec son type et le nombre de lignes, **sans aucune donnée personnelle**. Chaque
type vu en passage à blanc devient une règle décidée avec le mainteneur, ajoutée à cette
fiche, puis testée.

| Anomalie | Effet |
|---|---|
| statuts mélangés dans un groupe ; lignes qui ne vont pas avec le statut du paiement | groupe **non écrit** |
| ligne négative d'un statut autre que `N` / `R` | groupe non écrit |
| ligne `R` (remboursée) de quantité **positive** (forme ancienne possible : `main:BaseBillet/models.py` ~l.2271 compte `R` parmi les lignes payées) | groupe non écrit (QO-6) |
| avoir dont l'origine est introuvable | **signalée, la reprise continue** (avoir sans vente liée, Q-R14) |
| recharge validée dont la monnaie est introuvable | **signalée, la reprise continue** (Q-R19) |
| ligne d'un paiement Stripe avec un moyen non Stripe | groupe non écrit (QO-7) |
| avoir daté avant sa vente liée | groupe non écrit (QO-8) |
| avoir sur une part QR / NFC | groupe non écrit (QO-5) |
| total ancien (`amount × qty`) ≠ total nouveau de plus d'un centime par article, **hors parts QR** (pour elles l'écart est attendu, Q-R10) | groupe non écrit |
| Σ des `qty` des parts QR hors de [0,99 ; 1,01] | information (I-8) |

« Groupe non écrit » : le reste du lieu est repris. Mais la nuit de la bascule exige
**zéro anomalie bloquante** (§12) : un lieu avec un groupe non écrit garderait des lignes
sans vente.

## 10. La commande

`manage.py reprendre_les_ventes_existantes` :

- **par lieu** (`--schema`) ou tous les lieux ;
- **passage à blanc par défaut** : rien n'est écrit. Le rapport donne, par lieu (nombres
  seulement) : lignes, ventes par nature et par statut, règlements par moyen, totaux
  ancien calcul (`amount × qty`) et nouveau (Σ `total_ttc`), anomalies par type, durée
  mesurée ;
- `--executer` pour écrire ; une transaction par vente (§8) ;
- **garde-fou** : refus si le lieu a déjà une vente `REGLEE` dont la clé ne commence
  pas par `reprise-` (sinon les numéros ne suivraient plus l'ordre du temps) ;
- aucune requête réseau (ni Stripe, ni Fedow, ni ancien LaBoutik), aucune tâche Celery ;
- **ne dépend pas du moteur de monnaie** : aucun des services utilisés ne lit
  `Client.moteur_monnaie` ni les drapeaux de module (vérifié le 2026-10-06). Un lieu
  `legacy` voit ses ventes reprises dans « Ventes et comptabilité » (toujours visible,
  `Administration/admin/dashboard.py`).

## 11. Clôtures, FEC, admin (session R-3)

**Mise en service de la comptabilité (I-3).** Une seule lecture : la date de mise en
service d'un lieu = `datetime_fin` de sa **J « reprise »**. Lieu sans J reprise (aucune
vente historique) : pas de mise en service à respecter.

1. **J « reprise » (Q-R2)** : une J par lieu, la nuit de la bascule, qui couvre tout
   l'historique jusqu'à l'heure de bascule. Elle porte le total perpétuel de tout
   l'historique, comme une J normale, sans code spécial (Q-R13). Marque
   `"reprise": true` dans `rapport_json["en_tete"]` **avant** le scellement : le
   `rapport_json` est dans l'empreinte de la clôture (`comptabilite/integrite.py` ~l.97).
   Donc un paramètre de `_creer_la_cloture_journaliere` / `_enregistrer_la_cloture`
   (`comptabilite/tasks.py` ~l.302, ~l.382). Lieu sans vente : aucune J.
   **Commande synchrone** (I-12), jamais `.delay` (limite Celery de 30 min), et **sans
   mail** : `generer_cloture_pour_tenant` (~l.624) demande le mail (~l.682), la J
   reprise ne passe donc pas par lui.
2. **Rattrapage H / M / A de l'historique (Q-R2, I-4)** : le rattrapage existant
   (`generer_les_clotures_automatiques_du_lieu` ~l.771, `_periodes_finies_a_cloturer`
   ~l.728) partirait de la première vente et créerait des centaines de clôtures d'un
   coup (boucle sans limite). On ajoute un **plafond par passage : 12 clôtures H / M / A
   par lieu** (exemple chiffré du mainteneur, Q-R2). Les H / M / A de l'historique portent
   le perpétuel de la dernière J (la J reprise ou une suivante) : information, à écrire
   dans la doc. Leurs numéros se mêlent aux nouvelles J (chaîne valide, numéros non
   chronologiques) : accepté (Q-R2).
3. **Aucun mail** pour une clôture finie **avant** la mise en service, ni pour la J
   reprise (Q-R2, I-3) : garde dans `demander_l_email_automatique_si_configure` (~l.609)
   ou à ses appelants.
4. **FEC refusé (Q-R3)** pour la J reprise et pour toute H / M / A dont `datetime_debut`
   est avant la mise en service (couvre le mois de la bascule et le mois de la première
   vente). Point d'entrée : `generer_fec_cloture` (`comptabilite/fec.py` ~l.100), appelé
   par `ClotureCaisseAdmin.exporter_fec` (`comptabilite/admin.py` ~l.234). Message :
   « Le FEC commence à la date de mise en service de la comptabilité (jj/mm/aaaa). Pour
   avant, utilisez les rapports mensuels. » Les rapports H / M / A de l'historique restent
   consultables. Balance du plan comptable : QO-2.
5. **Admin (I-10, Q-R6)** : `_adresse_stripe_d_un_reglement`
   (`Administration/admin_tenant.py` ~l.2295) afficherait un lien vers le paiement pour
   un règlement « reprise ». Une référence `"reprise"` ne donne **aucun lien** ; l'écran
   affiche « reprise ».
6. **Filet après la bascule** : la première J automatique part de la fin de la J
   reprise (`_creer_la_cloture_journaliere` lit la dernière J). Rien à changer.

## 12. La nuit de la bascule (session R-4)

Une seule fenêtre, tous les lieux fermés (Q-R1). Tout est préparé avant ; on coupe le
soir, on bascule dans la nuit, on rouvre ensuite.

**Avant la nuit** : copie de la production, R-0, répétition chronométrée de toute la
nuit (I-12, Q-R15). `compter_avant` refait sur un dump le plus récent possible.

**La veille (J-1), en production, en lecture seule** (relecture Fable du 2026-10-07, I-1) :
`manage.py supprimer_lieux_inactifs --rapport <chemin hors dépôt>` (passage à blanc : aucune
écriture, aucun mail). **C'est cette liste que le mainteneur valide** (pas celle de la copie,
migrée et neutralisée). Elle devient le fichier `--liste` de l'étape 2 bis.

**Le mainteneur est aux commandes toute la nuit** (2026-10-07) : il fait aussi la migration de
serveur, avec changement d'IP dans le DNS, et décide seul d'un retour arrière (restauration de
la sauvegarde de l'étape 2 bis et image de `main`).

| # | Étape | Contrôle |
|---|---|---|
| 1 | Application entière coupée (ventes en ligne, admin, API) ; **worker ET beat Celery arrêtés** jusqu'à la J reprise du dernier lieu (I-11). Stripe rejoue ses webhooks jusqu'à 3 jours | une vente admin / API écrite avec le nouveau code bloquerait la reprise du lieu (garde §10) |
| 2 | Postgres relancé avec `max_locks_per_transaction=512` (BUGS n°31) | |
| 1 bis | **Image de la branche déployée avec `MIGRATE=0`**, site toujours coupé (Gunicorn non exposé) : `start.sh` ne doit lancer aucune migration (mainteneur, 2026-10-07 : il s'en occupe, `start.sh` passe aussi en migration un lieu après l'autre) | aucune ligne `migrate_schemas` dans le journal du conteneur |
| 2 bis | **Sauvegarde complète** (`pg_dump -Fc`), puis **suppression des lieux inactifs** : `manage.py supprimer_lieux_inactifs --liste <liste de J-1 validée> --executer --rapport … --traces-externes …` (§18) ; rapports gardés hors dépôt ; puis **suppression des 2 schémas sans lieu** déjà présents en production (mainteneur, 2026-10-07 ; comptés le 2026-10-06 sur la copie) | domaines supprimés = liste validée moins les lieux redevenus actifs ; ensuite 0 schéma sans lieu et 0 lieu sans schéma |
| 3 | **Avant les migrations** : `comptabilite_comptecomptable` et `comptabilite_mappingmoyendepaiement` ne contiennent **que le plan par défaut semé par `main:comptabilite/migrations/0002`** (9 comptes : 411000, 4457100, 4457200, 4457300, 511000, 512000, 530000, 706000, 756000, même jeu dans chaque lieu) ; ce plan est **supprimé et remplacé** par le plan de la branche, sans export (QO-11, mainteneur 2026-10-07) ; un autre compte dans un lieu → STOP. Aucun ancien plan de caisse (`41910000`…). **0 lieu de production avec un drapeau V2** (`compter_avant`, copie-prod §3.5), sinon STOP | `comptabilite 0005` supprime ces tables sans recopie ; `BaseBillet 0227` passerait ces lieux en moteur `v2` |
| 4 | **Export JSON des anciennes clôtures** `comptabilite_cloturecaisse` hors base (B-1, Q-R16), **avant** les migrations (`comptabilite 0004` retire `hash_lignes`) | nombre exporté = nombre en base |
| 5 | Capture de la fiche de l'asset CLAF et de `/fedow/asset/<uuid>/retrieve_bank_deposits/` (copie-prod §3.5, dernière case) ; aucun POST de remise en banque | |
| 6 | `manage.py migrate_schemas` **un lieu après l'autre** (exécuteur standard, **jamais** `--executor=multiprocessing` : interblocage PostgreSQL reproduit deux fois sur la copie du 2026-10-06, deux lieux ajoutant des clés étrangères vers `AuthBillet_tibilletuser` et `QrcodeCashless_cartecashless` dans l'ordre inverse ; mainteneur 2026-10-07) (liste des migrations : ancien §7.2, rappelée au §16) — durée mesurée en répétition (R-0 : §14 ligne 2) | journal : **aucune** ligne `-> [<schéma>] moteur v2 (module V2 actif)` ; tous les lieux `legacy` sauf `W` en `v2` ; empreintes du miroir `fedow_public` identiques ; tables `fedow_core_*` vides |
| 7 | **Suppression des anciennes clôtures** (B-1) | 0 ligne dans `comptabilite_cloturecaisse` |
| 8 | Passage à blanc de la reprise, lecture du rapport : **zéro anomalie bloquante** | |
| 9 | `--executer`, lieu par lieu, puis `verify_integrity` | chaîne des ventes valide |
| 10 | **J reprise** par lieu (commande synchrone, marquée, sans mail ; lieu sans vente : aucune J) | |
| 11 | Réouverture ; Celery relancé : filet J à `heure_de_fermeture` + 2 h ; rattrapage H / M / A plafonné, sans mail | Mailpit de la répétition : 0 mail |
| 12 | Capture CLAF (étape 5) refaite : mêmes chiffres | |

La migration de vérification de H (aucune ligne sans vente) **n'est pas** dans cette
nuit : H-2 vient après la production.

## 13. Découpage en sessions

Tests : **schéma dédié** (`FastTenantTestCase`, tronc §8.5), comme
`tests/pytest/test_qrcode_ecrit_la_vente.py`. Les anciennes lignes sont fabriquées par
`LigneArticle.objects.create` **sans vente**, une par forme réelle du §3. Mutations
jouées à la main par l'orchestrateur.

### R-0 — Comptages sur la copie (orchestrateur, aucun code)

`bash db-prod/copie_prod.sh` : `demarrer`, `charger`, `compter_avant`, `neutraliser`,
`migrer`, `compter`, puis les comptages du §14 (lecture seule, agrégés). Mesures :
durée de `charger`, de `migrer`. Résultat : §14 rempli ; chaque forme imprévue →
question au mainteneur avant R-1.

### R-1 — Le calcul et le passage à blanc

- **Fichiers probables** : `BaseBillet/reprise_des_ventes.py` (neuf : regroupement,
  statuts, montants, règlements, anomalies, sans écriture) ;
  `comptabilite/management/commands/reprendre_les_ventes_existantes.py` (neuf, passage
  à blanc seulement) ; `tests/pytest/test_reprise_des_ventes.py` (neuf).
- **Tests** :
  1. `test_reprise_passage_a_blanc_n_ecrit_rien`
  2. `test_reprise_une_vente_par_paiement_stripe`
  3. `test_reprise_parts_qr_d_un_meme_paiement_en_une_vente`
  4. `test_reprise_ligne_negative_ou_remboursee_devient_un_avoir_meme_avec_un_paiement_stripe`
  5. `test_reprise_statut_suit_le_paiement_stripe` (P V S R → réglée ; N → annulée ; O / W récents → en attente ; vieux, E F C → annulée)
  6. `test_reprise_ligne_creee_hors_stripe_vente_annulee`
  7. `test_reprise_parts_qr_argent_egal_au_montant_de_la_part`
  8. `test_reprise_offert_a_montant_non_nul_part_offerte_et_reglement_free`
  9. `test_reprise_jetons_part_en_jetons_egale_au_net`
  10. `test_reprise_moyen_vide_stripe_carte_ou_inconnu_ou_offert`
  11. `test_reprise_recharge_en_points_vente_dans_l_unite_de_la_monnaie`
  12. `test_reprise_anomalies_comptees_sans_donnee_personnelle` (dont monnaie introuvable et origine introuvable : signalées, le reste continue)
  13. `test_reprise_totaux_identiques_a_l_ancien_calcul_hors_parts_qr`
  14. `test_reprise_metadata_lue_en_dict_et_en_texte`
- **Mutations** : une vente par ligne au lieu d'une par paiement ; règle « négatif »
  après la règle Stripe ; `amount × qty` pour une part QR ; âge lu sur `last_action` ;
  `N` récent en attente ; seuil de 30 jours retiré ; TVA relue sur le tarif ;
  `metadata` texte non lu.

### R-2 — L'écriture

- **Fichiers probables** : `BaseBillet/reprise_des_ventes.py`, la commande
  (`--executer`), `BaseBillet/services_vente.py` (`encaisser_vente` :
  `datetime_encaissement=None`), `tests/pytest/test_reprise_des_ventes.py`.
- **Tests** :
  1. `test_reprise_toutes_les_lignes_ont_une_vente`
  2. `test_reprise_egalites_tenues_pour_chaque_vente`
  3. `test_reprise_numeros_dans_l_ordre_chronologique_et_chaine_valide`
  4. `test_reprise_date_d_origine_gardee_sur_vente_et_reglements`
  5. `test_reprise_avoir_lie_a_la_vente_d_origine_et_credit_note_for_pose`
  6. `test_reprise_avoir_stripe_reference_reprise`
  7. `test_reprise_paiement_stripe_moyen_et_montant_encaisse_poses`
  8. `test_reprise_vente_en_attente_encaissee_par_le_webhook_sans_ecart`
  9. `test_reprise_ne_declenche_ni_mail_ni_fedow_ni_laboutik` (aucune tâche Celery, aucun appel réseau)
  10. `test_reprise_rejouee_ne_double_rien`
  11. `test_reprise_refusee_si_le_lieu_a_deja_une_vente_hors_reprise`
  12. `test_reprise_groupe_en_anomalie_non_ecrit_le_reste_ecrit`
  13. `test_reprise_lignes_jamais_payees_vente_annulee_sans_numero`
  14. `test_encaisser_vente_sans_date_garde_maintenant` (caractérisation de l'appel d'aujourd'hui)
- **Mutations** : date « maintenant » au lieu de la date d'origine ; ordre non
  chronologique ; `save()` au lieu de `.update()` (les signaux partent) ; garde « lieu
  déjà vendu » retirée ; clé de reprise retirée (rejeu en double) ; référence
  « reprise » vide ; `credit_note_for` non posé ; `.update()` des lignes après
  l'encaissement (empreinte fausse).
- Caractérisation (`test_caracterisation_*.py`) verte **sans modification**.

### R-3 — Clôtures, FEC, admin

- **Fichiers probables** : `comptabilite/tasks.py`, `comptabilite/fec.py` (ou
  `comptabilite/admin.py`), une commande de J reprise
  (`comptabilite/management/commands/`), `Administration/admin_tenant.py`
  (`_adresse_stripe_d_un_reglement` et l'affichage), un test neuf
  `tests/pytest/test_reprise_clotures.py`.
- **Tests** :
  1. `test_j_reprise_couvre_tout_l_historique_et_porte_le_perpetuel`
  2. `test_j_reprise_marquee_dans_l_en_tete_et_empreinte_valide`
  3. `test_j_reprise_n_envoie_aucun_mail`
  4. `test_lieu_sans_vente_aucune_j_reprise`
  5. `test_rattrapage_plafonne_a_douze_par_passage`
  6. `test_aucun_mail_pour_une_cloture_finie_avant_la_mise_en_service`
  7. `test_fec_refuse_sur_la_j_reprise_avec_le_message`
  8. `test_fec_refuse_sur_un_mois_qui_commence_avant_la_mise_en_service`
  9. `test_fec_accepte_apres_la_mise_en_service`
  10. `test_reglement_reprise_sans_lien_stripe_dans_l_admin`
  11. `test_filet_apres_la_bascule_part_de_la_fin_de_la_j_reprise`
- **Mutations** : marque posée après le scellement ; plafond retiré ; garde mail
  retirée ; comparaison `<` / `<=` de la mise en service ; FEC accepté sur la J reprise ;
  lien Stripe rendu pour « reprise ».

### R-4 — La nuit, répétée sur la copie

Procédure du §12 écrite pas à pas (commandes exactes, contrôles, durées), puis
**répétition chronométrée** sur la copie (copie-prod §3.3 et §3.5). Aucun code, sauf
des corrections nées de la répétition (nouvelle session). Puis `detruire` et
suppression du dump.

Fin de fiche R : `make test` complet, CHANGELOG, relecture Fable, commit par le
mainteneur.

## 14. R-0 — chiffres de la copie (2026-10-06)

Dump : `tibillet.re-M0221-2026-10-06-04-52.sql.gz` (grappe `pg_dumpall` ; base
`tibillet` extraite en local). **Agrégats seulement.**

| # | Comptage | Pour la règle | Résultat |
|---|---|---|---|
| 1 | lieux (hors `public`), par catégorie ; lieux de production avec un drapeau V2 (`compter_avant`) ; lieux avec `server_cashless` renseigné | §12 étape 3 | **513 lieux** : 491 `S`, 20 `W` (pool), 1 `F`, 1 `M`. **0 lieu avec un drapeau V2 → OK.** `module_kiosk` absent des 513. `server_cashless` renseigné : 42 (41 `S`, 1 `F`). `module_federation` : 495 |
| 2 | durée de `charger`, de `migrer` | §12 | `charger` : 2 769 s (46 min, dump texte en une transaction, `max_locks_per_transaction` = 4 096 sur la copie ; 512 n'a pas suffi). `migrer` : **11 637 s (3 h 14) un lieu après l'autre** (~23 s par lieu ; 7 lieux déjà migrés par les deux essais en parallèle, arrêtés sur interblocage) ; schéma public : 17 s. Journal : **0 ligne « moteur v2 (module V2 actif) »** |
| 3 | lignes par statut × moyen × origine (`compter`) | §3, §5 | voir R-0 détail ci-dessous (tableau A) |
| 4 | lignes par lieu : total, et les 5 plus gros volumes (nombres seulement) | durée | **23 465 lignes** dans **115 lieux** (2022-05-13 → 2026-10-06). 5 plus gros : 4 164, 2 597, 2 381, 1 304, 1 131 |
| 5 | `Paiement_stripe` par statut, dont `R` et `N` ; `O` / `W` de moins de 30 jours (`order_date`) | §5.1 | `V` 11 305, `W` 4 698 (dont 167 de moins de 30 j), `R` 90, `E` 52, `P` 25. **Aucun `N`, `O`, `F`, `S`, `C`** |
| 6 | `Paiement_stripe` avec `source = I` ; lignes `SR` | §7 (B-3) | `source` : `F` 13 634, `Q` 1 652, `B` 498, `I` 254, `T` 125, `C` 7. Lignes `SR` : 254 (= `source I`) |
| 7 | lignes d'un paiement Stripe par moyen (dont vide, `SF`, `LE`, `CA`) | §7, QO-7 | vide 4 949 (`O` 133, `P` 23, `R` 8, `U` 3 105, `V` 1 680), `SN` 11 536, `SP` 108, `SR` 254. **Aucun `SF` / `LE` / `CA` → QO-7 sans objet** |
| 8 | paiements Stripe dont les lignes ont des statuts mélangés, ou ne vont pas avec le statut du paiement | §5.1, §9 | paiement × statuts des lignes positives (hors `N`, `R`) : `V`/`V` 11 052, `V`/`P` 128, `V`/aucune 125, `W`/`U` 4 447, `W`/`O` 97, `W`/aucune 154, `R`/`V` 89, `R`/`P` 1, `E`/`U` 52, `P`/`P` 20, `P`/`V` 4, `P`/aucune 1. **Aucun groupe à statuts mélangés.** Paiements **sans aucune ligne** : 280 (voir QO-9) |
| 9 | lignes à `qty` négative, par statut ; dont `credit_note_for` vide ; dont `metadata` avec `original_lignearticle_uuid` (dict / texte) ; dont origine introuvable | §4, §9 | `N` : 33 (toutes avec `credit_note_for`, 20 ont aussi l'origine en `metadata`, 2 sur un paiement Stripe). `R` : 105 (aucune avec `credit_note_for`, **toutes** avec l'origine en `metadata`, toutes sur un paiement Stripe). **Origine introuvable : 0. Sans aucun lien : 0** |
| 10 | lignes `R` de quantité positive | QO-6 | **0 → QO-6 sans objet** |
| 11 | lignes `QR` / `NF` ; groupes par texte `metadata` (comptés par empreinte md5, jamais affichés) ; parts par groupe (1, 2, plus) ; groupes dont Σ `qty` est hors de [0,99 ; 1,01] | §6, QO-1 | `NF` `V` 1 234, `QR` `V` 555, `QR` `O` 319 ; `metadata` toujours en texte JSON (`string`), jamais vide. Payées : **1 789 groupes, tous d'UNE seule part** ; Σ `qty` hors bornes : 0 ; statuts mélangés : 0. **Aucun paiement QR / NFC en deux monnaies en production → QO-1 sans objet** |
| 12 | avoirs dont la ligne d'origine est une part QR / NF | QO-5 | **0 → QO-5 sans objet**. (43 avoirs portent sur une ligne de `qty` ≠ 1 : billets multiples, forme normale) |
| 13 | avoirs datés avant leur ligne d'origine | QO-8 | **0 → QO-8 sans objet** |
| 14 | lignes `LG` (jetons) | §6 | **0** (`part_en_jetons` : rien à poser). Lignes `LE` : 2 010, toutes `V` |
| 15 | lignes sans moyen, par statut, avec / sans paiement Stripe, par catégorie de produit | §7 (Q-R9) | 4 949, **toutes sur un paiement Stripe** → `SN` (Q-R9). Catégories `A`, `B`, `N` ; montant nul : 2 859. **Aucune adhésion admin sans moyen** |
| 16 | lignes `NA` (offert) à `amount` > 0, par statut | §6 | 8 lignes `V`, catégorie `R` (recharge), monnaie `TNF` (voir QO-10) ; toutes les autres `NA` à 0 (`V` 1 027, `N` 26, `P` 3, `F` 1) |
| 17 | recharges (catégorie recharge) dont `asset` est introuvable dans `fedow_public_assetfedowpublic` ; par catégorie de monnaie | §6, Q-R19 | lignes avec `asset` : `TLF` 2 010 (catégorie `Q`), `FED` 4 (`Q`), `TNF` 8 (`R`). **Monnaie introuvable : 0. Recharge sans `asset` : 0** |
| 18 | lignes `O` (créées) hors Stripe, par origine et catégorie | §5.2 | 431, toutes catégorie `Q`, moyen `QR` (QR jamais payé, Q-R7) : origine `QR` 319, `LP` 112 |
| 19 | anciennes clôtures `comptabilite_cloturecaisse` par niveau, par lieu (avant `migrer`) | B-1, §12 étape 4 | **74 239** : `J` 62 943 (513 lieux, 1 209 non nulles), `H` 9 022 (510 lieux, 532 non nulles), `M` 2 274 (505 lieux, 224 non nulles), aucune `A`. Du 2026-05-20 au 2026-10-06. **B-1 confirmé** (Q-R16 : export JSON puis suppression) |
| 20 | `comptabilite_comptecomptable` et `comptabilite_mappingmoyendepaiement` non vides ; comptes à 7 chiffres | §12 étape 3 | **NON VIDES → STOP §12 étape 3 (QO-11)** : 4 617 comptes, 6 669 liens, dans les 513 lieux. C'est le **plan par défaut semé par `main:comptabilite/migrations/0002`** (`_seed_comptes_et_mappings`), **identique dans les 513 lieux** (même empreinte, tous actifs) : 411000, 4457100/200/300 (TVA, les seuls à 7 chiffres), 511000, 512000, 530000, 706000, 756000. **Pas d'ancien plan de caisse** (`41910000`) |
| 21 | après `migrer` : lieux avec une `Vente` ou un `Reglement` (attendu 0) ; lieux sans clé d'empreinte (attendu 0) ; moteur par catégorie | §10 garde, §8 | **0 lieu avec une vente ou un règlement ; 0 lieu sans clé d'empreinte.** Moteur : `legacy` pour `S` 491, `F` 1, `M` 1, `R` 1 ; `v2` pour les 20 `W`. Tables `fedow_core_*` à 0. Miroir `fedow_public` (235 monnaies, 44 fédérations, 2 invitations) et réseau CLAF (2 monnaies actives, 40 lieux) : **empreintes identiques avant / après**. Anciennes clôtures toujours là (74 239) : suppression à faire la nuit (étape 7) |
| 22 | Σ `amount × qty` par statut (en euros, tous lieux) | §10 comparaison | `V` 375 740,43 € (17 834 l.), `U` 155 590,89 € (4 758), `O` 13 527,03 € (582), `P` 1 633,00 € (152), `F` 0 (1), `N` −175,00 € (33), `R` −3 459,00 € (105) |
| 23 | mails captés par Mailpit (`compter`) | sécurité | **0** après `charger`, `neutraliser`, `migrer` |

**R-0 détail — tableau A (lignes par statut × moyen × origine).** `F NA AP` 1 · `N` : `CA AD` 3, `CC AD` 1, `NA AD` 26, `SN AD` 2, `TR AD` 1 · `O` : vide `LP` 133, `QR LP` 112, `QR QR` 319, `SN LP` 18 · `P` : vide `LP` 23, `NA LP` 3, `SN LP` 126 · `R` : vide `LP` 8, `SN LP` 97 · `U` : vide `LP` 3 105, `SN AP` 1, `SN LP` 1 613, `SP LP` 39 · `V` : vide `LP` 1 680, `CA AD` 1 863, `CA LP` 93, `CC AD` 627, `CC LP` 36, `CH AD` 37, `CH LP` 2, `LE AD` 1, `LE LP` 221, `LE NF` 1 234, `LE QR` 554, `NA AD` 231, `NA LP` 804, `SF AD` 2, `SF LP` 1, `SF QR` 1, `SN AD` 1, `SN LP` 9 679, `SP LP` 69, `SR LP` 26, `SR WK` 228, `TR AD` 34, `UK LB` 410.

**Autres constats de R-0** (pour les règles) :
- Lignes `LE` / `SF` d'origine `LP` ou `AD` : 226 (`LE LP` 221, `LE AD` 1, `SF LP` 1, `SF AD` 2… ) — des paiements QR / NFC écrits **sans** l'origine `QR` / `NF` (ancien code). Ils tombent en règle 4 (une vente par ligne) : même résultat, puisque tout paiement QR n'a qu'une part. **4 lignes à `qty` non entière hors `QR` / `NF`** (`AD LE`, `AD SF`, `LP LE`, `LP SF`, une chacune) : voir QO-12.
- TVA : `A` 0 % (10 411) ou 20 % (1 245) ; `B` 0 % (7 159), 2,1 % (256), 5,5 % (7), 10 % (40), 20 % (11) ; `F`, `N`, `Q`, `R` à 0 %.
- Aucune ligne sans tarif vendu (`pricesold`).

### 14 bis. R-1 — passage à blanc sur la copie (2026-10-07)

Copie migrée, **déjà nettoyée des 148 lieux inactifs** (365 lieux). Commande
`reprendre_les_ventes_existantes` (lecture seule), sortie complète hors dépôt
(`db-prod/passage_a_blanc_R1_2026-10-07.txt`, mode 600). **Agrégats seulement.**

| Mesure | Résultat | Comparaison avec R-0 |
|---|---|---|
| lignes lues | **23 465** | = R-0 (les lieux supprimés n'avaient aucune ligne) |
| durée | 31,7 s de calcul (42 s en tout) | |
| ventes | `VENTE REGLEE` 17 575 (dont 125 virements reçus), `VENTE ANNULEE` 4 617, `VENTE EN_ATTENTE` 159, `AVOIR REGLEE` 138 | avoirs 138 = 33 `N` + 105 `R` ; en attente 159 contre 167 `W` de moins de 30 jours au 2026-10-06 (un jour de plus) |
| règlements | `SN` 8 011 · 644 852,25 € ; `LE` 2 010 · 48 944,08 € ; `SR` 254 · 18 540,00 € ; `CA` 1 957 · 8 989,80 € ; `SP` 69 · 8 010,00 € ; `CC` 664 · 4 036,00 € ; `TR` 35 · 3 078,00 € ; `UK` 401 · 2 600,00 € ; `CH` 39 · 1 105,00 € ; `SF` 4 · 161,00 € ; `NA` 8 · 11,75 € | `SR` 254 = lignes `SR` ; `LE` 2 010 = lignes `LE` ; `TR` 35 = 34 + 1 avoir |
| hors parts QR : ancien Σ `amount × qty` / nouveau Σ `total_catalogue` | **487 312,48 € / 487 312,48 €** | égaux |
| Σ net vendu (`total_ttc`) / Σ part offerte | 909 434,05 € / 11,75 € (les 8 recharges `TNF`, QO-10) | |
| virements reçus (paiements `T`) | **125 ventes, 366 514,85 €, 24 lieux** | = 125 paiements `T` |
| paiements Stripe sans ligne (aucune vente) | 155 | = 154 `F` / `W` + 1 `Q` / `P` |
| anomalies | **0 bloquante.** « monnaie de recharge introuvable » : 1 004 lignes, non bloquante | voir ci-dessous |
| information | 28 paiements QR dont Σ `qty` sort de [0,99 ; 1,01] | |

**Les 1 004 « monnaies de recharge introuvables »** : anciennes lignes de catégorie `R`, **à 0 €**,
sans `asset`, moyen vide, origine en ligne, validées, sur des paiements Stripe validés, dans 4 lieux,
de 2022-05 à 2024-07. R-0 ne les voyait pas (il ne comptait que les lignes avec `asset`). Effet :
reprises en euros, à 0 €, signalées (Q-R19) ; aucun argent en jeu, pas de code (orchestrateur).

### 14 ter. R-2 — écriture sur la copie (2026-10-08)

Lancée par le mainteneur (`--executer`), après un instantané de la copie migrée et nettoyée
(`db-prod/copie_migree_nettoyee_2026-10-08.dump`, `pg_dump -Fc`, 256 Mo, mode 600 : il permet de
revenir en arrière sans refaire les migrations : `detruire`, `demarrer`, `charger <instantané>`).

| Mesure | Résultat |
|---|---|
| ventes écrites | **22 489** (`VENTE REGLEE` 17 575, `ANNULEE` 4 619, `EN_ATTENTE` 157, `AVOIR` 138) ; mêmes règlements et totaux que le passage à blanc (§14 bis) |
| chaîne des ventes | **valide dans les 365 lieux** ; 0 erreur, 0 lieu refusé |
| durée | **12 min** d'écriture (720 s) + 31 s de calcul ; le plus gros lieu : 80 s (2 381 lignes, ~34 ms par vente) |
| contrôle après (agrégats) | 0 ligne sans vente ; 0 vente hors reprise ; 0 paiement `T` sans vente ; 0 paiement payé sans `montant_encaisse` |
| signaux | seulement le journal `send_membership_product_to_fedow` à la création du produit `VR` (le signal ne contacte Fedow que pour une adhésion ou un badge) |

### 14 quater. R-3 et R-4a — clôtures sur la copie (2026-10-08)

Lancés par le mainteneur après l'écriture de R-2 (§14 ter). **Agrégats seulement.**

| Étape | Résultat |
|---|---|
| `anciennes_clotures --exporter` | 365 lieux, **50 827** clôtures exportées (R-0 : 74 239 avant la suppression des 148 lieux inactifs), **4,8 s** |
| `anciennes_clotures --supprimer --export … --executer` | 50 827 supprimées, **0 lieu refusé**, **2,5 s** |
| `creer_la_cloture_de_reprise` | **102 J reprise** (numéro 1, marquées `reprise`), 263 lieux sans vente réglée, 0 refus, 0 erreur |
| `verify_clotures` | « Audit complet : aucune anomalie détectée » |
| total perpétuel des J reprise | = Σ `total_ttc` des ventes réglées dans 78 lieux ; dans les 24 autres, = Σ moins le hors chiffre d'affaires (ce sont les 24 lieux à virements reçus) : la J compte le chiffre d'affaires, comme une J ordinaire |

**Les 28 « paiements QR dont Σ `qty` sort de [0,99 ; 1,01] » (§14 bis)** : des demandes QR
**jamais payées** (statut `O`, origine `QR`) dont le texte `metadata` est identique ; elles sont
réunies par groupe de 4 à 82 lignes dans **une vente ANNULEE** chacune (sans numéro, sans
règlement). Aucun argent en jeu ; R-0 ne comptait que les QR payés (0 hors bornes).

## 15. Décisions appliquées

Q-R1 (une fenêtre), Q-R2 (J reprise, rattrapage plafonné sans mail), Q-R3 (FEC refusé
avant la mise en service), Q-R4 (montant encaissé = total des articles), Q-R5 (un avoir
par ligne), Q-R6 (tous « reprise »), Q-R7 (QR jamais payé → annulée), Q-R8 (statut selon
le paiement et son âge), Q-R9 (moyen vide), Q-R10 (parts QR), Q-R11 (TVA et unité),
Q-R12 (coût inconnu), Q-R13 (perpétuel = tout l'historique), Q-R14 (date des lignes,
lien des remboursements), Q-R15 (copie complète en local), Q-R16 (anciennes clôtures
exportées puis supprimées), Q-R17 (paiement `R`), Q-R18 (paiement `N`), Q-R19 (restés
« créés »). Texte complet : `CHANTIER-05-SUIVI.md` §5. Défauts techniques de la
relecture Fable intégrés sans décision du mainteneur : B-3 (moyen du paiement), I-1,
I-2, I-3, I-5, I-7, I-9, I-10, I-11, I-12.

## 16. Ce que la fiche ne change pas, et traces

**Ne change pas** : aucune ligne supprimée ; aucun montant vendu changé ; aucune
nouvelle colonne ; le comportement des ventes d'aujourd'hui (`encaisser_vente` sans
date) est inchangé ; `kiosk/` intouché.

**Trace de H-1** : `total_catalogue_impose` gardé (§6) ; `LigneArticle.part_en_jetons`
(§6) ; les lignes sans vente écrites après la bascule (demandes QR jamais payées) sont
réglées par H-2, après la production ; anciennes pesées et anciens retours de consigne :
**sans objet** (caisse V2 jamais en production). Les colonnes `payment_method`, `asset`,
`carte` des lignes historiques sont **lues** par la reprise : H-2 les retire après R
(Q-H2).

**Trace du verrou moteur** (`FEDOW_IMPORT/15-spec-verrou-moteur-legacy.md`) : après
`Customers 0006`, tous les lieux de production restent `legacy`, sauf le réservoir `W`
en `v2` ; condition : 0 lieu de production avec un drapeau V2 avant la bascule (§12).

**Migrations de la branche** (depuis `556e2877`, elles repartent de `main`) : public —
`Customers 0005`, `0006_moteur_de_monnaie` ; `AuthBillet 0024` ; `MetaBillet 0018` ;
`QrcodeCashless 0021` ; `root_billet 0007` ; `fedow_public 0004` ; `fedow_core 0001` ;
`discovery 0003` ; `seo 0005` (données), `0006` ; `onboard 0002` ; `pages 0001`
(public et lieux). Chaque lieu — `BaseBillet 0222` à `0227` (dont `0227_moteur_v2_si_un_module_v2_est_actif`) ;
`comptabilite 0004`, `0005` ; `laboutik 0001`, `0002` (plan par défaut, clé
d'empreinte) ; `booking`, `controlvanne`, `inventaire`, `kiosk 0001` ; `crowds 0009`.
Apportées par la fusion d'`origin` (`3dc853fc`, 2026-10-07), vérifiées le 2026-10-08 :
`BaseBillet 0228` (`AlterField` d'un texte de `FederationConfiguration`) ; `booking 0002`
(`Resource.group` obligatoire : sans risque, la table `booking_resource` naît vide la même nuit
par `booking 0001`) et `booking 0003` (sème les groupes « Ressource » et « Espace » dans chaque
lieu : l'outil `supprimer_lieux_inactifs` les tolère, R-N-bis).

## 17. Questions ouvertes pour le mainteneur

**QO-1 — L'anomalie « Σ des parts ≠ montant du QR » (Q-R10) ne peut pas être
vérifiée.** Le montant demandé par le QR n'est gardé nulle part : à la création des
parts, l'ancienne ligne est supprimée (`main:BaseBillet/views.py` ~l.1311) et chaque part
prend le montant de sa transaction. Exemple : QR de 10,00 € payé 6,00 € en fédéré et
4,00 € en local → deux lignes, `amount` 600 et 400 ; la somme vaut toujours 1 000, il n'y
a rien à comparer. Proposé (I-8) : retirer cette anomalie ; signaler seulement, pour
information, les groupes dont Σ `qty` sort de [0,99 ; 1,01].

**QO-2 — La balance du plan comptable. Tranchée (mainteneur, 2026-10-08) : balance acceptée**, pas de refus.
 Q-R3 refuse le FEC avant la mise en service.
La **balance** (`comptabilite/balance.py`, onglet « Gérer » du plan comptable) lit les
mêmes J, datées du jour de leur **première** vente. La J reprise y serait datée du jour
de la plus vieille vente du lieu. Exemple : balance de janvier 2024 → elle contiendrait
tout l'historique, de 2024 à la bascule. Refuser aussi la balance sur une période qui
contient la J reprise (même message que le FEC) ?

**QO-3 — Le client d'une vente reprise.** Aucune ligne de `main` ne porte l'acheteur.
Proposé : l'utilisateur du paiement Stripe (`Paiement_stripe.user`), sinon celui de
l'adhésion (`membership.user`), sinon vide. Aucun écran ne filtre les ventes par client
aujourd'hui : c'est une information.

**QO-4 — Le plafond du rattrapage. Tranchée (mainteneur, 2026-10-08) : 12 par lieu et par passage.**
 Q-R2 dit « ex. 12 par lieu et par heure ». La
fiche écrit 12. Confirmer ce chiffre.

**QO-5 — Un ancien avoir sur une part QR / NFC** (à poser seulement si R-0 en trouve).
L'avoir admin de `main` recopie `qty = −qty` et `amount` : sur une part de 600 avec
`qty` 0,6, la formule rendrait 360 au lieu de 600. Imposer `total_catalogue = −amount`
(comme le « miroir » d'après la bascule) ?

**QO-6 — Une ligne « remboursée » de quantité positive** (à poser seulement si R-0 en
trouve) : ancienne forme où la ligne d'origine elle-même passait en `R`. Vente réglée +
avoir du même montant, ou autre règle ?

**QO-7 — Une ligne d'un paiement Stripe avec un moyen non Stripe** (`SF`, `LE`, `CA`…)
(à poser seulement si R-0 en trouve). La règle B-3 donnerait `SN` au paiement.

**QO-8 — Un avoir daté avant sa vente liée** (à poser seulement si R-0 en trouve). Exemple :
un paiement de deux billets dont le second a été ajouté après le remboursement du
premier. Garder la date de l'avoir (numéro avant la vente) ou le dater comme sa vente ?

**QO-11 — Plan comptable déjà présent en production** (trouvé par R-0, §14 ligne 20).
**Tranchée (mainteneur, 2026-10-07)** : le plan par défaut de `main` (9 comptes semés par
`main:comptabilite/migrations/0002`, identiques dans les 513 lieux) est **supprimé et
remplacé** par le plan de la branche, sans export : « ça n'aurait jamais dû être en prod ».

## 18. Supprimer les lieux sans aucune activité, avant la migration (session R-N)

**Décision du mainteneur (2026-10-07)** : supprimer complètement, la nuit de la bascule, **juste
avant `migrate_schemas`**, les lieux qui n'ont jamais eu aucune activité : leur schéma et leurs
domaines. But : place en base et ~57 min de migration en moins (148 lieux sur la copie du
2026-10-06 au passage réel de l'outil, ~23 s chacun ; la mesure SQL du jour disait 153). On **garde les utilisateurs** ; on ne supprime rien d'autre dans les
tables partagées que ce qui appartient au lieu.

**L'outil** : `manage.py supprimer_lieux_inactifs`, en **SQL brut** (`connection.cursor()`),
jamais par les modèles : la nuit, le code est celui de la branche mais la base n'est pas encore
migrée (`Client.moteur_monnaie` n'existe qu'après `Customers 0006`). `Client.delete()` est
inutilisable sur ce projet (`tests/PIEGES.md`, piège 12.5).

- **À blanc par défaut** ; `--executer` pour écrire. **Chaque lieu est désigné par son domaine
  principal** (`Customers_domain.is_primary`), jamais par son nom ni son schéma (souvent un uuid).
- **Rapport** : deux listes, affichées et écrites en CSV (`--rapport`) :
  - **lieux supprimés** (à blanc : « à supprimer ») : domaine, date de création, raison ;
  - **lieux gardés** : domaine, date de création, **toutes** les raisons qui les gardent.
  Plus un CSV des **traces externes** des lieux supprimés (identifiant Stripe Connect, place Fedow)
  pour un nettoyage plus tard, hors de cette nuit.
- **Double vérification** : avec `--executer`, `--liste <fichier de domaines>` est obligatoire ; un
  lieu n'est supprimé que s'il est **dans la liste validée par le mainteneur ET encore inactif** au
  moment de l'exécution. Un lieu de la liste redevenu actif est gardé et signalé.
- **Une transaction par lieu** : `DROP SCHEMA … CASCADE`, nettoyage des liens partagés, domaines,
  ligne `Client`. Les clés étrangères sont vérifiées au `COMMIT` : une référence oubliée fait
  échouer la transaction et **le schéma revient**.
- Toutes les références vers le lieu sont **lues dans le catalogue** (`pg_constraint`, tous les
  schémas), jamais dans une liste écrite à la main.

**Un lieu est inactif si TOUT est vrai** (sinon il est gardé, avec la raison) :

| # | Critère | Lecture |
|---|---|---|
| 1 | catégorie ni `W` (pool), ni `M` (meta), ni `R` (racine) | `Customers_client.categorie` |
| 2 | créé il y a plus de `--jours-minimum` jours (défaut **60**) | `created_on` |
| 3 | aucune activité : 0 ligne dans événements, lignes de vente, adhésions, paiements Stripe, réservations, billets, produits / prix vendus, `crowds_*`, transactions Fedow | schéma du lieu |
| 4 | catalogue de l'onboarding seulement : au plus 1 produit, de catégorie réservation gratuite (`F`), tous ses prix à 0 ; au plus 1 adresse | schéma du lieu |
| 5 | **aucune autre table non vide** que celles que la création d'un lieu ou les migrations remplissent seules (configurations uniques, TVA, jours, clôtures **à montant nul**, plan comptable par défaut, etc. : liste explicite dans l'outil, établie sur un lieu neuf) ; sur une base migrée, la page d'accueil créée par `BaseBillet 0225` est tolérée (au plus 1 page d'accueil, 3 blocs, 0 image : décision de l'orchestrateur, 2026-10-07) ; une table inconnue non vide → lieu gardé | schéma du lieu |
| 6 | configuration jamais personnalisée : champs égaux aux **défauts du modèle**, sauf ceux que le formulaire de création remplit (nom, slug, email, descriptions, site, téléphone, Stripe Connect, adresse) ; donc aussi pas de LaBoutik V1, pas d'inscription Stripe terminée, pas de logo ni d'image | schéma du lieu |
| 7 | rien dans les tables partagées qui montre une activité : monnaie Fedow (créée, fédérée, invitée), cartes NFC (`Detail.origine`), droits donnés (`create_event`, `initiate_payment`, `manage_crowd`), répertoires `MetaBillet`, appareils appairés, `fedow_core` | schéma public |
| 8 | **cité par aucun autre lieu** (`FederatedPlace`, `configuration_federated_with`, fédérations `fedow_connect`, `artist_on_event`) | tous les schémas |

**Ce que la suppression fait aux tables partagées** (défauts de l'orchestrateur, prudents, à
confirmer) : utilisateurs **gardés** (`client_source` → vide, liens M2M du lieu retirés) ;
**portefeuilles gardés** (`AuthBillet_wallet.origin` → vide, au lieu de la cascade) ; **fiche
d'onboarding supprimée** (`MetaBillet_waitingconfiguration` : elle porte l'email et les
coordonnées du demandeur, et le mail dit que les données du lieu sont supprimées) ; cache SEO
et invitations d'onboarding du lieu supprimés.

**Mail aux administrateurs** (mainteneur, 2026-10-07) : après la suppression **réussie** d'un
lieu (dans `transaction.on_commit`, jamais si la transaction est annulée), chaque
administrateur du lieu (`client_admin`, adresses lues **avant** la suppression) reçoit **un**
mail, qui liste tous ses lieux supprimés. Envoi **en file Celery** (`.delay()`) : la nuit, le
worker est arrêté, les mails partent à la réouverture. Option `--sans-mail` (répétition sur la
copie, où le capteur Mailpit les compte de toute façon). Texte (à valider par le mainteneur) :

> **Objet** : Votre espace TiBillet a été fermé
>
> Bonjour <adresse>, *(imposé par le gabarit générique du projet, accepté par le mainteneur)*
>
> Votre espace TiBillet **<domaine>**, ouvert le <date>, n'a jamais été utilisé : aucun
> événement, aucune adhésion, aucune vente. Dans un souci de mutualisation, nous supprimons
> les espaces non utilisés : nous l'avons fermé et nous avons supprimé ses données.
>
> Si vous souhaitez en ouvrir un nouveau, n'hésitez pas à retourner sur
> https://tibillet.coop. Une nouvelle version de TiBillet arrive très bientôt.
>
> Vos données personnelles : votre compte TiBillet (votre adresse email) reste ouvert, car il
> peut servir sur d'autres lieux. Pour le supprimer aussi, répondez simplement à ce message.
> Conformément au RGPD, vous pouvez à tout moment demander l'accès à vos données, leur
> correction ou leur suppression.
>
> Bien à vous,
> L'équipe de la coopérative TiBillet

*(Mainteneur, 2026-10-07 : gabarit générique `emails/email_generique.html` accepté ; phrase de
mutualisation et lien https://tibillet.coop ajoutés. Plusieurs lieux : paragraphe au pluriel.)*

**Preuve** : tests pytest, puis passage à blanc **et** exécution sur la copie de production
(faits le 2026-10-07, sur une copie **déjà migrée et neutralisée** : 148 supprimés, 0 échec ;
le critère LaBoutik V1 n'y est donc pas éprouvé, la revérification en prod le couvre) ; en R-4,
l'outil tourne aussi **entre `neutraliser` et `migrer`** (base de `main`, comme la nuit) ;
contrôles après : aucun schéma sans `Client` ni l'inverse, lieux restants inchangés, nombre
d'utilisateurs inchangé, durée.

**QO-3 — Le client d'une vente reprise. Tranchée (mainteneur, 2026-10-07)** : il y a toujours
quelqu'un derrière un billet ou une adhésion. Le client est l'utilisateur de la réservation
(`reservation.user_commande`), sinon de l'adhésion (`membership.user`), sinon du paiement Stripe
(`Paiement_stripe.user`).

**QO-12 — 4 lignes à quantité non entière hors QR** (`LE` / `SF`, origine « en ligne » ou
« admin »). **Tranchée (mainteneur, 2026-10-07)** : traitées comme une part QR (argent = `amount`).

**Formes absentes de la production (R-0)** : jetons cadeau `LG`,
paiement Stripe `N`, avoir sur une part QR, ligne `R` positive, avoir daté avant sa vente : la
reprise ne les code pas ; si l'une apparaît, anomalie « forme non prévue » (orchestrateur,
2026-10-07, pour éviter la sur-ingénierie). Un paiement QR en deux monnaies, absent lui aussi, donne **une vente et deux
règlements** : la règle générale (un règlement par moyen) le fait sans code de plus (constat de R-1).

**QO-9 — Les 280 paiements Stripe sans aucune ligne** (R-0, §14 ligne 8). **En partie tranchée.**
- 154 paiements `F` / `W` (paniers abandonnés, réservation sans ligne, aucun argent reçu) et 1
  paiement `Q` / `P` de 2022 : aucune vente, comptés dans le rapport.
- **125 paiements `T` / `V` (« Versement de monnaie globale »)** : le mainteneur (2026-10-07) :
  **ce sont des retours en banque, à garder absolument**, « le même objet que les retours en
  banque de la CLAF ». Enquête (lecture seule, 2026-10-07) :
  - producteur : webhook Stripe `transfer.created` (`ApiBillet/views.py` main ~l.1242-1304,
    branche ~l.1357-1435) ; la plateforme verse des euros au compte **Stripe Connect** du lieu
    pour les jetons **FED** qu'il a reçus ; Fedow écrit une `Transaction` `DEPOSIT` (« Remise en
    banque ») et détruit les jetons FED du lieu ; l'ancien LaBoutik écrit un `ArticleVendu`
    « Stripe TiBillet transfert » (méthode `TR`) ; dans Lespass : un `Paiement_stripe` source `T`,
    statut `V`, sans ligne ni utilisateur, montant seulement dans `metadata_stripe` ;
  - même objet que la remise CLAF **dans Fedow** (`DEPOSIT`, jetons détruits), mais monnaie FED
    (jamais la CLAF), déclencheur automatique ; une remise CLAF ne laisse dans Lespass qu'une
    `FedowTransaction` sans montant ;
  - aujourd'hui (main) : **invisibles en comptabilité** (aucun rapport ne lit `Paiement_stripe`) ;
  - la branche a déjà une forme prévue : article système « virement reçu » (`Product.VIREMENT_RECU`
    `VR`, hors CA, compte de la monnaie : 467000 pour le FED, règlement `TR` au 512000 : fiche E),
    mais **aucun producteur** ne l'écrit (`BankTransferService.enregistrer_virement` non branché).
  **Décision à prendre par le mainteneur** (options, sans choix de l'orchestrateur) :
  A. rien (comme sur `main` : gardés, visibles dans l'admin et la page Fedow, absents des rapports) ;
  B. une vente « virement reçu » par paiement `T` (article `VR` + règlement, à la date du
  transfert, numérotée et chaînée ; exception au « aucun article créé » du §2) ;
  C. pas de vente, une rubrique « versements reçus » du rapport qui lit les `Paiement_stripe` `T` ;
  D. l'avenir seulement : le webhook écrit la vente `VR` après la bascule, l'historique reste en A.
  Points comptables à trancher avec : (1) déjà écrits dans l'ancien LaBoutik : risque de compter
  deux fois ; (2) le 467000 de Lespass n'a presque pas de ventes FED en face (4 lignes `SF`) ;
  (3) compte de trésorerie : `TR` / 512000 ou Stripe / 517100 (l'argent arrive sur Stripe
  Connect) ; (4) numéroter et chaîner des opérations qui ne sont pas des ventes ; (5) la CLAF :
  Lespass n'a pas le montant de ses remises (il faudrait un appel à Fedow, interdit pendant la
  reprise).

**QO-9, 125 paiements `T` : tranchée (mainteneur, 2026-10-07) → option B.** Une vente « virement
reçu » par paiement `T` : article `VR` hors chiffre d'affaires, à la date du transfert, numérotée et
chaînée, montant lu dans `metadata_stripe` (aucun appel à Stripe), `Paiement_stripe.vente` posé.
Raison du mainteneur : avec A, une fois l'ancien Fedow et les LaBoutik V1 arrêtés, il ne resterait
aucune trace lisible. Le doublon avec l'ancien LaBoutik disparaît avec lui. Conséquence connue :
le compte de la monnaie FED de Lespass est déséquilibré sur l'historique (les ventes FED ont surtout
eu lieu dans l'ancien LaBoutik). **Remises de la CLAF : à traiter dans la session suivante** (les
montants sont dans la base de l'ancien Fedow, pas dans celle de Lespass).

**Règlement des ventes `VR` des paiements `T` : `SN` (Stripe en ligne, 517100), relié au paiement
`T` (mainteneur, 2026-10-07).** L'argent arrive sur le compte Stripe Connect du lieu, comme ses
ventes en ligne. L'article `VR` porte la monnaie FED (`ligne.asset`), pour son compte (467000,
fiche E). Rappel : les paiements `T` sont de la **FED** via Stripe (`transfer.created`, Fedow
`global_asset_bank_stripe_deposit`, jetons `STRIPE_FED_FIAT`), jamais un token local. Date : le
`created` du transfert, lu dans `metadata_stripe` (texte JSON) ; `order_date` est en `auto_now_add`,
il porte l'heure de réception du webhook.

**QO-10 — 8 recharges `TNF` offertes à montant non nul (R-0 §14 ligne 16) : règle du §6, sans
question** (orchestrateur, 2026-10-07) : part offerte = total, règlement FREE, unité EUR (monnaie
cadeau ni temps ni points), comme le producteur d'aujourd'hui (`api_v2/views.py` ~l.1040,
`offert_en_totalite=True`).

**Remises en banque de la CLAF : hors du chantier R (mainteneur, 2026-10-07).** Leurs montants ne
sont que dans l'ancien Fedow (transactions `DEPOSIT`, `../Fedow/fedow_core/views.py` ~l.441) ;
Lespass n'en garde qu'une `FedowTransaction` sans montant. La reprise ne les traite pas : une
commande à part, **après la production**, écrira leurs ventes « virement reçu » historiques
(`TODO/BUGS-constats-chantier-05.md` n°35, avec l'absence de producteur `VR` après la bascule).

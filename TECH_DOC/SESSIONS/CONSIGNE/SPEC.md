# SPEC — Consigne et retour de consigne au POS V2, et ventilation du chèque

**Date :** 2026-09-07
**Statut :** validée en brainstorming, corrigée après relecture adverse
**Migration :** Oui — `laboutik.ClotureCaisse.total_cheque`

---

## 1. Objectif

Rendre la consigne réellement utilisable au point de vente V2, à parité avec la V1,
et réparer la ventilation comptable du chèque, qui perd de l'argent en silence.

Deux sujets qui n'ont l'air liés que par hasard, mais qui partagent la même cause :
un moyen d'encaissement câblé jusqu'à la vente, puis oublié par la chaîne comptable.

---

## 2. Ce qui existe aujourd'hui — le constat

### 2.1 La consigne V2 ne peut pas se déclencher

`laboutik/views.py:152` détecte la consigne par un UUID en dur :

```python
UUID_ARTICLE_CONSIGNE = "8f08b90d-d3f0-49da-9dbd-8be795f689ef"
```

- Cet UUID **ne correspond à aucun produit** — vérifié sur les 15 tenants non-public
  de la base de dev : zéro produit portant cet UUID, zéro produit `methode_caisse=CR`,
  zéro prix négatif.
- Il n'apparaît **nulle part ailleurs** dans le dépôt (ni fixture, ni migration, ni
  données de démo), et **pas non plus dans la V1**. C'est un vestige recopié.
- Pendant ce temps `Product.RETOUR_CONSIGNE = "CR"` existe
  (`BaseBillet/models.py:1315`) et **n'est utilisé nulle part**, là où son voisin
  `VIDER_CARTE` a son service (`BaseBillet/services_refund.py`) et ses tests.

Effet du drapeau quand il se lèverait : `abs()` sur le total dans `moyens_paiement()`
(l. 5706) et `payer()` (l. 5843-5844), et `deposit_is_present` passé aux deux
templates. Le crédit de la carte n'existe pas.

**Et le flux NFC ferait pire que rien.** Un produit `CR` à prix négatif posé dans un
panier NFC *avant* que le flux soit câblé tombe dans la branche « articles
fiduciaires » de `_payer_par_nfc` : le montant négatif rend `reste_article <= 0`, la
boucle `break` immédiatement, et l'on obtient **zéro ligne, zéro débit, et un écran de
succès**. Un retour de consigne qui « réussit » sans rien écrire.
→ Contrainte d'ordre, voir §9.

### 2.2 Le chèque disparaît de la ventilation stockée

L'encaissement fonctionne : `"CH"` → `PaymentMethod.CHEQUE`
(`MAPPING_CODES_PAIEMENT`, l. 3697), et `reports.py:224` calcule `total_cheque` et
l'ajoute à `total_general` (l. 246).

Mais `laboutik.ClotureCaisse` ne porte que `total_especes`, `total_carte_bancaire`,
`total_cashless`, `total_general`. En cascade :

| Lecteur | Ce qu'il fait du chèque |
|---|---|
| `archivage.py:236` | **`total_cheque = '0'` en dur** — l'archive fiscale LNE est fausse |
| `csv_export.py:61-63` | ne l'écrit pas |
| `pdf.py:56-58` | ne l'écrit pas |
| `ventilation.py:103` → `fec.py` | **correct** — lit `rapport_json` |
| `excel_export.py:123` | **correct** — lit `rapport_json` |
| `printing/formatters.py:443` | **correct** — ticket Z imprimé |

`archivage.py:37` déclare pourtant `total_cheque` dans `COLONNES_CLOTURES` :
l'intention était là, la donnée n'a jamais suivi. Dès qu'un chèque est encaissé,
`especes + cb + cashless ≠ total_general` dans la clôture stockée.

Les trois lecteurs déjà corrects sont à **ne pas toucher**.

---

## 3. Le mécanisme V1 de référence

Lu dans `/home/jonas/TiBillet/dev/LaBoutik`.

**Deux produits distincts** (`administration/management/commands/install.py:305-318`) :

| Article | Prix | Méthode | Rôle |
|---|---|---|---|
| `Consigne` | **+1 €** | `VENTE` | on encaisse la consigne — vente ordinaire |
| `Retour Consigne` | **−1 €** | `RETOUR_CONSIGNE` | on la rembourse |

**Front** (`webview/static/webview/js/points_ventes.js:128-133`) :
`RetourConsigne` → `moyens_paiement: 'espece|nfc'`, `groupe: 'groupe2'` — un groupe
distinct de la vente, donc non mélangeable. La détection (`depositIsPresent`,
l. 1423) cherche `methode_name === 'RetourConsigne'` : **par méthode, jamais par
UUID**.

**Backend** (`webview/views.py:1511`, `methode_CR`) :

```python
total = round((article.prix * qty), 2)          # négatif
if self.moyen_paiement.categorie != MoyenPaiement.LOCAL_EURO:
    self._to_db_cash_cb(article, qty)            # espèces/CB : ligne comptable seule
elif self.moyen_paiement.categorie == MoyenPaiement.LOCAL_EURO:
    fedowApi.transaction.refill_wallet(amount=int(abs(total) * 100), ...)
    ArticleVendu.objects.create(prix=article.prix, ...)   # prix NÉGATIF conservé
```

Le point qui compte : **en cashless, un retour de consigne est une RECHARGE**, et la
ligne comptable garde le montant négatif. `_total_vente_article` (l. 880) exclut
d'ailleurs `RETOUR_CONSIGNE` du total à débiter : un retour ne se soustrait pas d'un
achat, il suit son propre chemin.

**Compta** (`administration/ticketZ_V4.py:322-350`) : ventilé sur `LOCAL_EURO` et
`CASH` uniquement, `"N/A"` explicite pour CB, chèque et Stripe.

---

## 4. Décisions de design

D1–D4 tranchées par le mainteneur (brainstorming 2026-09-07) ; D5–D10 en découlent.

| # | Décision | Raison |
|---|---|---|
| D1 | **Espèces + NFC**, comme la V1 | Le template propose déjà les deux boutons. N'en coder qu'un laisserait un bouton qui ment au caissier. |
| D2 | **Colonne `total_cheque`** sur `laboutik.ClotureCaisse` + migration | Corrige l'archive LNE, le CSV et le PDF, et rétablit `especes + cb + cashless + cheque = total_general`. |
| D3 | **Refus côté serveur** d'un retour de consigne payé en CB ou chèque | La V1 ne filtre qu'au front ; un POST forgé y passe. |
| D4 | Le double webhook Stripe part en **chantier séparé** | Voir §10. |
| D5 | Détection par **`methode_caisse == Product.RETOUR_CONSIGNE`**, `UUID_ARTICLE_CONSIGNE` **supprimée** | Une constante qui ne matche rien donne l'illusion d'une fonctionnalité couverte. |
| D6 | L'asset à créditer vient de **`Product.asset`** (jamais `Price.asset`), et sa catégorie doit être **TLF** | Même mécanique que `_executer_recharges`. Voir §4.2. |
| D7 | **Un panier de retour de consigne ne se mélange pas** à d'autres articles | Voir §4.1. |
| D8 | Le crédit Fedow va **DANS** le bloc `atomic()`, avec la `LigneArticle` | Voir §4.3 — la décision la plus importante du chantier. |
| D9 | Un article `RETOUR_CONSIGNE` **ne touche pas au stock** : ni validation amont, ni décrémentation | Voir §4.4. |
| D10 | **Pas de backfill** des clôtures existantes | Voir §5.1 — avec la vraie raison, pas une fausse. |
| D11 | Un panier de retours portant **plusieurs monnaies** est refusé | Le crédit vise UN asset pour le total du panier : deux monnaies rendraient au client une monnaie qu'il n'a pas avancée. Deux monnaies = deux opérations. |

### 4.1 Pourquoi le panier mixte est refusé (D7)

`payer()` fait `total_en_euros = abs(total_en_euros)` **dès qu'une consigne est
présente**. Sur un panier mixte — deux bières à 3 € et un retour de consigne à −1 € —
le total vaut 5 €, `abs()` le laisse à 5 €, et l'écran bascule pourtant en mode
« Rembourser la consigne » : le caissier lirait « À rembourser : 5 € » alors que le
client lui doit 5 €. L'`abs()` n'a de sens que sur un panier entièrement négatif.

La V1 évite le problème par ses groupes front, c'est-à-dire par une convention que
rien ne fait respecter côté serveur.

**Ce que ça impose au comptoir :** un client qui rend deux gobelets *et* reprend deux
bières fait deux opérations successives — le retour (−2 €), puis la vente. C'est déjà
le geste imposé par la V1. En revanche `qty > 1` sur une ligne de retour reste
autorisé : 2 × −1 € = −2 € en une seule ligne.

### 4.2 L'asset du retour (D6)

`_extraire_articles_du_panier` ne retient que les `Price` avec `asset__isnull=True`
(`views.py:3826-3830`) : un gestionnaire qui poserait l'asset sur le **Price** verrait
son produit ignoré en silence, avec le message trompeur « n'a pas de prix EUR
publié ». L'asset se pose donc sur le **`Product`**, et nulle part ailleurs.

Sa catégorie doit être **TLF** (monnaie locale fiduciaire). Un asset cadeau (TNF)
produirait un crédit en cadeau tout en étiquetant la ligne `LOCAL_EURO` : le total
cashless resterait juste (LE et LG y sont confondus, `reports.py:216-220`) mais le
détail par asset mentirait.

Asset absent ou de mauvaise catégorie → **refus explicite** en 400 dans `payer()`,
jamais de repli silencieux.

**Limite connue :** `_determiner_moyens_paiement` ne regarde que `methode_caisse`, jamais
l'asset. CASHLESS reste donc proposé sur un produit mal configuré, et le refus n'arrive
qu'après que le client a présenté sa carte. C'est une gêne, pas une faute comptable :
rien n'est écrit, rien n'est crédité. Filtrer aussi à l'affichage est une amélioration
identifiée, non faite.

### 4.3 Le crédit va dans l'atomic (D8)

`TransactionService.creer_recharge` (`fedow_core/services.py:909`) **n'est pas un
appel réseau** : `fedow_core/services.py` n'importe ni `requests`, ni `httpx`, ni
`FedowAPI`. C'est une écriture DB dans le schéma du tenant.

C'est pourquoi `_executer_recharges` est appelée **à l'intérieur** de
`with db_transaction.atomic():` à ses cinq sites d'appel (l. 6045, 6269, 6813, 7252,
7773), et sa docstring l'exige (l. 5478).

Le retour de consigne suit la même règle : **crédit et `LigneArticle` dans le même
`atomic()`**. Les sortir serait fabriquer le cas « argent crédité, ligne comptable en
échec » — de la monnaie créée sans trace comptable.

Ce qui reste hors atomic, comme aujourd'hui, c'est la **résolution du wallet**
(`_obtenir_ou_creer_wallet`, qui peut interroger Fedow par le réseau), déjà faite en
amont dans `_payer_par_nfc`.

### 4.4 Le stock ne bouge pas (D9)

`StockService.decrementer_pour_vente` (`inventaire/services.py:29`) le dit
lui-même : « Ici on décrémente **toujours** ». Un produit « Retour Consigne » associé
à un `Stock` (des gobelets, typiquement) serait donc **décrémenté au moment où le
gobelet revient**, et `_valider_stock_panier` (`views.py:4106`) **bloquerait** le
retour dès que le stock atteint zéro : le client ne pourrait plus récupérer sa
consigne.

Un article `RETOUR_CONSIGNE` est donc exclu des deux mécanismes.

L'incrément de stock au retour (le gobelet rentre vraiment) relève de la gestion de
parc et **n'est pas dans ce chantier** : ne pas décrémenter est le comportement
neutre et sûr. À confirmer au moment du plan.

---

## 5. Modèle de données

### 5.1 Migration — `laboutik.ClotureCaisse.total_cheque`

Le modèle visé est bien `laboutik.ClotureCaisse` — pas `comptabilite.ClotureCaisse`
(`comptabilite/models.py:20`), qui couvre les ventes web et n'a pas de détail par
moyen. Ce second modèle est hors périmètre.

```python
total_cheque = models.IntegerField(
    default=0,
    verbose_name=_("Total chèque (centimes)"),
    help_text=_("Total check amount in cents."),
)
```

**Pas de backfill (D10), et voici la vraie raison.** Le montant chèque des clôtures
déjà écrites **existe** : il est dans `rapport_json['totaux_par_moyen']['cheque']`
(`reports.py:307`), et leur `total_general` l'inclut déjà. Un backfill serait donc
techniquement possible pour les journalières — mais pas pour les clôtures
hebdo/mensuelles/annuelles, dont le `rapport_json` n'est qu'un résumé
(`tasks.py:784-788`) et qu'il faudrait re-sommer.

On s'en passe parce que **la V2 n'est pas en production** : l'historique de dev n'a
aucune valeur comptable. Si une instance venait à avoir des clôtures réelles avec des
chèques, un backfill depuis `rapport_json` serait **nécessaire** — et son ré-export
LNE produirait un ZIP au hash différent, ce qui devra être mentionné au CHANGELOG.

### 5.2 Aucune migration pour les produits

Les produits `Consigne` et `Retour Consigne` sont des **données** : un gestionnaire
les crée dans l'admin. Une migration de données les imposerait à tous les tenants, y
compris ceux qui ne pratiquent pas la consigne.

Ils sont ajoutés aux **données de démo**
(`laboutik/management/commands/create_test_pos_data.py`) :

| Produit | `categorie_article` | `methode_caisse` | Prix | `Product.asset` | Catégorie POS | Stock |
|---|---|---|---|---|---|---|
| Consigne | `VENTE` | `VENTE` | +1,00 € | — | sans TVA | aucun |
| Retour Consigne | `VENTE` | `RETOUR_CONSIGNE` | **−1,00 €** | asset **TLF** local | sans TVA | aucun |

**La catégorie doit être sans TVA**, et ce n'est pas cosmétique :
`LigneArticle.save()` (`BaseBillet/models.py:3543-3554`) force `vat` depuis la
catégorie quand il vaut 0. Une catégorie taxée produirait une TVA négative et une
écriture FEC négative (`ventilation.py:191`). La consigne n'est pas un produit taxé :
c'est un dépôt de garantie.

`Price.prix` est un `DecimalField(max_digits=6, decimal_places=2)` sans validator de
minimum, et le `clean_prix` de l'admin (`Administration/admin/prices.py:148`)
n'interdit que la plage `0 < prix < 1` : **−1 € passe**. Vérifié.

---

## 6. Les flux

### 6.1 Détection — un helper, deux appelants

```python
def _panier_contient_retour_consigne(articles_panier):
    """Vrai si le panier porte au moins un article de retour de consigne."""
```

Posé à côté de `_panier_contient_recharges_payantes` (l. 1485), même forme. Les deux
appelants ont déjà `articles_panier` sous la main : `moyens_paiement()` (défini
l. 5604, articles extraits l. 5637) et `payer()` (défini l. 5768, articles extraits
l. 5822). Les deux appels à `payment_method.extraire_uuids_articles(request.POST)`
disparaissent avec la constante — ce sont ses deux seuls usages
(`laboutik/utils/method.py:6`).

### 6.2 `_determiner_moyens_paiement` — et le template qui doit suivre

Sur un panier de retour de consigne, les moyens se réduisent à `nfc` et `espece` —
`espece` restant soumis à `point_de_vente.accepte_especes`. Ni `carte_bancaire`, ni
`CH`.

**Le template doit être aligné.** Aujourd'hui `hx_display_type_payment.html:92`
affiche le bouton ESPÈCE **inconditionnellement** en mode consigne, alors que
CASHLESS est bien gardé par `'nfc' in moyens_paiement` (l. 88). Sans correction, un
PV qui refuse les espèces afficherait quand même le bouton. Le fichier est ajouté
en §11.

### 6.3 `payer()` — les deux gardes

1. **Panier mixte** (D7) → 400, `hx_messages.html`.
2. **Moyen interdit** (D3) : `carte_bancaire` ou `CH` sur un panier consigne → 400.

Les deux tombent **avant** l'aiguillage (l. 5851-5895), donc avant toute écriture.
C'est nécessaire parce que `payer()` ne confronte jamais le moyen posté à
`_determiner_moyens_paiement` : le filtrage des moyens est un confort d'affichage, la
garde est la seule vraie protection.

### 6.4 Espèces — rien de spécial, et c'est voulu

`_creer_lignes_articles` crée la ligne avec `amount` négatif et
`payment_method=CASH`. `_payer_en_especes` calcule
`somme_est_suffisante = (given_sum == 0 or given_sum >= total_centimes)`
(l. 6166-6168) : le caissier ne saisit rien pour un remboursement, donc la branche
passe. Le template affiche « A rembourser : X € ».

**Le fond de caisse se règle tout seul.** `calculer_solde_caisse` (`reports.py:504`)
somme les lignes `CASH` via `montant_ttc_centimes()` =
`Cast(Round(Sum(F("amount") * F("qty"))))` — **sans `abs()`, sans filtre de signe**
(`reports.py:37-52`). Une ligne négative se soustrait donc du tiroir. La V1 avait
besoin d'un poste dédié (`return_consign_cash`) ; la V2 n'en a pas besoin.
**Ne pas en ajouter un.**

### 6.5 NFC — le cœur du chantier

Le retour de consigne ne passe **pas** par `_payer_par_nfc`, qui reste intact : il a sa
propre méthode, `_rembourser_consigne_par_nfc`, appelée directement depuis `payer()`.
Entrer dans la cascade de débit n'aurait rien donné — sur un montant négatif elle
`break` au premier tour sans rien écrire (§2.1) — et alourdir une fonction de 760 lignes
pour l'opération inverse de ce qu'elle fait n'aurait aidé personne.

Dans le même `with db_transaction.atomic():` (D8), et dans cet ordre :

```python
TransactionService.creer_recharge(
    sender_wallet=asset.wallet_origin,
    receiver_wallet=wallet_du_client,
    asset=asset,                        # Product.asset, catégorie TLF (D6)
    montant_en_centimes=abs(total_centimes),
    tenant=tenant_courant,
    ip=ip_client,
)
_creer_lignes_articles(
    articles_du_retour,
    "nfc",
    asset_uuid=asset.uuid,
    carte=carte_client,
    wallet=wallet_client,
    point_de_vente=point_de_vente,
)
```

La `LigneArticle` garde le montant **négatif**, avec `carte`, `wallet` et `asset`
renseignés et `payment_method=LOCAL_EURO`. Ce signe négatif est ce qui fait que le
retour se soustrait du CA cashless dans tous les rapports, sans une ligne de code de
plus.

La résolution du wallet reste **hors** atomic, là où elle est déjà.

---

## 7. Comptabilité

### 7.1 Chèque — remplir la colonne aux TROIS sites de clôture

`reports.py` n'a **rien** à changer : il calcule déjà `total_cheque` et l'inclut dans
`total_general`. Ce sont les écritures de `ClotureCaisse` qui l'ignorent, et il y en
a trois, pas une :

| Site | Nature | Changement |
|---|---|---|
| `laboutik/views.py:2041` | clôture **manuelle** depuis le POS — le chemin le plus courant | extraire `totaux["cheque"]` (l. 1993-1996) et le passer au `create()` |
| `laboutik/tasks.py:489` | journalière automatique | `total_cheque=totaux['cheque']` |
| `laboutik/tasks.py:774` | agrégats hebdo / mensuel / annuel | ajouter `Sum('total_cheque')` (l. 755-758), sinon ces clôtures resteront à 0 |
| `create_test_pos_data.py:1654` | données de démo | cohérence |

Sans les deux premiers, D2 est faux pour le chemin le plus emprunté.

Puis les lecteurs à réparer : `archivage.py:236` (supprimer le `'0'` en dur),
`csv_export.py:62`, `pdf.py:57` + son template.

### 7.2 Retour de consigne — ce qui marche déjà

Rien à ajouter dans `reports.py` : les montants négatifs se soustraient naturellement
(`total_especes`, `total_cashless`, `total_general`, solde de caisse), conséquence de
`Sum(amount × qty)` sans valeur absolue.

**Non couvert :** aucun test ne vérifie `calculer_solde_caisse` sur une ligne négative.
Le raisonnement (`Sum(amount × qty)` sans `abs()`) est vérifié dans le code, pas exercé
par un test. À écrire.

**Deux points à prouver par un test, pas à supposer :**
- `calculer_tva` (`reports.py:461`) sur une ligne négative — d'où la catégorie sans
  TVA en §5.2 ;
- la chaîne d'intégrité LNE : `calculer_hmac` (`integrity.py:28`) sérialise un
  `amount` signé et `calculer_total_ht` (l. 167) tolère le négatif. `verifier_chaine`
  doit être vue passer sur une ligne négative.

`hash_lignes` (`reports.py:1042`) porte sur `uuid|amount|status` : la nouvelle colonne
ne l'affecte pas. Le HMAC d'archive est calculé **à l'export** et embarqué dans le ZIP
(`archivage.py:529-556`), sans hash stocké en base : la migration ne casse
l'inaltérabilité d'aucune archive déjà produite.

---

## 8. Tests

Tous en **pytest DB-only** (`tests/pytest/`) : rien ici n'a besoin d'un navigateur.
Modèle : `tests/pytest/test_pos_adhesion_fusion_wallet_fedow.py` (`FastTenantTestCase`
+ `TenantClient` + POST `/laboutik/paiement/payer/`).

**Pas de mock `FedowAPI` pour le crédit** : `creer_recharge` est local (§4.3). Le seul
point réseau du flux est `_obtenir_ou_creer_wallet` sur une carte sans user ni wallet
éphémère — c'est **là** et nulle part ailleurs qu'un `create_autospec` se justifie.

**`test_pos_retour_consigne.py`**

1. Retour en espèces → une `LigneArticle` à montant **négatif**, `payment_method=CASH`.
2. Le solde de caisse **baisse** du montant du retour.
3. Retour en NFC → le wallet du porteur est **crédité** du montant absolu, et la ligne
   reste négative.
4. Retour en NFC sur une **carte anonyme** (wallet éphémère) → créditée aussi.
5. `qty = 2` → une ligne à −200, et 2 € crédités.
6. `moyens_paiement` sur panier consigne ne propose que `nfc` et `espece`.
7. Idem avec `accepte_especes=False` → `espece` absent (le template suit, §6.2).
8. Retour posté en `carte_bancaire` → **400**, **aucune** `LigneArticle` (D3).
9. Retour posté en `CH` → 400, aucune ligne (D3).
10. Panier mixte (vente + retour) → 400, aucune ligne (D7).
11. Produit `CR` sans `Product.asset` payé en NFC → refus, aucun crédit, aucune ligne (D6).
12. Produit `CR` avec un asset **TNF** → refus (D6).
13. Produit `CR` **avec un Stock** → le stock n'est **pas** décrémenté, et le retour
    n'est **pas** bloqué à stock zéro (D9).
14. `verifier_chaine` (LNE) passe sur une ligne négative.

**`test_pos_paiement_cheque.py`**

15. Vente payée par chèque → ligne `payment_method=CHEQUE`.
16. `moyens_paiement` propose `CH` si et seulement si `accepte_cheque`.

**`test_rapports_cheque.py`** — le cœur de « tester les rapports comptables avec les
chèques »

17. `calculer_totaux_par_moyen` isole le chèque et l'inclut dans `total_general`.
18. **Clôture manuelle** (`views.py:2041`) → `total_cheque` stocké.
19. **Clôture journalière auto** (`tasks.py:489`) → `total_cheque` stocké.
20. **Clôture hebdo** (`tasks.py:774`) → `total_cheque` agrégé sur les journalières.
21. `especes + cb + cashless + cheque == total_general`.
22. L'**archivage LNE** exporte le vrai `total_cheque`, pas `0` — le test qui aurait
    attrapé le bug d'origine.
23. CSV et PDF de clôture montrent la ligne chèque.
24. Clôture **sans aucun chèque** → `total_cheque = 0` (pas de régression).

**Validation par mutation : 16 mutations.** Chacune casse volontairement un point précis
du correctif et fait tomber **exactement** le ou les tests qui le surveillent.

Cela ne signifie pas que chacun des 30 tests a sa propre mutation : quelques-uns
documentent un comportement déjà correct (la ligne négative en espèces, le solde de
caisse qui baisse de lui-même, la chaîne LNE sur un montant négatif) et servent de
garde-fous contre une régression future.

---

## 9. Ordre d'implémentation

L'ordre n'est pas indifférent (§2.1) : **le flux NFC doit être câblé AVANT que les
produits de démo existent**. Un produit `CR` présent dans un panier NFC non câblé
produit un écran de succès sans aucune écriture — un faux vert qui donnerait
l'illusion que la fonctionnalité marche.

1. Helper de détection + suppression de `UUID_ARTICLE_CONSIGNE` + gardes de `payer()`
2. Flux espèces (le plus simple, valide la ligne négative de bout en bout)
3. Flux NFC (crédit dans l'atomic)
4. Stock (D9)
5. Colonne `total_cheque` + les trois sites de clôture + les lecteurs
6. Données de démo **en dernier**

---

## 10. Hors périmètre

- **Double webhook Stripe** (D4). Diagnostiqué le 2026-09-07 : deux `stripe listen`
  livraient le même `evt_`, les deux franchissaient
  `if invoice != last_stripe_invoice` (`ApiBillet/views.py:1409`), chacun créant son
  `Paiement_stripe` et sa `LigneArticle` (294 µs d'écart, deux uuid distincts). La
  garde n'est pas atomique et Stripe livre en *at-least-once*. Correctif à instruire :
  `select_for_update` sur le `Membership`, ou contrainte d'unicité
  `(membership, last_stripe_invoice)`. À surveiller : le serveur ASGI s'est figé peu
  après ce double traitement — lien non établi.
- **Cashback et fidélité.** `Product.FIDELITE = "FD"` déclaré et jamais utilisé ; la
  V1 a un `methode_HB` (deux lignes : CB positive, espèces négative). Non testé des
  deux côtés.
- **Incrément de stock au retour** (§4.4), **consigne au paiement fractionné**,
  **retour depuis le parcours web** : la V1 ne les fait pas non plus.
- **`comptabilite.ClotureCaisse`** (ventes web) : pas de détail par moyen, non concerné.

---

## 11. Fichiers touchés

| Fichier | Nature |
|---|---|
| `laboutik/views.py` | `- UUID_ARTICLE_CONSIGNE` ; `+ _panier_contient_retour_consigne` et `_panier_est_uniquement_retour_consigne` ; `_determiner_moyens_paiement` ; deux gardes dans `payer()` ; `+ _rembourser_consigne_par_nfc` (méthode dédiée) et `_refuser_le_retour_de_consigne` ; garde dans `payer_commande` ; exclusion stock ; `+ totaux["cheque"]` à la clôture manuelle et à son écran |
| `laboutik/printing/formatters.py` | ligne « Chèque » sur le ticket Z |
| `laboutik/templates/laboutik/partial/hx_cloture_rapport.html` | ligne « Chèque » sur l'écran de clôture |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | bouton ESPÈCE conditionné (§6.2) |
| `laboutik/models.py` | `+ ClotureCaisse.total_cheque` |
| `laboutik/migrations/00XX_…` | `AddField` |
| `laboutik/tasks.py` | journalière (l. 489) + agrégats `Sum('total_cheque')` (l. 755-758, 774) |
| `laboutik/archivage.py` | supprime le `'0'` en dur (l. 236) |
| `laboutik/csv_export.py`, `laboutik/pdf.py` + template PDF | ligne chèque |
| `laboutik/management/commands/create_test_pos_data.py` | produits de démo, **en dernier** |
| `tests/pytest/test_pos_retour_consigne.py` | neuf |
| `tests/pytest/test_pos_paiement_cheque.py` | neuf |
| `tests/pytest/test_rapports_cheque.py` | neuf |
| `CHANGELOG/2026-09-07-consigne-et-ventilation-cheque.md` | neuf |

**i18n :** ce chantier ajoute des chaînes traduisibles (messages de refus, libellé
« Chèque » des exports). Les `_()` sont écrits en **français** ; le workflow
`makemessages` est lancé **par le mainteneur**, jamais par l'assistant.

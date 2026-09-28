# Chantier 04-E — Vente en points / temps à la caisse (`NM`)

> **Statut** : ✅ LIVRÉE (2026-09-28) — voir `CHANGELOG/2026-09-28-melanges-argent-E-vente-en-points.md` (décisions et écarts)
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décisions : D1 à D5, D7, D8, D11 à D17, D28 — Dépend de : D (`MOYENS_HORS_ARGENT`)
> Effort estimé : 5 à 6 j (4 sessions, §8)

---

## 1. La situation aujourd'hui, simplement

Un lieu peut donner à ses clients des **points de fidélité** (monnaie FID) ou des
**heures** (monnaie temps TIM, par exemple pour le bénévolat). Ces monnaies ne sont
pas de l'argent.

Dans l'admin, un tarif de caisse peut déjà être exprimé dans ces monnaies : case
« Tarif non fiduciaire » + choix de la monnaie (`Administration/admin/products.py`,
`POSPriceInline`, ~l.619-675 ; le menu ne propose que TIM et FID actifs du lieu).
Le champ `prix` est alors un nombre d'unités (300,00 = 300 points). **N'importe quel
produit de caisse** peut recevoir un tel tarif.

**Mais la caisse ne vend pas ces tarifs** :

- les tuiles ne chargent que les tarifs sans monnaie
  (`laboutik/views.py` `_construire_donnees_articles`, ~l.532-540 :
  `asset__isnull=True`) ; un produit sans tarif en euros est ignoré (~l.578) ;
- le panier applique le même filtre (`_extraire_articles_du_panier`, ~l.4430) : un
  tarif en points envoyé de force est **ignoré sans message** (`continue`,
  ~l.4540-4547).

Le code qui encaisse des points existe (`articles_non_fiduciaires` dans
`_payer_par_nfc` et `_executer_paiement_complementaire`) mais n'est jamais appelé.
S'il l'était, il enregistrerait la vente **en euros** : FID est mappé sur
`LOCAL_EURO` et TIM retombe sur `LOCAL_EURO` par défaut
(`MAPPING_ASSET_CATEGORY_PAYMENT_METHOD`, ~l.4161).

**Unité** (D16) : la caisse compte les points en **centièmes**, comme les euros
(`int(round(prix × 100))`, ~l.578 ; soldes affichés `value / 100`, ~l.1250). Un
Pin's à 300,00 points coûte 30000 unités. L'API v2 crédite, elle, l'unité brute :
fiche à part, hors chantier.

Données de démo (`laboutik/management/commands/create_test_pos_data.py`
~l.770-831) : « Pin's TiBillet » 300 points (FID), « Machine 3D » 1 heure (TIM),
« Bière » tarif « Bénévole » 1 heure (TIM) en plus de son tarif 5 €. La Bière est
vendue dans 4 points de vente (Bar, Terrasse, Mix, Accueil Festival) ; ses deux
tarifs ont le même `order` (100). Les tests créent leurs propres produits (ne pas
dépendre de la démo).

## 2. Les règles métier (décisions du mainteneur)

1. Les tarifs en points / temps deviennent **vendables à la caisse**, sur les
   **articles de vente** (`methode_caisse = VENTE`) et les **adhésions**. Pas sur
   les recharges ni les billets.
2. **Une seule monnaie par panier** : uniquement des euros, OU uniquement UNE
   monnaie non monétaire. Sinon : « Un panier ne mélange pas plusieurs monnaies :
   encaissez-les séparément. »
3. Un panier en points / temps se paie **uniquement par carte NFC**. Pas d'OFFRIR.
4. Solde insuffisant : **refus simple**, sans 2ᵉ carte. Le solde est comparé à la
   **somme** du panier.
5. **Commandes de table** : tarifs en points refusés.
6. La vente est enregistrée avec **`NM`**, `amount` = prix en unités (centièmes),
   **TVA 0**.
7. Les tarifs en **euros passent d'abord** dans l'ordre des tarifs.
8. Le Z et le ticket X ont une section **« Non monétaire »**, une ligne **par nom
   de monnaie**.

## 3. Modèle, mapping, admin

```python
# BaseBillet/models.py — class PaymentMethod
NON_MONETAIRE = "NM", _("Points ou temps (non monétaire)")
```

- Migration « choices seulement » : trois `AlterField` BaseBillet (`Ticket` ~l.3292,
  `LigneArticle` ~l.3695, `Membership` ~l.3979). Aucune donnée modifiée. Après la
  migration, migrer ou supprimer les schémas `test_*` des `FastTenantTestCase`
  (skill `tibillet-test`).
- `PaymentMethod.classic()` ne le liste pas. `not_online()` le liste (aucun
  appelant).
- `_compute_default_vat()` : la règle « TVA 0 » de la fiche D inclut `NON_MONETAIRE`.
- `laboutik/reports.py` : `MOYENS_HORS_ARGENT = [FREE, NON_MONETAIRE]`.
- `LABELS_MOYENS_PAIEMENT_DB` (`laboutik/views.py` ~l.144) : entrée `NM`.
- **Admin** (`POSPriceInline`) : validation du formulaire — un tarif non
  fiduciaire n'est accepté que sur un produit de vente ou une adhésion, sinon
  « Un tarif en points n'est possible que sur un article de vente ou une adhésion. »

```python
# laboutik/views.py
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,
    Asset.TLF: PaymentMethod.LOCAL_EURO,
    Asset.FED: PaymentMethod.STRIPE_FED,
    Asset.TIM: PaymentMethod.NON_MONETAIRE,
    Asset.FID: PaymentMethod.NON_MONETAIRE,
}
```

**Plus de repli sur les euros (D12)** : les 7 appels `.get(category, LOCAL_EURO)`
(`laboutik/views.py` ~l.7699, 7931, 8767, 8969, 9275, 9523 ; `controlvanne/billing.py`
~l.320) deviennent `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD[category]`. Le refus propre
se fait **avant** : à la classification des articles (phase 2 de `_payer_par_nfc`),
un tarif dont la monnaie n'est pas dans le mapping est refusé avec `hx_messages`,
avant tout débit. Les 7 accès directs ne peuvent donc plus lever en pratique (les
assets de la cascade sont toujours TNF/TLF/FED). Un `KeyError` restant serait un
bug de code, visible en dev.

## 4. La caisse

### 4.1 Tuiles et panier : voir les tarifs en points

Seules **deux** requêtes changent : `_construire_donnees_articles` (~l.532-540) et
`_extraire_articles_du_panier` (~l.4430-4438).

```python
# Tarifs vendables a la caisse : en euros, OU en points/temps (monnaie TIM/FID
# active et non archivee) sur un article de vente ou une adhesion. Les tokens
# fiduciaires (TLF/TNF/FED) ne sont jamais un prix : ils passent par la cascade.
# Les euros d'abord : le premier tarif sert de tarif par defaut (tuile, ancien
# format de panier sans price_uuid).
# / POS-sellable prices: euros, OR points/time. Euros first (default price).
queryset=Price.objects.filter(
    Q(asset__isnull=True)
    | Q(non_fiduciaire=True,
        asset__category__in=[Asset.TIM, Asset.FID],
        asset__active=True, asset__archive=False),
    publish=True, recurring_payment=False, manual_validation=False,
).order_by(F("asset").asc(nulls_first=True), "order")
```

Le produit doit être une vente ou une adhésion : un tarif en points posé sur un
autre produit (avant la validation admin) est ignoré par la boucle de construction.

On **garde le nom** `prix_euros` (le renommer toucherait une vingtaine de lignes et
une clé homonyme de `hx_card_recharge.html`) et on corrige son commentaire. Les
autres filtres `asset__isnull=True` restent en euros, volontairement : billetterie
(~l.461-463, ~l.4477, ~l.4493), recharges (~l.1594-1597, ~l.1680, ~l.1710-1716).

Le tri « euros d'abord » garantit que `prix_euros[0]` reste le tarif en euros
(prix de la tuile ~l.580, ancien format ~l.4551, `test_pos_views_data.py:788`).

### 4.2 Une seule monnaie par panier (garde serveur)

```python
def _monnaie_du_panier(articles_panier):
    """
    Renvoie la monnaie non monetaire du panier (Asset), ou None pour un panier
    en euros. Leve ValueError si le panier melange plusieurs monnaies.
    / Returns the cart's non-monetary asset, or None for a euro cart.
      Raises ValueError if the cart mixes currencies.
    """
```

Rendu d'erreur standard `hx_messages.html`, comme le panier de consigne mixte
(~l.6672-6718).

| Appel | Pourquoi |
|---|---|
| vue `moyens_paiement` (~l.6376) | le caissier voit le refus dès « VALIDER » |
| `_executer_paiement` (~l.6586, avant l'aiguillage ~l.6740-6760) | **garde réelle** : `payer()` ne confronte jamais le moyen reçu à la liste proposée (~l.6697) |

### 4.3 NFC uniquement (garde serveur)

- `_determiner_moyens_paiement` (~l.4801) : panier en points → `return ["nfc"]`.
  La tuile OFFRIR n'est pas rendue.
- `_executer_paiement` : panier en points **et** moyen ≠ `nfc` → refus.

**Garde la plus importante de la fiche.** Sans elle, un POST forgé « espèces » passe
par `_creer_lignes_articles()` (~l.4941), qui ne lit jamais `price.asset` et ne
débite aucun portefeuille : la ligne est créée en espèces pour 300 €, le stock
baisse, et le client garde ses points.

### 4.4 Paiement NFC

Le chemin existe : classement (`articles_non_fiduciaires`, ~l.7602), débit
(phase 7b, `TransactionService.creer_vente`, ~l.7916-7937), ligne créée par la
cascade avec `amount = prix_centimes` (~l.5329-5333) ; le legacy FED ne s'active
jamais pour ces articles.

À changer :

- **Adhésion payée en points** — aujourd'hui une adhésion est classée **avant** le
  test non fiduciaire (~l.7594-7608) et part dans la cascade euros
  (`articles_pour_cascade = articles_fiduciaires + articles_adhesion`, ~l.7616) : elle
  serait débitée en euros. Nouveau classement : un tarif non fiduciaire va **toujours**
  dans `articles_non_fiduciaires` (débit en points) ; si c'est une adhésion, il est
  **aussi** ajouté à une liste `adhesions_payees_en_points`, parcourue avec
  `articles_adhesion` à la création des adhésions (~l.7977-8023). Il ne passe jamais
  par la cascade euros. Même changement dans `_executer_paiement_complementaire`
  (~l.8724-8743) — qui refuse de toute façon un panier en points (ci-dessous).
- **Vérification du solde sur la somme** (phase 3, ~l.7630-7663) : aujourd'hui
  article par article ; deux articles à 300 points passent avec 500 points, puis le
  débit échoue dans la transaction (`SoldeInsuffisant`, repli ~l.8035). On compare le
  solde à la **somme** du panier.
- **Popup solde insuffisant** (`hx_funds_insufficient.html`) : « Il manque X € »
  (~l.48) devient « Il manque 100 Points fidélité » (`monnaie_name` est déjà
  transmis, ~l.7651) ; le bouton **2ᵉ carte** (~l.87-91, inconditionnel) n'est pas
  rendu pour un panier en points.
- `_executer_paiement_complementaire` refuse un panier en points (POST direct).

### 4.5 Commandes de table

Trois endroits chargent ou paient un tarif sans passer par les gardes :

| Endroit | Aujourd'hui | Garde |
|---|---|---|
| `ouvrir_commande` (~l.10710) | `Price.objects.get(uuid=…, product=…)` sans filtre | refus d'un tarif non fiduciaire, **avant** la boucle `atomic` |
| `ajouter_articles` (~l.10851) | idem | idem |
| `payer_commande` (~l.10957) | appelle `_payer_en_especes` / `_payer_par_nfc` directement | refus si un article a `price.asset` non nul (filet de sécurité) |

### 4.6 Tireuse

`controlvanne/billing.py:287` et `controlvanne/models.py:306` :
`produit.prices.filter(poids_mesure=True).first()` sans filtre de monnaie. Ajout de
`asset__isnull=True` : la tireuse facture en euros.

## 5. Affichage

Un panier ne contient qu'une monnaie : chaque écran affiche son nom (« Points
fidélité ») là où il affiche « € ». Format des montants : comme les euros, deux
décimales (« 300,00 Points fidélité », « 1,00 Temps »).

| Où | Aujourd'hui | Changement |
|---|---|---|
| `_construire_donnees_articles`, dict `tarifs[]` (~l.626-641) | aucune info de monnaie par tarif | `unite_label` (nom de l'asset, ou symbole €) |
| `cotton/articles.html` (~l.18, 117, 126, 139, 150) | `currency_data.symbol` par tuile | `unite_label` du tarif |
| `static/js/tarif.js` (~l.51-179) | un seul `currency` pour tous les tarifs | `tarif.unite_label`, **repli sur `currency`** s'il est absent (`tests/e2e/test_tarif_popup.py` injecte `currency` seul) |
| `static/js/addition.js` (~l.141, 164, 392) + `cotton/addition_footer.html:48` | total toujours en € | l'unité du total suit la 1ʳᵉ ligne (un panier mixte afficherait une somme sans sens avant le refus serveur : accepté, le serveur fait foi) |
| écrans de paiement (`hx_display_type_payment.html`, `hx_confirm_payment.html`, `hx_return_payment_success.html`, `hx_funds_insufficient.html`, `_succes_carte.html`) | `CURRENCY_DATA` et filtre `euros` | les vues passent un `currency_data` au nom de la monnaie du panier ; filtre `montant_en_unites` (÷ 100, deux décimales, sans symbole) |
| liste des ventes et détail d'une vente (`liste_ventes` ~l.3591, `detail_vente` ~l.3731) | `amount × qty` avec `|euros` | ligne NM : montant en unités + nom de la monnaie |
| ticket client (`printing/formatters.py`, `escpos_builder.py`, `sunmi_inner.py`) | « EUR » en dur | clé `unite` fournie par le formateur ; pas de bloc TVA sur un ticket en points |

## 6. Rapports (Z, ticket X, exports)

- `NM` est dans `MOYENS_HORS_ARGENT` : total, TVA, CA, FEC, panier moyen ne voient
  jamais ces lignes (fiche D).
- `calculer_non_monetaire()` dans `laboutik/reports.py`, calquée sur
  `cashless_detail` (~l.258-297, regroupement **par nom** d'asset) :

```python
{"par_monnaie": [
    {"nom": "Points fidélité", "qty_articles": 3, "unites": "900,00"},
    {"nom": "Temps", "qty_articles": 5, "unites": "5,00"},
]}
```

  (`unites` = `Σ amount × qty / 100`, stocké en centièmes entiers dans
  `rapport_json`, formaté à l'affichage.) Clé `"non_monetaire"` dans
  `generer_rapport_complet()` et appel explicite dans `recap_en_cours` (ticket X).
- Affichage aux mêmes endroits que « Offerts » (fiche D, caisse **et** admin) :
  `data-testid="cloture-non-monetaire"` / `recap-non-monetaire`.
- **Archive fiscale LNE** : ligne NM avec son code, TVA 0, `total_ht` = TTC (D11).
- **Chaînage HMAC** : la ligne NM reste dans la chaîne `LABOUTIK`.

## 7. Tests

Tests de rapport en schéma dédié (D28). Produits, tarifs et point de vente créés
par le test (pas la démo).

### 7.1 pytest (serveur)

| # | Scénario | Assertion (rouge aujourd'hui) |
|---|---|---|
| E1 | tuiles d'un PV avec un article « Pin's » 300 FID | article présent, tarif `unite_label` == nom de l'asset FID |
| E2 | article avec tarif 5 € (order 100) et tarif TIM (order 100) | deux tarifs, le tarif en euros en premier, tuile au prix 5 € |
| E3 | panier Pin's seul, carte avec 30000 FID, POST `nfc` | 1 ligne `NM`, `amount == 30000`, `vat == 0` ; solde FID == 0 |
| E3b | adhésion avec tarif 300 FID, POST `nfc` | adhésion créée, ligne `NM`, solde FID débité, **aucun débit en euros** |
| E4 | panier Pin's + article 5 € | refus (`hx_messages`), aucune ligne, aucun débit |
| E5 | panier Pin's + article TIM | refus, aucune ligne |
| E6 | panier Pin's, **POST forgé `espece`** | refus, aucune ligne |
| E6b | panier Pin's, POST `gift` avec carte gérant | refus, aucune ligne |
| E7 | `moyens_paiement` sur panier Pin's | seul `nfc` ; pas de tuile OFFRIR |
| E8 | carte avec 10000 FID | popup avec le nom de la monnaie, sans bouton 2ᵉ carte, aucune ligne |
| E9 | deux produits FID à 300, carte avec 50000 FID | refus propre en phase 3 (popup), aucun débit |
| E10 | clôture après E3 + vente espèces 500 | `total_general == 500`, `tva` sans les points, `non_monetaire` : 1 article, 30000 centièmes |
| E11 | FEC de E10 (mappings laboutik créés) | équilibré, aucune écriture NM |
| E12 | archive fiscale de E10, ligne par uuid | TVA 0, `total_ht` == TTC |
| E13 | `ouvrir_commande` et `ajouter_articles` avec le tarif Pin's | refus, aucun article de commande créé |
| E13b | `payer_commande` sur une commande contenant un tarif en points (créée en base) | refus |
| E14 | tireuse : fût avec tarif TIM « au poids » + tarif euros | la facturation prend le tarif euros |
| E15 | tarif dont la monnaie a une catégorie hors mapping (monkeypatch du mapping) | refus à la classification, aucun débit, aucune ligne |
| E16 | POST direct `_executer_paiement_complementaire` avec panier Pin's | refus |
| E17 | admin : tarif non fiduciaire sur un produit recharge | formulaire refusé |
| E18 | `liste_ventes` après E3 | la vente affiche des points, pas « 300,00 € » |

### 7.2 E2E Playwright (affichage, JS)

| # | Scénario |
|---|---|
| E19 | tuile Pin's affiche « 300,00 Points fidélité », pas « € » |
| E20 | popup multi-tarif : « 5,00 € » et « 1,00 Temps » |
| E21 | panier Pin's : total en points ; seul le bouton CASHLESS apparaît |
| E22 | panier mixte → message « encaissez-les séparément » à VALIDER |
| E23 | paiement réussi avec carte NFC simulée : écran de succès en points |

### 7.3 Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| `Asset.FID: LOCAL_EURO` rétabli | E3, E10 |
| adhésion classée avant le test non fiduciaire | E3b |
| garde « NFC uniquement » retirée | E6, E6b |
| garde « une seule monnaie » retirée | E4, E5 |
| solde vérifié article par article | E9 |
| `NON_MONETAIRE` retiré de `MOYENS_HORS_ARGENT` | E10, E11 |
| TVA 0 retirée pour NM | E3, E12 |
| tri « euros d'abord » retiré | E2 |
| garde de `ajouter_articles` retirée | E13 |
| filtre tireuse `asset__isnull=True` retiré | E14 |
| vérification de catégorie en phase 2 retirée | E15 |
| validation admin retirée | E17 |

Le test `test_qrcodescanpay_flux_complet.py` ~l.626 (paiement QR, `if/elif` propre)
n'est pas touché.

## 8. Découpage en sessions

| Session | Contenu | Livrable vérifiable |
|---|---|---|
| E1 | `NON_MONETAIRE` + migration (+ schémas de test) + mapping sans repli + TVA 0 + `MOYENS_HORS_ARGENT` + `calculer_non_monetaire` + libellés + validation admin | E17 vert ; `manage.py check`, suite complète verte |
| E2 | tarifs visibles et triés, classement (adhésions), une seule monnaie, NFC uniquement, solde sur la somme, complément, commandes, tireuse | E1-E16 verts |
| E3 | affichage : tuiles, popup tarifs, panier, écrans de paiement, liste des ventes, ticket imprimé, Z/X caisse et admin | E18-E23 verts |
| E4 | relecture, `make test` + `make e2e` complets, CHANGELOG | suites vertes |

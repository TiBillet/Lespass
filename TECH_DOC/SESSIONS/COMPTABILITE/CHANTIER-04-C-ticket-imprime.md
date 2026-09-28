# Chantier 04-C — Ticket client imprimé : quantité, détail des moyens, impression

> **Statut** : ✅ LIVRÉ (non commité) le 2026-09-27 — voir CHANGELOG
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décision : D20 — Indépendante des autres fiches (le ticket client ne lit que des
> lignes de caisse, qui suivent déjà la règle d'or)
> Effort estimé : 1 j

---

## 1. Le défaut, simplement

Après un paiement, le caissier peut imprimer un ticket pour le client
(`laboutik/views.py` ~l.10262-10295 : lignes du `uuid_transaction` →
`laboutik/printing/formatters.py` → `formatter_ticket_vente()` →
`imprimer_async.delay`).

**Erreur 1 — la quantité est tronquée à l'entier.** Un article payé avec deux
monnaies donne deux lignes avec des quantités partielles (règle d'or). Exemple :
3 verres à 5 € (15 €), payés 6 € en cadeau et 9 € en monnaie locale → lignes
`qty 1,2` et `qty 1,8`. Le ticket imprime :

```
Vin x1   5,00        (au lieu de 6,00)
Vin x1   5,00        (au lieu de 9,00)
TOTAL   10,00        (au lieu de 15,00)
```

Un seul verre à 10 € payé 2 € + 8 € (`qty 0,2` et `0,8`) : **« x0, 0,00 € »**. La
TVA du ticket est calculée sur ces totaux faux.

**Erreur 2 — le détail « payé par monnaie » est faux, et n'est jamais imprimé.**
Le formateur calcule un `cascade_detail` qui additionne des prix unitaires (même
exemple : « 5,00 / 5,00 » au lieu de « 6,00 / 9,00 ») et ignore les espèces / CB d'un
complément. Mais **aucune imprimante ne lit `cascade_detail`** : il n'apparaît
jamais sur le papier.

## 2. Où, dans le code (vérifié le 2026-09-27)

`laboutik/printing/formatters.py`, `formatter_ticket_vente(lignes_articles, pv,
operateur, moyen_paiement)` (l.25) :

```python
# ~l.101 — erreur 1
qty = int(ligne.qty)                       # ← 1,8 devient 1 ; 0,2 devient 0
amount_centimes = ligne.amount
article_total = amount_centimes * qty
```

```python
# ~l.231-238 — erreur 2
lignes_par_asset = (
    LigneArticle.objects.filter(uuid_transaction=uuid_tx, asset__isnull=False)
    .values("asset")
    .annotate(total=_Sum("amount"))        # ← somme des prix unitaires, sans qty
)
```

Deux moteurs de rendu lisent le dictionnaire du ticket :

| Moteur | Utilisé par | Lit `cascade_detail` ? |
|---|---|---|
| `escpos_builder.py` → `build_escpos_from_ticket_data()` (l.30) | Sunmi Cloud, Sunmi LAN, mock | **non** |
| `sunmi_inner.py` | imprimante interne Sunmi | **non** |

Les deux impriment `x{article_qty}` tel quel (`escpos_builder.py` ~l.156,
`sunmi_inner.py` ~l.96) : une quantité `Decimal("3.000000")` s'imprimerait
« x3.000000 ».

Le complément espèces/CB d'un paiement NFC partage bien le `uuid_transaction`
(`laboutik/views.py` ~l.8813 → 9019-9023, 9604-9609).

**Aucun test** ne couvre `formatter_ticket_vente` ni le rendu du ticket de vente.

## 3. Le correctif

### 3.1 Regrouper les parts d'un même article

Les parts d'un même article partagent `pricesold`, `amount` (prix unitaire) et `vat`.
On les regroupe : le client a acheté « 3 verres de vin ».

```python
# Les parts d'un meme article paye avec plusieurs monnaies ont le meme tarif
# vendu, le meme prix unitaire et la meme TVA : on les regroupe, le client lit
# « Vin x3 ».
# / Parts of one item paid with several currencies are grouped: "Wine x3".
articles_regroupes = {}
for ligne in lignes_articles:
    cle = (ligne.pricesold_id, ligne.amount, float(ligne.vat or 0))
    if cle not in articles_regroupes:
        articles_regroupes[cle] = {"ligne": ligne, "qty": Decimal("0")}
    articles_regroupes[cle]["qty"] += ligne.qty
```

- Montant d'un article : `int(Decimal(amount × qty).quantize(Decimal("1"),
  rounding=ROUND_HALF_UP))` (règle d'arrondi du tronc §2).
- **Quantité mise dans le dictionnaire** : un `int` si elle est entière, sinon une
  chaîne à deux décimales. Jamais un `Decimal` (lisibilité du ticket, et
  sérialisation JSON de `imprimer_async.delay`).
- `weight_detail` (vente au poids) est lu sur la 1ʳᵉ ligne du groupe (identique
  sur toutes les parts, ~l.5356). Deux ventes au poids identiques dans le même
  ticket ne garderaient qu'un détail : accepté.

### 3.2 Détail de tous les moyens de paiement (D20)

`cascade_detail` devient une ligne par **monnaie de carte** (par nom d'asset) **plus**
une ligne par **autre moyen** (Espèces, CB, Chèque) :

```python
# montant_ttc_centimes() importe de laboutik/reports.py ; libelle des moyens
# hors carte par dict(PaymentMethod.choices) (la requete rend des dicts, pas
# des instances : get_payment_method_display() n'existe pas ici).
.values("asset", "payment_method").annotate(total=montant_ttc_centimes())
```

### 3.3 Impression, seulement si au moins deux moyens

Les deux moteurs impriment le bloc **quand `cascade_detail` contient au moins deux
lignes**. Un ticket payé d'un seul moyen reste comme aujourd'hui.

```
Vin            x3     15,00
TOTAL                 15,00
-----------------------------
Cadeau                 6,00
Monnaie locale         4,00
Espèces                5,00
```

## 4. Tests

Mise en place réelle (cascade NFC, complément) sur le modèle de
`tests/pytest/test_paiement_complementaire.py` et `test_pos_retour_consigne.py`
(`FastTenantTestCase`, Token TNF/TLF, POST `/laboutik/paiement/payer/`).

| # | Scénario | Assertion (rouge aujourd'hui) |
|---|---|---|
| C1 | 3 × article 500 cts payé TNF 600 + TLF 900 | un seul article, `qty == 3` **de type `int`**, `total == 1500` ; total du ticket 1500 (aujourd'hui 1000) |
| C2 | 1 × article 1000 cts payé 200 + 800 | `total == 1000` (aujourd'hui 0) |
| C3 | même paiement que C1 | `cascade_detail` = Cadeau 600, Monnaie locale 900 (aujourd'hui 500 / 500) |
| C4 | paiement espèces 2 × 500 (non-régression) | `qty == 2`, `total == 1000`, `cascade_detail` d'une seule ligne |
| C5 | TVA du ticket C1, taux 20 % | `ht == 1250`, `tva == 250` |
| C6 | 15 € payés TNF 600 + TLF 400 + complément espèces 500 (`payer_complementaire`) | détail : Cadeau 600, Monnaie locale 400, Espèces 500 |
| C7 | `build_escpos_from_ticket_data()` sur le dictionnaire de C6 | les octets contiennent « Espèces » et « 5,00 » ; ceux de C4 ne contiennent pas le bloc |
| C8 | rendu `sunmi_inner` sur le dictionnaire de C6 | idem |

### Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| `int(ligne.qty)` rétabli | C1, C2 |
| `Sum("amount")` rétabli | C3 |
| filtre `asset__isnull=False` rétabli | C6 |
| bloc de détail retiré de `escpos_builder` | C7 |
| seuil « au moins deux moyens » retiré | C7 (partie C4) |

## 5. Fichiers touchés

| Fichier | Changement |
|---|---|
| `laboutik/printing/formatters.py` | regroupement, `amount × qty`, quantité lisible, détail de tous les moyens |
| `laboutik/printing/escpos_builder.py` | impression du détail si ≥ 2 moyens |
| `laboutik/printing/sunmi_inner.py` | idem |
| nouveau `tests/pytest/test_ticket_client_imprime.py` | C1-C8 |

Pas de migration.

## 6. Lien avec la fiche E

La fiche E modifie ensuite ce même dictionnaire pour les ventes en **points** : clé
`unite` (au lieu de « EUR » écrit en dur dans les deux moteurs) et pas de bloc TVA.

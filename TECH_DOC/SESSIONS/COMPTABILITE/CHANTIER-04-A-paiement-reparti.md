# Chantier 04-A — Paiement réparti sur deux monnaies (QR/NFC et tireuse)

> **Statut** : ✅ LIVRÉ (non commité) le 2026-09-27 — voir CHANGELOG
> Tronc commun : [`CHANTIER-04-melanges-argent.md`](CHANTIER-04-melanges-argent.md)
> Décision : D18

---

## 1. Le défaut, simplement

Quand un client paie avec **deux monnaies** (une partie en monnaie locale TLF, le
reste en monnaie fédérée FED, ou une partie en cadeau TNF à la tireuse), Lespass
crée une ligne de vente par monnaie. Chaque ligne reçoit :

- `amount` = **la part d'argent** de cette monnaie ;
- `qty` = **la proportion** de cette part (part / total).

Le montant d'une ligne vaut `amount × qty`. On multiplie donc la part par elle-même :

> 10 € payés 6 € + 4 € → 600 × 0,6 + 400 × 0,4 = 360 + 160 = **5,20 €** enregistrés.

Il manque 4,80 € dans le ticket Z, les exports et le chiffre d'affaires.

Avec **une seule** monnaie, `qty = 1` et `amount = total` : le montant est juste.
Le défaut ne touche que les paiements répartis.

## 2. Où, dans le code (vérifié le 2026-09-27)

### 2.1 Paiement QR code / carte NFC en ligne — deux copies du même code

`BaseBillet/views.py`, `QrCodeScanPay.process_with_nfc()` (~l.1970-1982) et
`QrCodeScanPay.valid_payment()` (~l.2167-2179) :

```python
total_amount = ligne_article.amount
...
for transaction in transactions:
    ...
    ligne_article = LigneArticle.objects.create(
        ...
        qty=dround(Decimal(transaction['amount'] / total_amount)),   # ← proportion
        amount=transaction['amount'],                              # ← part d'argent
        ...
    )
```

Deux défauts :

1. `amount` porte la part, pas le prix unitaire → montant² / total.
2. `dround()` (`fedow_connect/utils.py:16`) arrondit la `qty` à **2 décimales**
   (le champ en a 6). Même avec le bon `amount`, 3,33 € sur 10 € donnerait
   `qty = 0,33` → 3,30 €.

Le serveur Fedow découpe bien le paiement en plusieurs transactions :
`Fedow/fedow_core/serializers.py` → `TransactionQrCodeSerializer._iter_asset_payments()`
répartit sur les assets fiduciaires acceptés (TLF puis FED).

La ligne d'origine (`BaseBillet/views.py` ~l.1877) a toujours `qty=1` et
`amount = montant total` : `total_amount` est donc bien le prix unitaire.

### 2.2 Tireuse connectée

`controlvanne/billing.py` (~l.300-335) :

```python
lignes_amounts = [{"amount_centimes": montant_a} for _, montant_a in debits_par_asset]
lignes_avec_qty = _calculer_qty_partielles(lignes_amounts, montant_centimes, Decimal("1"))
...
ligne = LigneArticle.objects.create(
    ...
    qty=qty_partielle,       # ← proportion (calcul juste, 6 décimales)
    amount=montant_a,        # ← part d'argent : même défaut
    ...
)
```

Le commentaire juste au-dessus (~l.302) le montre sans le voir : « Pinte mixte
1 € TNF + 3 € TLF → qty 0,25 LOCAL_GIFT + qty 0,75 LOCAL_EURO ». Avec
`amount = 100` puis `300`, la pinte de 4 € est enregistrée **2,50 €**.

Le cas « solde insuffisant » (~l.258-274) réduit `montant_centimes` au montant
réellement débité **avant** ce calcul : le correctif reste cohérent (décision D27 :
on n'y touche pas).

### 2.3 En base de dev

Relevé du 2026-09-27 : 37 lignes QRCODE_MA, 2 NFC_MA, 12 TIREUSE. Aucune ligne
répartie (pas deux lignes pour un même paiement). Les 3 lignes avec `qty ≠ 1`
(QR qty 20 amount 500 ; NFC qty 10 amount 400 et 600, datées 2026-09-25 14:00,
sans `uuid_transaction`) sont des données de démo qui suivent déjà la règle d'or.
Rien à rattraper.

## 3. Le correctif

Appliquer la règle d'or : `amount` = prix unitaire, `qty` = proportion à 6
décimales, la dernière ligne prend le reste. La fonction existe déjà :
`laboutik/views.py` → `_calculer_qty_partielles()`.

### 3.1 QR/NFC (deux endroits identiques)

```python
# Import local, comme controlvanne/billing.py : laboutik.views est un gros
# module qu'on ne charge que sur ce chemin de paiement.
# / Local import, as in controlvanne/billing.py.
from laboutik.views import _calculer_qty_partielles

total_amount = ligne_article.amount
parts_par_transaction = [{"amount_centimes": t["amount"]} for t in transactions]
parts_avec_qty = _calculer_qty_partielles(parts_par_transaction, total_amount, Decimal("1"))

for index, transaction in enumerate(transactions):
    ...
    LigneArticle.objects.create(
        ...
        amount=total_amount,                   # prix unitaire / unit price
        qty=parts_avec_qty[index]["qty"],      # proportion a 6 decimales
        ...
    )
```

On garde les deux copies (`process_with_nfc` et `valid_payment`) telles quelles :
pas de factorisation dans ce chantier. (La fiche F réorganise ensuite ces deux
blocs : appels réseau d'abord, puis une transaction.)

**Effet visible** : `process_with_nfc` répond au navigateur
`'amount_paid': dround(ligne_article.amount)` et
`'balance': user_balance - ligne_article.amount` (~l.2011-2012), lus sur la
**dernière** ligne créée. Aujourd'hui c'est la part de la dernière monnaie (faux) ;
après le correctif, c'est le total payé (juste).

**Au passage** : `transactions.index(transaction)` (choix de l'uuid réutilisé) devient `enumerate`. Une garde bon marché journalise une erreur si `Σ parts != total_amount` (Fedow garantit l'allocation complète, `Fedow/fedow_core/serializers.py` ~l.1108, mais le correctif masquerait un débit partiel). Le `raise f"..."` de `process_with_nfc` (~l.2005, lève une `TypeError`) est corrigé par la fiche F.

**Non-cas** : une transaction Fedow à 0 n'arrive pas (`_iter_asset_payments` saute
les soldes nuls, `Fedow/fedow_core/serializers.py` ~l.1099-1101).

### 3.2 Tireuse

Une seule ligne change : `amount=montant_centimes` au lieu de `amount=montant_a`.
Le commentaire de ~l.302 est réécrit au présent avec l'exemple juste
(« amount = 400 sur les deux lignes, qty 0,25 et 0,75 »).

### 3.3 Arrondis

`LigneArticle.total()` tronque (`int()`), alors que les rapports arrondissent la
somme (`Round(Sum(amount × qty))`). La somme des `total()` peut donc valoir le
total moins 1 centime. Les rapports restent justes. Les tests comparent donc les
**totaux du rapport** et la **somme des `qty`**, pas la somme des `total()`
arrondis ligne à ligne.

## 4. Tests

### 4.1 Test existant qui passe à tort

`tests/pytest/test_qrcodescanpay_flux_complet.py`
→ `test_un_paiement_reparti_sur_deux_monnaies_donne_deux_lignes` (~l.479-506) :

```python
assert sum(une_ligne.amount for une_ligne in lignes) == MONTANT_DEMANDE_CENTIMES
```

Il additionne des `amount` : il est vrai **sur le défaut** (500 + 750 = 1250) et
deviendrait faux après le correctif (1250 + 1250). À réécrire.

### 4.2 Tests à écrire (rouges sur le code actuel)

| # | Fichier | Scénario | Assertions |
|---|---|---|---|
| A1 | `test_qrcodescanpay_flux_complet.py` | `valid_payment`, Fedow simulé renvoie 500 + 750 sur 1250 | chaque ligne `amount == 1250` ; `Σ qty == 1` ; `Σ amount×qty == 1250` (aujourd'hui 650) |
| A2 | idem | `process_with_nfc`, même simulation | mêmes assertions + réponse `amount_paid == 12.50` |
| A3 | idem | trois parts 333 + 333 + 334 sur 1000 | `Σ qty == Decimal("1.000000")` exactement (aujourd'hui 0,99 avec `dround`) |
| A4 | `test_controlvanne_billing.py` (base partagée : le test ne lit que ses lignes) | tirage 250 cts, carte 100 cts TNF + 1000 cts TLF | lignes du `uuid_transaction` du tirage : 2 lignes `amount == 250`, `Σ qty == 1`, `Σ amount × qty == 250` (aujourd'hui 130). Pas de rapport : le défaut est dans `amount`/`qty`. La fixture `carte_avec_solde` (~l.111-149) n'a que du TLF : ajouter un asset TNF (même astuce `order_by("name").first()` que `asset_tlf`, ~l.95-108, car `obtenir_contexte_cashless` prend le premier TNF accessible). |
| A5 | idem | une seule monnaie (non-régression) | 1 ligne, `qty == 1`, `amount == montant` |

### 4.3 Mutations à jouer

| Mutation | Test qui doit tomber |
|---|---|
| `amount=transaction['amount']` rétabli dans `valid_payment` | A1 |
| idem dans `process_with_nfc` | A2 |
| `dround(...)` rétabli pour la `qty` | A3 |
| `amount=montant_a` rétabli dans `billing.py` | A4 |

## 5. Fichiers touchés

| Fichier | Changement |
|---|---|
| `BaseBillet/views.py` | `process_with_nfc`, `valid_payment` : `amount` unitaire + `_calculer_qty_partielles` |
| `controlvanne/billing.py` | `amount=montant_centimes` + commentaire |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | test existant corrigé + A1-A3 |
| `tests/pytest/test_controlvanne_billing.py` | A4-A5 |

Pas de migration.

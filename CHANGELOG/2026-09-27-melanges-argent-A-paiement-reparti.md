# Paiement réparti sur deux monnaies : montant enregistré juste / Split payment: correct recorded amount

**Date :** 2026-09-27
**Migration :** Non

## Resume / Summary

**Quoi / What :** un paiement QR code, carte NFC en ligne ou tireuse, réparti sur
deux monnaies, enregistre désormais le montant entier. Chaque ligne porte le prix
unitaire du paiement dans `amount` et la part de sa monnaie dans `qty` (6 décimales,
la dernière part prend le reste). /
A QR code, online NFC card or tap payment split over two currencies now records the
full amount: unit price in `amount`, currency share in `qty`.

**Pourquoi / Why :** chaque ligne portait la part d'argent dans `amount` ET la
proportion dans `qty`. Le montant (`amount × qty`) valait donc part² / total :
10 € payés 6 + 4 étaient enregistrés 5,20 €. La quantité était en plus arrondie à
2 décimales (3 parts de 3,33 € → 0,99). /
Each line carried the money share in `amount` AND the ratio in `qty`, so the amount
was share² / total (10 € paid 6 + 4 recorded as 5.20 €).

Chantier : `TECH_DOC/SESSIONS/COMPTABILITE/CHANTIER-04-A-paiement-reparti.md`.
Aucune ligne existante n'est modifiée. Si Fedow débite moins que demandé (cas non
attendu : il répartit le montant entier), l'écart est journalisé et la vente enregistre
ce qui a été réellement débité, comme la tireuse.

**Base de dev** : les lancements de `test_08` d'avant son nettoyage ont laissé 8 wallets
« Wallet test tirage reparti » et 16 lignes TIREUSE (dont 3 paires à l'ancienne
convention). Purge à décider par le mainteneur. `test_08` nettoie désormais tout ce
qu'il crée (`try/finally`).

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `BaseBillet/views.py` | `process_with_nfc` et `valid_payment` : `amount` = montant total, `qty` via `_calculer_qty_partielles`, `enumerate` au lieu de `transactions.index` ; si les parts ne font pas le total : erreur journalisée et vente au montant débité |
| `controlvanne/billing.py` | `facturer_tirage` : `amount=montant_centimes` (prix du tirage) + commentaire d'exemple corrigé |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` | test « deux monnaies » corrigé (il additionnait des `amount` et passait sur le défaut) ; 2 nouveaux tests (trois parts, carte NFC répartie) |
| `tests/pytest/test_controlvanne_billing.py` | nouveau `test_08` : tirage réparti TNF + TLF, nettoyage en `finally` |
| `tests/pytest/test_qrcodescanpay_flux_complet.py` (relecture) | `test_un_debit_partiel_enregistre_ce_qui_a_ete_paye` |

### Tests vus échouer puis mutations / Tests seen failing, then mutations

Avant correctif : 4 échecs sur le défaut (`amount` 750 au lieu de 1250, 334 au lieu
de 1000, 150 au lieu de 250 ; `amount_paid` 7,50 au lieu de 12,50).

| Mutation du code de production | Test qui tombe |
|---|---|
| `valid_payment` : `amount=transaction['amount']` | `..._reparti_sur_deux_monnaies_donne_deux_lignes`, `..._reparti_en_trois_parts_...` |
| `process_with_nfc` : `amount=transaction['amount']` | `test_un_paiement_par_carte_reparti_enregistre_le_montant_entier` |
| `valid_payment` : `qty=dround(...)` | `test_un_paiement_reparti_en_trois_parts_garde_toute_la_quantite` |
| `facturer_tirage` : `amount=montant_a` | `test_08_pour_end_reparti_sur_deux_monnaies_enregistre_le_montant_entier` |
| `valid_payment` : `total_amount = somme_des_parts` retiré | `test_un_debit_partiel_enregistre_ce_qui_a_ete_paye` |

Chaque mutation restaurée, empreinte sha256 vérifiée.

---

## Comment tester (a la main) / Manual test

### Test 1 — paiement QR réparti
1. Un adhérent possède de la monnaie locale (TLF) ET de la monnaie fédérée (FED),
   aucune des deux ne couvrant seule le montant.
2. L'encaisseur génère un QR code de 12,50 € ; l'adhérent le scanne et valide.
3. Admin → Lignes comptables : deux lignes QRCODE_MA, chacune à 12,50 € de prix
   unitaire, quantités qui somment à 1 ; total des deux = 12,50 €.

### Test 2 — tireuse, carte avec cadeau + monnaie locale
1. Carte avec 1,00 € de monnaie cadeau et du TLF.
2. Tirer 50 cl à 5 €/L.
3. Deux lignes TIREUSE à 2,50 € de prix unitaire, quantités 0,4 et 0,6 ; ticket X :
   2,50 € en cashless.

### Verifs DB
```bash
docker exec -i lespass_django poetry run python /DjangoFiles/manage.py shell <<'PY'
from django_tenants.utils import tenant_context
from Customers.models import Client
from BaseBillet.models import LigneArticle
with tenant_context(Client.objects.get(schema_name="lespass")):
    for l in LigneArticle.objects.filter(sale_origin__in=["QR", "NF", "TI"]).order_by("-datetime")[:6]:
        print(l.sale_origin, l.payment_method, l.amount, l.qty, l.amount * l.qty)
PY
```

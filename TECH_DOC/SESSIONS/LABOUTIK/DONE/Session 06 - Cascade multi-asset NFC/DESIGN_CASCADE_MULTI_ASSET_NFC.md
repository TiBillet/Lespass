# Design — Cascade multi-asset NFC + paiement complémentaire

> Date : 2026-04-08
> Statut : validé en brainstorming
> Scope : tâche 0 de l'INDEX

---

## 1. Objectif

Quand un client paie par NFC, le système débite ses tokens dans un ordre
de priorité fixe : **TNF (cadeau) → TLF (local) → FED (fédéré)**.
Aujourd'hui `_payer_par_nfc()` ne débite que sur un seul asset TLF.

En complément : les articles avec un prix non-fiduciaire (TIM, FID) sont
débités directement sur leur asset. Si la cascade NFC ne couvre pas le total,
l'opérateur peut compléter en espèces, CB, ou 2ème carte NFC.

---

## 2. Modèle de données

### 2.1 `Price.non_fiduciaire` (nouveau champ)

```python
# BaseBillet/models.py — sur Price
non_fiduciaire = models.BooleanField(
    default=False,
    verbose_name=_("Non-fiduciary price"),
    help_text=_("If checked, the price is in tokens (time, loyalty, etc.) instead of euros."),
)
```

**Validation `clean()` :**
- `non_fiduciaire=True` et `asset=None` → `ValidationError`
- `non_fiduciaire=True` et `asset.category in (TLF, TNF, FED)` → `ValidationError`
- `non_fiduciaire=False` → `asset` ignoré (peut rester set sans effet)

**Admin POSPriceInline :**
- `non_fiduciaire` visible
- `asset` en conditional field (visible seulement si `non_fiduciaire=True`)
- `asset` filtré sur les assets TIM/FID du tenant

**1 migration BaseBillet.**

### 2.2 `LigneArticle` — pas de changement modèle

Les champs existants suffisent :

| Champ | Type | Rôle cascade |
|-------|------|-------------|
| `qty` | Decimal(12,6) | Quantité partielle (somme = qty totale de l'article) |
| `amount` | int (centimes) | Montant débité sur cet asset (entier, zéro arrondi) |
| `asset` | UUID nullable | UUID de l'asset débité (null pour espèces/CB) |
| `uuid_transaction` | UUID | Regroupe les N lignes d'un même paiement |
| `payment_method` | CharField | "LE" (cashless), "CA" (espèces), "CC" (CB) |
| `carte` | FK CarteCashless | Carte NFC utilisée (null pour espèces/CB) |

**Exemple — Bière 4€ payée 1€ TNF + 3€ espèces :**

```
LigneArticle 1 : qty=0.25, amount=100, asset=TNF_uuid, payment_method=LE, carte=carte1
LigneArticle 2 : qty=0.75, amount=300, asset=null,     payment_method=CA, carte=null
```

---

## 3. Cascade fiduciaire

### 3.1 Ordre fixe

```python
ORDRE_CASCADE_FIDUCIAIRE = [Asset.TNF, Asset.TLF, Asset.FED]
```

Codé en dur. Pas configurable par tenant (décision brainstorming).
L'ordre correspond au legacy LaBoutik et à la logique métier :
cadeau (offert) → local (déjà encaissé) → fédéré (frais Stripe).

### 3.2 Algorithme boucle article par article

```
Phase 1 : Préparer les soldes disponibles
  soldes_cascade = OrderedDict()
  Pour chaque catégorie dans ORDRE_CASCADE_FIDUCIAIRE :
    asset = Asset.objects.filter(tenant, category, active=True).first()
    Si asset et solde > 0 : soldes_cascade[asset] = solde

Phase 2 : Classifier les articles
  articles_fiduciaires     → Price.non_fiduciaire=False (VT + AD)
  articles_non_fiduciaires → Price.non_fiduciaire=True
  articles_recharge         → RC/TM (inchangé)

Phase 3 : Vérifier soldes non-fiduciaires
  Pour chaque article non-fiduciaire :
    solde = WalletService.obtenir_solde(wallet, price.asset)
    Si insuffisant → rejet immédiat, TOUT le paiement est annulé

Phase 4 : Boucle cascade article par article
  lignes_a_creer = []
  soldes_restants = copie(soldes_cascade)

  Pour chaque article fiduciaire :
    reste_article = montant_article_centimes
    Pour chaque (asset, solde) dans soldes_restants :
      Si reste <= 0 : break
      Si solde <= 0 : continue
      debit = min(solde, reste)
      lignes_a_creer.append((article, asset, debit))
      soldes_restants[asset] -= debit
      reste_article -= debit
    Si reste > 0 :
      lignes_a_creer.append((article, None, reste))  # complémentaire

Phase 5 : Calculer total complémentaire
  total_complementaire = sum(amount pour lignes avec asset=None)

Phase 6 : Si complémentaire > 0 → écran choix opérateur
  Sinon → bloc atomic
```

### 3.3 Calcul qty partielle

Pour un article donné, on collecte ses N lignes `[(asset, amount), ...]` :

```python
SIX_PLACES = Decimal("0.000001")
prix_unitaire_centimes = article["prix_centimes"]
qty_totale = article["quantite"]
somme_qty = Decimal("0")

for i, (asset, amount) in enumerate(lignes_de_cet_article):
    est_derniere = (i == len(lignes_de_cet_article) - 1)
    if est_derniere:
        qty_partielle = qty_totale - somme_qty
    else:
        qty_partielle = (qty_totale * Decimal(amount) / Decimal(prix_unitaire_centimes)).quantize(SIX_PLACES)
        somme_qty += qty_partielle
```

- Somme qty = qty_totale exactement (la dernière prend le reste)
- Somme amount = total article exactement (entiers, zéro arrondi)

---

## 4. Débit non-fiduciaire (TIM/FID)

Pas de cascade. Débit direct sur `Price.asset`.

- Si solde insuffisant → rejet immédiat de TOUT le paiement (pas juste l'article)
- Vérifié AVANT le bloc atomic (Phase 3)
- Dans l'atomic : `TransactionService.creer_vente(asset=price.asset)`

---

## 5. Paiement complémentaire

### 5.1 Déclenchement

Quand la cascade NFC ne couvre pas le total fiduciaire, au lieu de rejeter,
on affiche un écran intermédiaire avec le reste à payer.

### 5.2 Sources complémentaires

3 options pour l'opérateur :
- **Espèces** → le reste est payé cash
- **Carte bancaire** → le reste est payé CB
- **2ème carte NFC** → scan d'une autre carte, cascade sur ses assets

Maximum 2 cartes NFC (comme le legacy).

### 5.3 Template `hx_complement_paiement.html`

```
┌──────────────────────────────────────────────┐
│ Carte ABCD1234                               │
│ Solde utilisé : 8,00€ (3€ cadeau + 5€ local)│
│                                              │
│ Total panier : 12,00€                        │
│ Reste à payer : 4,00€                        │
│                                              │
│ [Espèces]  [Carte bancaire]  [Autre carte]   │
└──────────────────────────────────────────────┘
```

- `data-testid="complement-paiement"` sur le conteneur
- `data-testid="complement-btn-especes"`, `complement-btn-cb`, `complement-btn-nfc`
- `aria-live="polite"` sur la zone montants

### 5.4 Propagation des données

Hidden fields dans `#addition-form` :
- `tag_id_carte1` : tag_id de la 1ère carte
- `cascade_carte1` : JSON `[["asset_uuid", montant_centimes], ...]`
- `total_nfc_carte1` : total NFC en centimes
- Les `repid-*` du panier sont déjà dans `#addition-form`

### 5.5 Action `payer_complementaire`

Nouvelle action sur `PaiementViewSet` :

```python
@action(detail=False, methods=["POST"], url_path="payer-complementaire")
def payer_complementaire(self, request):
    # 1. Relire les données cascade carte1 depuis le POST
    # 2. Re-vérifier les soldes (race condition protection)
    # 3. Si complément = espèces/CB :
    #    → bloc atomic : débits NFC cascade + lignes complémentaires espèces/CB
    # 4. Si complément = 2ème carte NFC :
    #    → cascade sur carte2 pour le reste
    #    → si encore insuffisant → re-render hx_complement_paiement (2 cartes)
    #    → si OK → bloc atomic (débits carte1 + carte2)
    # 5. Même uuid_transaction pour toutes les lignes
```

### 5.6 Flow 2ème carte

1. Opérateur clique "Autre carte" → scan
2. `payer_complementaire` reçoit `tag_id_complement`
3. Cascade sur les assets de la 2ème carte pour le montant restant
4. Si encore insuffisant → re-render écran complémentaire, cette fois
   sans bouton "Autre carte" (max 2 cartes), seulement espèces/CB
5. Si OK → bloc atomic avec les 2 cartes

### 5.7 LigneArticle en complémentaire

Même `uuid_transaction`. Les lignes NFC ont `payment_method=LE` et `carte=carteX`.
Les lignes espèces/CB ont `payment_method=CA/CC`, `asset=null`, `carte=null`.

---

## 6. Ordre des opérations dans l'atomic

```
with db_transaction.atomic():
    # 1. Crédits recharges gratuites (RC/TM) — AVANT les débits
    #    Pour que le solde soit à jour si un article TIM est dans le panier
    _executer_recharges(articles_recharge_gratuite, ...)

    # 2. Débits non-fiduciaires (TIM/FID) — direct
    Pour chaque article non-fiduciaire :
        TransactionService.creer_vente(asset=price.asset, ...)
        créer LigneArticle(qty=totale, amount=total, asset=price.asset)

    # 3. Débits fiduciaires (cascade TNF→TLF→FED)
    Pour chaque (article, asset, amount) dans lignes_cascade :
        TransactionService.creer_vente(asset=asset, ...)

    # 4. Lignes complémentaires (espèces/CB) si applicable
    Pour chaque (article, None, amount) dans lignes_complement :
        créer LigneArticle(payment_method=CA/CC, asset=null)

    # 5. Créer LigneArticle cascade avec qty partielle
    #    (regrouper par article pour le calcul qty)

    # 6. Stock : décrémenté 1 SEULE fois par article
    #    (sur la qty totale, pas sur chaque ligne partielle)

    # 7. Adhésions : créer Membership, rattacher à la 1ère LigneArticle

    # 8. Billetterie : créer Reservation + Ticket

    # 9. HMAC : chaîner toutes les lignes créées (NFC + complémentaire)
```

---

## 7. Adaptation `_creer_lignes_articles()`

La fonction actuelle crée 1 LigneArticle par article du panier. Elle doit
être adaptée pour créer N lignes par article quand il y a cascade/complémentaire.

**Option retenue :** ne pas modifier `_creer_lignes_articles()` directement.
Créer une nouvelle fonction `_creer_lignes_articles_cascade()` qui prend
la liste de lignes pré-calculées `[(article, asset, amount_centimes)]` et
gère les qty partielles, le stock (1 seule fois), et le HMAC.

L'ancienne `_creer_lignes_articles()` reste inchangée pour les paiements
espèces/CB purs (pas de cascade).

---

## 8. Écran de succès enrichi

Le `hx_return_payment_success.html` affiche les soldes de tous les assets
débités :

```
✓ Paiement accepté — 12,00€
  Cadeau : 0,00€ restant
  Monnaie locale : 2,00€ restant
  Complément espèces : 4,00€
```

---

## 9. Impact rapports et clôture

### 9.1 Ticket X (`calculer_totaux_par_moyen`)

`cashless_detail` enrichi : au lieu d'un seul total cashless, détail par asset :

```python
cashless_detail = [
    {"name": "Cadeau", "total": 300},
    {"name": "Monnaie locale", "total": 500},
]
```

### 9.2 Clôture

Le total ventes = `sum(amount)` sur les LigneArticle. Pas de double comptage
car `amount` est le montant partiel (pas `qty × prix`).

### 9.3 Export FEC

Lignes cascade groupées par `uuid_transaction` → 1 écriture FEC par paiement.

### 9.4 Correction paiement

On peut corriger 1 ligne parmi N du même `uuid_transaction`. Le reste inchangé.

### 9.5 Impression ticket

Ticket enrichi : détail par asset + complément si applicable.

---

## 10. Fichiers impactés

| Fichier | Changement |
|---------|-----------|
| `BaseBillet/models.py` | `Price.non_fiduciaire` BooleanField + `clean()` |
| `BaseBillet/migrations/0XXX_*.py` | Migration `non_fiduciaire` |
| `laboutik/views.py` | `_payer_par_nfc()` refonte cascade + `_creer_lignes_articles_cascade()` + `payer_complementaire()` |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | Nouveau template |
| `laboutik/templates/laboutik/partial/hx_return_payment_success.html` | Affichage multi-soldes |
| `laboutik/templates/laboutik/partial/hx_funds_insufficient.html` | Adapter pour cascade |
| `laboutik/reports.py` | `cashless_detail` par asset dans `calculer_totaux_par_moyen()` |
| `laboutik/printing/formatters.py` | Ticket cascade (détail par asset) |
| `Administration/admin_tenant.py` | POSPriceInline : `non_fiduciaire` + conditional field `asset` |
| `Administration/admin_tenant.py` | `inline_conditional_fields` pour `non_fiduciaire` → `asset` |
| `laboutik/management/commands/create_test_pos_data.py` | Fixtures : assets TNF/FED, articles TIM/FID, wallet avec soldes |
| `tests/pytest/test_cascade_nfc.py` | 68 tests pytest |
| `tests/e2e/test_cascade_nfc.py` | 8 tests E2E |
| `tests/e2e/test_admin_price_non_fiduciaire.py` | 6 tests admin |

---

## 11. Tests — 82 cas exhaustifs

### A. Cascade fiduciaire — cas normaux (8 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 1 | TNF suffit pour tout | 1 LigneArticle, asset=TNF |
| 2 | TNF + TLF (TNF partiel) | 2 LigneArticle, sum(amount)=total |
| 3 | TNF + TLF + FED (3 assets) | 3 LigneArticle |
| 4 | TLF seul (pas de TNF) | 1 LigneArticle, asset=TLF |
| 5 | FED seul (pas de TNF ni TLF) | 1 LigneArticle, asset=FED |
| 6 | Montant exact = solde | Solde final = 0 |
| 7 | FED fédéré via Federation | Cascade inclut assets accessibles |
| 8 | Aucun asset fiduciaire actif | Rejet "Monnaie locale non configurée" |

### B. Cascade — qty partielle et amounts (6 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 9 | Split 2 assets : somme qty exacte | `Decimal("1.000000")` |
| 10 | Split 3 assets : pas de `.333333` infini | Dernière qty = reste |
| 11 | qty > 1 (3 bières) | sum(amount)=prix×3 |
| 12 | Article à 1 centime | Pas de qty=0 ni amount=0 |
| 13 | Prix libre dans cascade | custom_amount splitté |
| 14 | Poids/mesure dans cascade | weight_quantity identique, stock 1 fois |

### C. Multi-articles (5 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 15 | TNF épuisé sur le 1er article | 2ème commence sur TLF |
| 16 | 3 articles épuisent 3 assets | sum(all amounts) = total panier |
| 17 | Article gratuit (prix=0) | 1 ligne amount=0, pas de cascade |
| 18 | qty=5 du même article | 1 PriceSold, N LigneArticle si split |
| 19 | Ordre du panier respecté | Comme le legacy |

### D. Non-fiduciaire TIM/FID (6 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 20 | TIM suffisant | 1 LigneArticle asset=TIM |
| 21 | FID suffisant | 1 LigneArticle asset=FID |
| 22 | TIM insuffisant | Rejet immédiat |
| 23 | FID insuffisant | Rejet immédiat |
| 24 | Panier mixte EUR + TIM | Cascade EUR + direct TIM, même uuid_transaction |
| 25 | Mixte EUR + TIM, TIM insuffisant | Tout ou rien : rejet total |

### E. Complémentaire espèces/CB (8 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 26 | Cascade insuffisante → écran complément | Render template, pas 400 |
| 27 | Complément espèces | Lignes LE + CA, même uuid_transaction |
| 28 | Complément CB | Lignes LE + CC |
| 29 | Aucun solde NFC → tout en complément | Reste = total panier |
| 30 | Amounts entiers des 2 côtés | sum(NFC) + sum(complément) = total |
| 31 | Qty partielle NFC + complément | sum(qty) = qty_totale par article |
| 32 | Race condition entre écran et POST | Re-calcul cascade, adapte reste |
| 33 | Mixte EUR+TIM + complément espèces | TIM direct, EUR cascade+complément |

### F. Complémentaire 2ème carte NFC (6 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 34 | 2ème carte suffit | Toutes lignes LE, 2 cartes |
| 35 | 2ème carte insuffisante → espèces/CB | Écran complément sans "Autre carte" |
| 36 | Même carte que la 1ère | Rejet "Même carte" |
| 37 | Carte inconnue | Rejet "Carte inconnue" |
| 38 | Carte anonyme (wallet_ephemere) | Cascade sur éphémère, OK |
| 39 | Max 2 cartes | Après 2 insuffisantes → espèces/CB only |

### G. Adhésions cascade (5 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 40 | Adhésion cascade TNF→TLF | LigneArticle + Membership créée |
| 41 | Adhésion + vente même panier | Membership + vente, même uuid |
| 42 | Adhésion non-fiduciaire TIM | Direct TIM + Membership |
| 43 | Adhésion cascade insuffisante → complément | Membership créée après complément |
| 44 | Adhésion + vente + RC gratuite | 3 types dans le même atomic |

### H. Recharges NFC (4 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 45 | RE payante bloquée | Garde existante |
| 46 | RC seule | Crédit direct, FREE |
| 47 | RC + vente cascade | Crédit + cascade, même uuid |
| 48 | RC crédite TIM + article débite TIM | Crédit AVANT débit dans l'atomic |

### I. Billetterie cascade (3 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 49 | Billet payé cascade NFC | Reservation + Ticket + LigneArticle cascade |
| 50 | Billet + bière mixte | Jauge + stock, même atomic |
| 51 | Billet cascade insuffisant → complément | Reservation après complément |

### J. Stock / inventaire (3 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 52 | Article avec stock splitté 2 lignes | Stock décrémenté 1 seule fois |
| 53 | Poids/mesure splitté | weight_quantity identique, stock 1 fois |
| 54 | WebSocket broadcast | 1 par produit, pas par ligne |

### K. HMAC / LNE (4 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 55 | N lignes cascade → N HMAC chaînés | Chaque ligne chaînée |
| 56 | HMAC ligne complémentaire | Dans la même chaîne |
| 57 | total_ht sur amount partiel | HT = amount / (1 + tva) |
| 58 | weight_quantity dans HMAC | Identique sur toutes les lignes split |

### L. Rapports et clôture (4 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 59 | cashless_detail par asset | TNF: X€, TLF: Y€ |
| 60 | Pas de double comptage | Total = sum(amount) |
| 61 | FEC groupé par uuid_transaction | 1 écriture par paiement |
| 62 | Correction 1 ligne parmi N | Reste inchangé |

### M. Impression (2 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 63 | Ticket cascade | Détail par asset |
| 64 | Ticket complémentaire | NFC + espèces |

### N. Price validation (4 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 65 | non_fiduciaire=True + asset=None | ValidationError |
| 66 | non_fiduciaire=True + asset=TLF | ValidationError |
| 67 | non_fiduciaire=True + asset=TIM | OK |
| 68 | non_fiduciaire=False + asset=TIM | asset ignoré |

### O. Edge cases (6 tests pytest)

| # | Cas | Attendu |
|---|-----|---------|
| 69 | Carte anonyme cascade | OK sur wallet_ephemere |
| 70 | Carte anonyme + TIM | Si tokens TIM → OK, sinon rejet |
| 71 | 2 assets TLF actifs (bug config) | .first(), pas de crash |
| 72 | Asset archivé dans cascade | Ignoré (active=True only) |
| 73 | Rescanne même carte après écran complément | Pas de double débit |
| 74 | Race condition atomic | Rollback complet |

### P. E2E Playwright (8 tests)

| # | Cas | Attendu |
|---|-----|---------|
| 75 | Cascade TNF+TLF → succès multi-soldes | Texte 2 soldes |
| 76 | Insuffisant → complément espèces → succès | DB: LE + CA |
| 77 | Insuffisant → 2ème carte → succès | DB: 2 cartes |
| 78 | Article TIM → succès | DB: asset=TIM |
| 79 | Mixte EUR+TIM → succès | DB: cascade + direct |
| 80 | Admin: checkbox non_fiduciaire → asset | Conditional JS |
| 81 | Admin: asset filtré TIM/FID | Pas TLF/TNF/FED |
| 82 | 2ème carte = même carte → erreur | Message affiché |

---

## 12. Décisions prises

| # | Décision | Raison |
|---|----------|--------|
| 1 | Ordre fixe TNF→TLF→FED, pas configurable | Couvre 99% des cas, simple |
| 2 | N LigneArticle par article (comme legacy) | Comptabilité précise par asset |
| 3 | qty décimale, amount entier (centimes) | Zéro risque d'arrondi sur les montants |
| 4 | Dernière ligne prend le reste de qty | Somme exacte garantie |
| 5 | Pas de fallback cross-devise (TIM→EUR) | Devises incommensurables |
| 6 | Tout ou rien si TIM/FID insuffisant | L'opérateur choisit le tarif |
| 7 | Max 2 cartes NFC (comme legacy) | UX simple |
| 8 | Crédit RC/TM AVANT débits dans l'atomic | Solde TIM à jour pour articles TIM |
| 9 | Stock décrémenté 1 fois par article | Pas par ligne partielle |
| 10 | Approche A : tout dans _payer_par_nfc() | FALC, pas d'abstraction éclatée |
| 11 | BooleanField non_fiduciaire sur Price | Explicite en DB |

---

## 13. Hors scope

- Ordre de cascade configurable par tenant
- Fallback TIM→EUR si solde TIM insuffisant
- Admin UX avancé pour créer des tarifs TIM/FID (tâche 9 Multi-Asset)
- 3ème carte NFC

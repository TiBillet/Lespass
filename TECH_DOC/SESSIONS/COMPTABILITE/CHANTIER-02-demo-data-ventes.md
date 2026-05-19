# Chantier 02 — Démo data : ventes comptables Option A

> Hub permanent app `comptabilite/`. Pour le contexte global, voir
> [`INDEX.md`](INDEX.md) et la spec du chantier 01 [`SPEC.md`](SPEC.md).
>
> **Date démarrage :** 2026-05-18
> **Branche :** `main-compta`
> **Statut :** ✅ **IMPLÉMENTÉ 2026-05-18** (22 lignes générées, total 995 € net, 6 tests pytest, 0 régression).

## 1. Objectif

Enrichir `Administration/management/commands/demo_data_v2.py` pour qu'il
génère, sur le tenant `lespass`, un **jeu de `LigneArticle` complet et à
chiffres ronds** couvrant **tous les cas que TiBillet sait tracer
comptablement**.

But : permettre de **valider visuellement** que l'admin
`/admin/comptabilite/cloturecaisse/`, les exports FEC, CSV, Excel, PDF et le
rapport temps réel produisent les bons agrégats, en quelques clics, sans
calculer mentalement.

## 2. Périmètre — Option A (« scope LigneArticle uniquement »)

On génère **13 cas** identifiés lors du panorama de session :

| # | Cas | `payment_method` | `status` | `sale_origin` | Lien |
|---|---|---|---|---|---|
| 1 | Billet event payé Stripe fédéré | `SF` | `PAID` | `LP` | `reservation` |
| 2 | Billet event payé Stripe non-fédéré | `SN` | `PAID` | `LP` | `reservation` |
| 3 | Billet event payé Stripe SEPA | `SP` | `PAID` | `LP` | `reservation` |
| 4 | Billet event payé Stripe récurrent | `SR` | `PAID` | `LP` | `reservation` |
| 5 | Réservation gratuite | `NA` | `FREERES` | `LP` | `reservation` |
| 6 | Billet avec code promo | `SF` | `PAID` + FK `promotional_code` | `LP` | `reservation` |
| 7 | Remboursement d'un billet (qty=-1) | identique | `REFUNDED` | `LP` | `reservation` |
| 8 | Avoir émis par admin (qty=-1) | identique | `CREDIT_NOTE` | `AD` | `reservation` |
| 9 | Adhésion en ligne | `SF` | `PAID` | `LP` | `membership` |
| 10 | Adhésion manuelle admin (CB / espèces / chèque / virement) | `CC` / `CA` / `CH` / `TR` | `PAID` | `AD` | `membership` |
| 11 | Adhésion récurrente Stripe (échéance) | `SR` | `PAID` | `WK` | `membership` |
| 12 | Vente monnaie locale (asset LE/LG via QR/NFC) | `LE` ou `LG` | `VALID` | `QR` / `NF` | `asset` UUID |
| 13 | Contribution crowdfunding | `SN` | `VALID` | `LP` | aucun |

### Hors scope (documenté dans [`../TODO/COMPTABILITE-inter-tenants.md`](../TODO/COMPTABILITE-inter-tenants.md))

- Versements bancaires entre tenants (`BankTransferService` V2)
- Recharges wallet fédéré pures (Stripe → asset sans adhésion)
- Trigger d'adhésion qui crédite un wallet en gift
- Remboursement de crowdfunding (pas implémenté)

→ Ces opérations seront ajoutées **après le chantier Fedow V2**. La démo
affichera un **warning explicite** à la fin de la commande pour signaler
ces trous.

## 3. Chiffres cibles (à viser pour les exports)

Total TTC final attendu : **1 000,00 €**, après tous les remboursements
et avoirs : **964,00 €**. Ventilation conçue pour vérification mentale.

| Type | Détail | Montant ligne TTC |
|---|---|---:|
| Billet Concert Jazz - Plein × 10 (TVA 10%) | `SF` Stripe fédéré | 200,00 |
| Billet Concert Jazz - Réduit × 5 (TVA 10%) | `SN` Stripe CC | 80,00 |
| Billet Concert Jazz - Offert × 2 | `NA` Gratuit | 0,00 |
| Billet Atelier - Normal × 4 (TVA 10%) | `CC` CB TPE | 120,00 (manuel admin) |
| Billet Atelier - Solidaire × 2 (TVA 10%) | `CA` Espèces | 20,00 (manuel admin) |
| **Sous-total billets** | | **420,00** |
| Adhésion 2026 × 8 (TVA 0%) | `SF` Stripe fédéré | 200,00 |
| Adhésion Soutien × 1 (TVA 0%) | `CH` Chèque | 50,00 |
| Adhésion par virement × 1 (TVA 0%) | `TR` Virement | 100,00 |
| Adhésion Stripe SEPA × 1 (TVA 0%) | `SP` Stripe SEPA | 30,00 |
| Adhésion Stripe récurrent × 1 (TVA 0%) | `SR` Stripe abo | (à valider — peut-être 0 pour clarté) |
| **Sous-total adhésions** | | **380,00** |
| Bière × 20 (TVA 20%) | `QR` QR/NFC | 100,00 |
| Soft × 10 (TVA 5,5%) | `LE` Local Euro | 40,00 |
| Sandwich × 10 (TVA 5,5%) | `LG` Local Gift | 60,00 |
| **Sous-total ventes QR/NFC** | | **200,00** |
| **Total TTC brut** | | **1 000,00** |
| Avoir admin sur 1 billet Plein (qty=-1) | `SF` `CREDIT_NOTE` | -20,00 |
| Remboursement Stripe sur 1 billet Réduit | `SN` `REFUNDED` (hors total TTC, section dédiée) | -16,00 |
| **Total TTC net** | | **964,00** |

### Vérifications mentales attendues

| Indicateur | Valeur attendue |
|---|---|
| Total TTC (compte général) | 980,00 € (1000 - 20 avoir, refunded sorti hors total) |
| Total HT | ~926,52 € |
| Total TVA | ~53,48 € |
| Détail TVA 20% (boissons) | TTC 100 → HT 83,33 + TVA 16,67 |
| Détail TVA 10% (billets) | TTC 400 (après avoir 20) → HT 363,64 + TVA 36,36 |
| Détail TVA 5,5% (food) | TTC 100 → HT 94,79 + TVA 5,21 |
| Adhésions hors TVA | 380,00 € |
| Section remboursements | -20,00 € avoir + -16,00 € refunded |

## 4. Implémentation

### 4.1 Architecture

Nouveau fichier importé par `demo_data_v2.py` :
```
Administration/management/commands/_demo_data_v2_ventes.py
```

Fonction principale :
```python
def seed_ventes_demo(tenant, *, reset=False, verbose=True):
    """
    Crée le jeu de demo de ventes comptables sur le tenant donné.
    Doit etre appele dans un tenant_context(tenant).

    reset : si True, supprime d'abord toutes les LigneArticle de demo
            (identifiees par marqueur dans le rapport_json ou par
            datetime cible)
    """
```

### 4.2 Options CLI

Les ventes sont generees **par defaut** dans tous les modes (`demo_data_v2`
sans arg, `--quick`, `--flush`). Trois options pour piloter :

```python
parser.add_argument(
    '--no-sales',
    action='store_true',
    help="Skip la generation des ventes comptables (sortie squelette seul).",
)
parser.add_argument(
    '--sales-only',
    action='store_true',
    help="Genere UNIQUEMENT les ventes (skip _handle_full / _handle_quick).",
)
parser.add_argument(
    '--reset-sales',
    action='store_true',
    help="Supprime les LigneArticle [DEMO] avant regeneration (etat propre).",
)
```

Exemples :
```bash
# Tout : fixtures full + ventes (par defaut)
manage.py demo_data_v2

# Restaurer le dump SQL + regenerer les ventes (plus rapide)
manage.py demo_data_v2 --quick

# Juste les fixtures, pas les ventes
manage.py demo_data_v2 --no-sales

# Juste les ventes (suppose que les tenants existent)
manage.py demo_data_v2 --sales-only --reset-sales
```

### 4.3 Tenant cible

`lespass` (validé en session 2026-05-18). Si le tenant n'existe pas, skip
avec warning. Si le tenant n'a pas les produits/events nécessaires
(`module_billetterie` ou `module_adhesion` désactivés), skip.

### 4.4 Datetime backdaté

Les `LigneArticle` ont `datetime = auto_now_add=True`. Pour les backdater,
patcher après création :
```python
LigneArticle.objects.filter(uuid__in=created_uuids).update(
    datetime=datetime_cible,
)
```

Datetime cible par défaut : **hier 14:00 heure locale**. → tombe dans la
fenêtre de la clôture journalière `J`.

### 4.5 Produits / events / adhésions requis

Le seed doit s'appuyer sur des produits déjà créés par `demo_data_v2`.
Choisir :
- 1 Event "Concert Jazz" avec 3 tarifs (Plein 20, Réduit 16, Offert)
- 1 Event "Atelier" avec 2 tarifs (Normal 30, Solidaire 10)
- 1 Adhésion "Adhésion 2026" à 25 €
- 1 Adhésion "Soutien" à 50 €
- 1 Adhésion "Adhésion AMAP" à 30 € (récurrente SEPA)
- 3 produits POS pour ventes monnaie locale : "Bière 5€" (TVA 20%),
  "Soft 4€" (TVA 5,5%), "Sandwich 6€" (TVA 5,5%)
- 1 Initiative crowd "Sauvons le piano" avec contribution 1 × 50€ — ou
  skip si module_crowdfunding inactif

Si certains produits manquent, log warning et skip le cas concerné.

### 4.6 Idempotence

Marqueur : tag la `LigneArticle` avec un commentaire dans une FK ou un
flag DB ? Non, on n'a pas ce champ. À la place, on identifie les lignes de
démo par leur **datetime** (hier 14:00 ± 1h) **ET** par un produit dont le
nom commence par `"[DEMO] "`. Les products créés par le seed démo ont ce
préfixe.

→ Le reset filtre :
```python
LigneArticle.objects.filter(
    datetime__date=hier.date(),
    pricesold__productsold__product__name__startswith="[DEMO] ",
).delete()
```

### 4.7 Avoir / Remboursement

L'avoir et le remboursement sont créés en appelant respectivement
`Reservation._creer_avoir()` et `Reservation.cancel_and_refund_resa()`
plutôt qu'en bricolant la `LigneArticle` à la main → reste cohérent avec
le code de prod, génère bien la qty=-1 et le status correct.

### 4.8 Warning final

À la fin de la commande, afficher :
```
====================================================================
Demo data comptable generee sur tenant 'lespass'.
13 cas crees, total TTC 980,00 EUR.

Cas NON couverts dans la compta TiBillet actuelle :
  - Versements bancaires inter-tenants → cf. TECH_DOC/SESSIONS/TODO/
  - Recharges wallet federe pures (Stripe -> asset)
  - Trigger adhesion -> credit wallet gift
  - Remboursements crowdfunding

Ces operations apparaissent dans fedow_core.Transaction (V2) mais pas
dans LigneArticle. Elles seront integrees apres le chantier Fedow V2.
====================================================================
```

## 5. Tests pytest à créer

`tests/pytest/test_demo_data_ventes.py` :

1. `test_seed_ventes_demo_cree_les_13_cas` : appelle le seed, vérifie
   qu'on a bien 13+ LigneArticle (ou compte par `payment_method`).
2. `test_seed_ventes_demo_idempotent` : 2 appels successifs avec
   `reset=True` produisent le même nombre de lignes.
3. `test_seed_ventes_demo_total_correct` : appelle
   `RapportComptableService` sur la période et vérifie `total = 98000`
   centimes (980,00 €).
4. `test_seed_ventes_demo_ventilation_tva` : 3 taux présents (5.5, 10, 20)
   avec montants attendus.
5. `test_seed_ventes_demo_avoir_et_remboursement` : section
   `remboursements` du rapport contient l'avoir (-2000c) et le refunded
   (-1600c).
6. `test_seed_ventes_demo_fec_equilibre` : export FEC produit, vérifier
   que somme(Debit) == somme(Credit) par écriture.

## 6. Critères d'acceptation

- [ ] Commande `manage.py demo_data_v2 --quick --with-sales` régénère la
  démo complète en moins de 60s
- [ ] Total TTC affiché dans `/admin/comptabilite/cloturecaisse/...` =
  980,00 €
- [ ] Export FEC contient toutes les payment_method utilisées + sections
  TVA + sections produits
- [ ] Export Excel ouvrable directement (pas de cellule cassée)
- [ ] Rapport temps réel affiche les 8 sections sans erreur
- [ ] Tests pytest passent (6 nouveaux + 52 existants = 58)

## 7. Notes pour la session d'implémentation

- Au moment de l'implémentation, vérifier que les modèles `Reservation`,
  `Membership`, `LigneArticle`, `Paiement_stripe` (pour SR) acceptent bien
  une construction "à la main" hors du flow Stripe normal (sans payment
  intent réel). Si une contrainte bloque (ex: `pricesold` doit avoir un
  prix Stripe ID), créer un produit "demo" qui contourne.
- Les signaux `pre_save_signal_status` sont automatiques. Pour passer une
  ligne en `PAID`, créer en `CREATED` puis `.status = PAID; .save()` →
  vérifier que le signal ne court-circuite pas.
- Si `--with-sales` est passé sans `--quick`, on suppose que
  `_handle_full` vient d'être lancé : les events/products existent.
- En cas d'erreur sur un cas, logger et continuer sur les suivants (mode
  best-effort). À la fin, résumé `N cas créés, M skippés`.

# Chantier — Redondance cascade fiduciaire `controlvanne/billing.py` vs `laboutik/views.py`

**Date** : 2026-05-05
**Statut** : 🟡 À reprendre — décision de refactoring en attente
**Branche** : `dev_vps`
**Contexte** : Review du merge `dev_vps` → `V2` (Mike). Découvert pendant l'analyse de `controlvanne/billing.py`.

---

## 1. Principe violé

> `controlvanne` ne doit pas réimplémenter la logique métier fedow/laboutik, il doit s'appuyer dessus.

Aujourd'hui, `controlvanne/billing.py` (426 lignes) duplique ~250 lignes de logique cashless cascade qui existe déjà dans `laboutik/views.py`.

---

## 2. Tableau des redondances

| Concept | `controlvanne/billing.py` | `laboutik/views.py` | Verdict |
|---|---|---|---|
| Constante ordre cascade | `_ordre_cascade()` lignes **42-46** | `ORDRE_CASCADE_FIDUCIAIRE` ligne **3137** | 🔴 Doublon strict |
| Résolution wallet client | `obtenir_contexte_cashless()` lignes **71-86** | `_obtenir_ou_creer_wallet(carte)` lignes **947-981** | 🔴 Doublon strict |
| Boucle solde cascade | `calculer_solde_total_cascade()` lignes **107-121** | Inline `views.py:5292-5302` | 🟡 Algorithme dupliqué |
| Boucle débit cascade | `facturer_tirage()` lignes **214-244** | Phase 4 + 7c `views.py:5384-5443` + `5552-5571` | 🟡 Algorithme dupliqué |
| Mapping asset → PaymentMethod | `LOCAL_EURO` en dur ligne **301** | `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD` lignes **3143-3149** | 🚨 **Bug fonctionnel** (voir §3) |
| Wallet receveur | `WalletService.get_or_create_wallet_tenant(tenant)` ligne **221** | Idem `views.py:5530` | ✅ Helper partagé bien utilisé |
| Sync fedow_django | Lignes **345-413** | Absent | ⚠️ Logique inventée par Mike — à challenger |
| Création N LigneArticle par cascade | Une seule LigneArticle ligne **294-307** | `_creer_lignes_articles_cascade()` ligne **3728** crée N LigneArticle | 🚨 Régression conformité LNE |

---

## 3. Bug fonctionnel à corriger

`controlvanne/billing.py:294-307` crée **une seule `LigneArticle`** avec `payment_method=PaymentMethod.LOCAL_EURO`, quels que soient les assets débités.

Or laboutik distingue (ligne 3143-3149) :
```python
MAPPING_ASSET_CATEGORY_PAYMENT_METHOD = {
    Asset.TNF: PaymentMethod.LOCAL_GIFT,  # LG — cadeau
    Asset.TLF: PaymentMethod.LOCAL_EURO,  # LE — local
    Asset.FED: PaymentMethod.LOCAL_EURO,  # LE — fédéré
}
```

**Conséquence concrète** : pinte payée 1€ TNF + 3€ TLF → enregistrée comme **4€ LOCAL_EURO** au lieu de **1€ LOCAL_GIFT + 3€ LOCAL_EURO**. Les rapports clôture (Ticket X, ventilation moyens de paiement, chaînage HMAC LNE) sont **faussés** sur les ventes tireuse.

---

## 4. Fichiers à ouvrir dans PyCharm

```
controlvanne/billing.py:30-122       — cascade + wallet de Mike
controlvanne/billing.py:170-344      — facturer_tirage (à refondre)
laboutik/views.py:947                — _obtenir_ou_creer_wallet (à réutiliser)
laboutik/views.py:3137               — ORDRE_CASCADE_FIDUCIAIRE (à réutiliser)
laboutik/views.py:3143               — MAPPING_ASSET_CATEGORY_PAYMENT_METHOD (à réutiliser)
laboutik/views.py:3728               — _creer_lignes_articles_cascade (à réutiliser)
laboutik/views.py:5275-5443          — vue paiement NFC laboutik = la référence
laboutik/views.py:5505-5582          — bloc atomic cascade (Phase 7) = à factoriser
```

---

## 5. Trois options de refactoring

### Option 1 — Service partagé (le plus propre)

Créer `laboutik/services/cashless_payment.py` (ou `fedow_core/cascade_service.py`) qui expose :
- `obtenir_ou_creer_wallet(carte)` (déplacé depuis `laboutik/views.py:947`)
- `ORDRE_CASCADE_FIDUCIAIRE`, `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD` (constantes publiques)
- `creer_lignes_articles_cascade(...)` (déplacé depuis `laboutik/views.py:3728`)
- `payer_panier_cascade(panier, carte, point_de_vente, ip) -> dict` qui exécute Phase 1→7 atomique et retourne `{transactions, lignes_articles, montant_centimes}`

`controlvanne/billing.py` devient ~30 lignes : construit un panier à 1 article (le tirage en cl avec `weight_quantity`) et appelle `payer_panier_cascade()`.

**Pour** : zéro duplication, conformité LNE garantie, testé une seule fois.
**Contre** : touche à du code conformité LNE certifié (Phase ⑤ PLAN_LABOUTIK), donc session dédiée + tests E2E laboutik à rejouer.

### Option 2 — Exposer publiquement les helpers `laboutik`

Renommer `_obtenir_ou_creer_wallet` → `obtenir_ou_creer_wallet`, `_creer_lignes_articles_cascade` → `creer_lignes_articles_cascade`. Extraire la Phase 7 dans `executer_paiement_cascade(...)`. `controlvanne` importe directement depuis `laboutik.views`.

**Pour** : moins invasif que Option 1.
**Contre** : couple `controlvanne` à l'organisation interne de `laboutik/views.py` (déjà 7000+ lignes). Pas terrible architecturalement.

### Option 3 — Minimum viable pour le merge

`controlvanne/billing.py` importe `ORDRE_CASCADE_FIDUCIAIRE`, `MAPPING_ASSET_CATEGORY_PAYMENT_METHOD`, `_obtenir_ou_creer_wallet` depuis `laboutik.views`. Corrige le bug PaymentMethod en créant **N LigneArticle** au lieu de 1 (une par asset débité, avec qty proportionnelle via `_calculer_qty_partielles`).

**Pour** : débloque le merge `dev_vps` → `V2` sans dériver le scope.
**Contre** : la boucle débit cascade reste dupliquée. Dette technique connue.

---

## 6. Recommandation

**Option 1** est la cible. **Option 3** est le compromis si on veut merger `dev_vps` rapidement sans toucher au code certifié LNE.

À décider avec le mainteneur après exploration complète du chantier `dev_vps`.

---

## 7. Question annexe à creuser

**Sync fedow_django** dans `controlvanne/billing.py:345-413` (push vers "Ma Tirelire" pour les débits FED). Cette logique n'existe pas dans `laboutik/views.py`. Trois hypothèses :

1. Mike a inventé cette logique → faut-il la généraliser à laboutik ?
2. laboutik le fait via un signal qu'on n'a pas trouvé → vérifier `fedow_core/signals.py`
3. C'est une feature spécifique tireuse (les paiements POS classiques n'ont pas besoin d'apparaître dans Ma Tirelire) → décision métier à valider

À trancher avant de finaliser le refactoring.
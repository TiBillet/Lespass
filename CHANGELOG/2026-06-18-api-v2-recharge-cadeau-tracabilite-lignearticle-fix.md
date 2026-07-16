# API v2 recharge cadeau : traçabilité LigneArticle + fix 500 Fedow / API v2 gift refill: LigneArticle traceability + Fedow 500 fix

**Date :** 2026-06-18
**Migration :** Non / No

**Contexte / Context :** `POST /api/v2/wallet-refills/` ne fonctionnait **pas du tout** en réel
(500), mais les tests **mockaient Fedow** et le cachaient. L'endpoint Fedow réutilisé
(`refill_from_lespass_to_user_wallet`) est en fait celui de la **récompense d'adhésion** : son
serializer exige `ligne_article_uuid` + `membership_uuid` + `product_uuid` + `price_uuid`. Une
recharge cadeau directe n'a aucun de ces objets. De plus, aucune **trace comptable** n'était créée.

**Quoi / What :**
1. **Le fix Fedow (option C, sans toucher Fedow)** : le serializer Fedow prévoit un bypass via le
   flag `rewarded_from_ticket_scanned` (crédit direct sans contexte de vente, déjà utilisé pour les
   récompenses de scan de ticket). La vue le passe désormais dans le metadata → la recharge
   **crédite réellement** le wallet. Validé en intégration réelle (solde vérifié sur Fedow).
2. La vue crée une **LigneArticle de traçabilité** AVANT l'appel Fedow (un produit
   `RECHARGE_CASHLESS` par asset, tarif 0 €, `payment_method=FREE`) et passe son `uuid` dans le
   metadata. Comme une recharge offerte sur LaBoutik V1 : on trace tout ce qui est crédité.
3. Succès Fedow → ligne `VALID` ; échec → ligne `FAILED` + **502** propre (au lieu de la 500 brute).
   Pas de double-crédit (ligne `CREATED`, `_state.adding` → aucun trigger ; `trigger_R` commenté).
4. **Restriction d'assets alignée sur Fedow** : `REFILLABLE = {cadeau TNF, temps TIM, fidélité FID}`.
   **BADGE (BDG) retiré** (Fedow le refuse via `validate_asset`, et il n'est plus utilisé) ; euro
   (TLF) et fédéré (FED) rejetés en 422.
5. **Tests convertis en intégration RÉELLE** (plus de mock du crédit Fedow) : recharge de chaque
   type (cadeau/temps/fidélité) via l'API + **vérification du solde réel** sur Fedow, et idempotence
   réelle. La fixture crée les assets sur Fedow (comme l'admin : `wallet_origin = place.wallet` +
   `get_or_create_token_asset`). Mocks conservés uniquement pour simuler l'indisponibilité (503) et
   la panne Fedow (502), non reproductibles en réel.

**Pourquoi / Why :** auditer toute recharge (trou comptable) et rendre l'erreur Fedow propre et
traçable, **sans toucher au serveur Fedow** (option choisie par le mainteneur).

### Fichiers / Files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `WalletRefillViewSet` : flag `rewarded_from_ticket_scanned` (bypass Fedow) + `_creer_ligne_article_recharge` + `ligne_article_uuid` dans metadata + succès/échec (VALID/FAILED, 502) |
| `fedow_public/models.py` | `REFILLABLE_CATEGORIES` : retrait de `BADGE` (aligné sur `validate_asset` côté Fedow) |
| `tests/pytest/test_api_v2_wallet_refill.py` | Rejet FED testé (422) ; **tests d'intégration réels** (recharge cadeau/temps/fidélité + vérif solde Fedow + idempotence) via fixture `fedow_real_setup` (assets créés sur Fedow) ; test échec Fedow → 502 + ligne FAILED |

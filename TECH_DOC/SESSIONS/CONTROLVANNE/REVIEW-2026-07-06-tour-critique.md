# Review critique complète — controlvanne (2026-07-06)

> **MAJ même jour** : C1, C2, C3, I1, I2, I3, I4 **corrigés** en TDD —
> voir [CHANTIER-03-fixes-review.md](./CHANTIER-03-fixes-review.md).
> Les Minor restent en dette (section 🟡 ci-dessous).

Tour critique demandé par le mainteneur après les chantiers 1-2 : chasse aux
bugs, conformité djc, relecture intégrale — axes inventaire, templates, et
surtout transactions/Fedow. 3 reviewers indépendants (circuit monétaire,
stock/signaux, vues/templates/JS), findings contre-vérifiés dans le code
avant consignation.

## Verdict global

Le socle est sain : arithmétique centimes int exacte (conservation des sommes
dans la cascade multi-asset), verrous fedow_core corrects (pas de découvert
possible), isolation multi-tenant vérifiée, invariant débit/crédit/Transaction
respecté (`verify_transactions` passerait), XSS couvert (textContent partout,
token kiosk échappé), permissions admin complètes, piège « broadcast WS dans
atomic » évité. **Mais 3 bugs sérieux et 4 moyens à corriger avant un usage
réel en festival.**

## 🔴 Critical (à corriger avant prod)

### C1 — Double facturation possible sur pour_end/card_removed concurrents — CONFIRMÉ
`controlvanne/viewsets.py:470-476` (lecture session sans verrou) + `:523-553`

La session ouverte est lue par `.filter(ended_at__isnull=True).first()` sans
`select_for_update`, et le triptyque `close_with_volume` → décrément réservoir
→ `facturer_tirage` n'est pas dans une transaction commune (pas
d'`ATOMIC_REQUESTS`). Deux requêtes concurrentes (`pour_end` rejoué par le Pi
sur timeout, ou `pour_end`+`card_removed` chevauchés) passent toutes deux la
garde → **2 Transaction SALE, 2 jeux de LigneArticle, le client débité deux
fois** pour un seul tirage (le verrou Token empêche seulement le découvert).
Le rejeu séquentiel est sain (404 au 2e appel) — le trou est purement
concurrentiel.

**Fix proposé** : dans la branche `pour_end/card_removed`, `transaction.atomic()`
englobant + `RfidSession.objects.select_for_update().filter(pk=..., ended_at__isnull=True)`
et re-check avant facturation.

### C2 — Aucune reconnexion WebSocket : le kiosk 24/7 gèle à la première coupure — CONFIRMÉ
`controlvanne/static/controlvanne/js/panel_kiosk.js:232` (unique `new WebSocket`,
zéro `onclose`/`onerror` dans le fichier)

Un restart de daphne (déploiement, `supervisorctl restart daphne`) ou une
micro-coupure réseau fige TOUS les écrans kiosk en silence (jauges, solde,
autorisations) jusqu'à rechargement manuel de chaque Pi. Critique en
production festival — d'autant que le chantier 2 rend les restarts daphne
courants.

**Fix proposé** : `onclose`/`onerror` → retry avec backoff (1s → 30s max) +
bandeau « connexion perdue » sur le kiosk pendant la coupure.

### C3 — 500 au lieu d'un refus propre : carte sans wallet en tenant V2 — CONFIRMÉ
`laboutik/views.py:1073` (`raise Exception("Carte … inconnue de Fedow")` quand
ni `user.wallet` ni `wallet_ephemere` et `can_fedow()` False/carte inconnue du
legacy) + `controlvanne/viewsets.py:543` (`obtenir_contexte_cashless` appelé
**hors** du try/except)

- À l'`authorize` : carte présente en base mais jamais passée au POS → 500.
- Pire au `pour_end` : l'exception remonte APRÈS `close_with_volume` et le
  décrément réservoir (committés) → **bière servie, réservoir décrémenté,
  aucune facturation, 500 au Pi**.

Le billing de Mike supposait un `_obtenir_ou_creer_wallet` qui crée un wallet
éphémère local (proto V2) ; notre implémentation réelle (C-C, Fedow-legacy-
centrée) lève. Divergence proto/réel typique.

**Fix proposé** : englober `obtenir_contexte_cashless` dans le try du viewset
(refus loggé, pas de 500) ; et décider de la sémantique V2 : créer un wallet
éphémère local pour une carte inconnue du legacy quand `can_fedow()` est
False, OU refuser proprement en 200 `{authorized: false}`.

## 🟠 Important

### I1 — Les 3 compteurs (réservoir / Token fedow / Stock) divergent sur échec de facturation — CONFIRMÉ
`viewsets.py:527-532` : `reservoir_ml` décrémenté et committé AVANT
`facturer_tirage` (qui a son propre atomic pour débit + stock). Sur
`SoldeInsuffisant` (ou toute exception billing) : réservoir décrémenté,
monnaie intacte, stock intact. Fix naturel : même transaction que C1.

### I2 — Swap de fût sans Stock inventaire : `reservoir_ml` périmé — CONFIRMÉ
`signals.py:103-116` : le pre_save ne réinitialise `reservoir_ml` que si le
nouveau fût a un `Stock > 0`. Fût neuf sans Stock → le réservoir garde la
valeur de l'ancien fût (« fût vide » prématuré côté kiosk). Atténué par
`reservoir_illimite=True` par défaut.

### I3 — `volume_ml` négatif accepté sur pour_update/pour_start — CONFIRMÉ
`serializers.py:77-83` (pas de `min_value=0`) : un Pi défaillant peut pousser
« -100 cl » sur le kiosk. Seul `close_with_volume` clampe. Fix : `min_value`
sur le serializer.

### I4 — Volume affiché 0 en fin de tirage court — CONFIRMÉ
`viewsets.py` : `dernier_volume_ml` n'est mis à jour que par `pour_update` ;
un tirage < 1 intervalle d'update affiche « 0 cl » servi alors que la
facturation est correcte. Fix : `close_with_volume` met aussi à jour
`dernier_volume_ml`.

## 🟡 Minor (dette, à traiter à l'occasion)

1. La cascade importée inclut `Asset.FED` (`ORDRE_CASCADE_FIDUCIAIRE`) — inerte
   tant que « jamais de FED local » tient, mais aucun garde-fou dans billing.py.
2. Décrément `reservoir_ml` en read-modify-write Python (pas `F()`) — faible
   risque (1 bec = 1 flux), incohérent avec le pattern stock.
3. `except Exception: pass` autour du décrément stock DANS l'atomic
   (`billing.py:313-326`) : une vraie erreur DB avalée → `TransactionManagementError`
   au commit ; et un échec stock silencieux alors que l'argent est pris.
4. Arrondi `volume_cl = round(ml/10)` : tirages < 5 ml jamais décrémentés du
   stock (dérive stock/réservoir lente).
5. `reservoir_ml` décrémenté même si `reservoir_illimite=True` (sans effet sur
   l'autorisation, jauge trompeuse).
6. i18n absente sur toute l'UI calibration + filtre admin date range
   (4 templates 100 % FR en dur — vues staff, règle projet non respectée).
7. N+1 sur 5 des 8 ModelAdmin (historiques sans `select_related("tireuse_bec")`
   — le pattern correct existe dans `TireuseBecAdmin`).
8. `MouvementStock.quantite_avant` lu en mémoire (audit périmé si 2 tireuses
   partagent un fût — FK, pas OneToOne).

## Axes vérifiés sains (preuves dans les rapports des reviewers)

Arithmétique centimes/Decimal exacte, conservation cascade (`Σ parts = total`,
`Σ qty = 1`), pas de découvert (verrou Token), pas de fuite cross-tenant
(assets filtrés par `tenant_origin`/fédération), invariant débit+crédit+
Transaction atomique, garde FakeTenant du signal PairingDevice, pas de
récursion post_save, broadcast WS hors atomic, fût sans Stock ne crashe pas,
XSS couvert (textContent, escape+iri_to_uri sur le token kiosk), templates
kiosk conformes (i18n/aria/data-testid/data-*), 4 permissions sur les 9
admins, helpers hors classe.

## Suite proposée → CHANTIER-03

1. Fix C1+I1 ensemble (transaction atomique + verrou session autour de
   close/réservoir/facturation) — TDD avec test de concurrence.
2. Fix C3 (try englobant + décision mainteneur sur la sémantique wallet
   éphémère V2).
3. Fix C2 (reconnexion WS kiosk).
4. I2/I3/I4 (petits, à grouper).
5. Minors en dette listée.

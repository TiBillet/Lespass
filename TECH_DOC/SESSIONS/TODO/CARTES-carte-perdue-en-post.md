# Cartes — Boutons « carte perdue » en POST (et plus en GET)

> **Status :** idée posée, **spec à écrire**. Rien n'est codé.
> **Date :** 2026-10-11 (relectures Fable + Opus du correctif BILLETTERIE-COOP-TW).
> **Pré-requis :** aucun.

## Aujourd'hui (vérifié dans le code)

Les deux boutons « carte perdue » modifient l'état avec une requête **GET** :
- usager : `MyAccount.lost_my_card` (`BaseBillet/views.py`), appelé en `hx-get` depuis
  `pages/templates/pages/{classic,V2}/vues/compte/partials/card_table.html` et
  `pages/templates/pages/V2/vues/compte/index.html` ;
- admin : `MyAccount.admin_lost_my_card`, appelé en `hx-get` depuis
  `Administration/templates/admin/membership/wallet_info.html`.

Les deux appellent `declarer_la_carte_perdue` : la carte est détachée chez Fedow et dans
Lespass, et retirée des cartes primaires de caissier de tous les lieux.

## Le risque

`SessionAuthentication` (DRF) n'applique la protection CSRF qu'aux méthodes non sûres
(POST, PUT, DELETE…). Un GET n'est pas protégé. Une simple balise
`<img src="https://<lieu>/my_account/<uuid>:<numero>/admin_lost_my_card/">` sur une page
visitée par un admin connecté déclare la carte perdue à son insu. Il faut connaître l'uuid
du porteur et le numéro de carte. `SESSION_COOKIE_SAMESITE='Lax'` ne protège pas des
requêtes venant d'un même site, c'est-à-dire des autres sous-domaines `*.tibillet.coop`.
Même chose pour `lost_my_card` (seulement le numéro de carte, sur la carte de l'usager
connecté).

## À faire

1. Passer les deux actions en `@action(..., methods=['POST'])`.
2. Passer les 4 boutons en `hx-post` (le jeton CSRF est déjà posé par
   `hx-headers='{"X-CSRFToken": ...}'` sur le `<body>` des skins ; à vérifier dans le
   gabarit admin Unfold).
3. Garder `hx-disabled-elt="this"` (anti double clic, posé le 2026-10-11).
4. Ajouter un `hx-confirm` (« Déclarer cette carte perdue ? »), l'action étant
   irréversible depuis l'interface.
5. Tests : un GET doit répondre 405 ; adapter
   `tests/pytest/test_carte_perdue_cycle_complet.py` et
   `tests/pytest/test_vues_carte_branchees_sur_service.py` (POST + jeton CSRF), et l'E2E
   `tests/e2e/test_carte_perdue_recharge_fed.py`.

## À vérifier dans la spec

- Aucun autre appelant de ces deux URL (app mobile, LaBoutik V1, liens dans des mails).
- Les autres actions de `MyAccount` qui modifient l'état en GET (`refund_online`…) : même
  traitement, ou fiche à part.

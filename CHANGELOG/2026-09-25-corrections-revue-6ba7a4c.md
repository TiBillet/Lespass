# Corrections issues de la revue 6ba7a4c..HEAD / Fixes from the 6ba7a4c..HEAD review

**Date :** 2026-09-25
**Migration :** Non

## Resume / Summary

**Quoi / What :** sept corrections (3 critiques, 4 majeures) trouvées par la revue des
commits depuis `6ba7a4c`. Le point « recharge cadeau depuis tous les PV » est volontairement
laissé tel quel (décision du mainteneur).
/ Seven fixes (3 critical, 4 major) from the review. The "gift top-up from every POS"
  point is left as is on purpose.

### 1. Recharge temps (TM) : plus jamais vendue comme un article normal
**Pourquoi / Why :** `RECHARGE_TEMPS` était seulement commenté dans `METHODES_RECHARGE`,
mais le signal Asset créait toujours un produit TM (tarifs en euros). Il s'affichait comme
un article normal : payé en euros, aucun temps crédité.
**Correction / Fix :** `Asset.TIM` retiré de `CATEGORY_TO_RECHARGE` (plus de création) ;
les produits TM déjà en base sont masqués (`_construire_donnees_articles`) et refusés dans
un panier (`_extraire_articles_du_panier`).

### 2. Vente au poids/mesure : le serveur recalcule le prix
**Pourquoi / Why :** le montant calculé par `tarif.js` était accepté tel quel (seul `> 0`
était vérifié). Un client modifié pouvait vendre 1 kg à 1 centime. Sans quantité, l'article
était même vendu au prix d'un kilo entier.
**Correction / Fix :** `_montant_poids_mesure_en_centimes()` recalcule depuis la quantité
saisie (`weight-…`) et le prix de référence (÷1000 pour les grammes, ÷100 pour les cl,
arrondi `ROUND_HALF_UP`). Le montant du JS est ignoré (un écart est journalisé). Une ligne
sans quantité valide est ignorée.

### 3. Double appui sur « Valider » : un seul encaissement
**Pourquoi / Why :** rien n'empêchait deux POST `payer` pour le même panier.
**Correction / Fix :** deux couches.
- Client : `hx-sync="this:drop"` + `hx-disabled-elt="#bt-valider-layer2"` sur
  `#addition-form`, `#complement-form`, `#card-recharge-form`.
- Serveur : une clé d'idempotence (`cle_idempotence_paiement`) est créée à chaque
  affichage des moyens de paiement (champ hors bande dans `#addition-form`) et dans le
  formulaire de recharge. `payer()` et `payer_complementaire()` passent par
  `_executer_avec_cle_idempotence()` : verrou PostgreSQL de session
  (`pg_advisory_lock`), puis « des LigneArticle portent-elles déjà cette clé ? ». Si oui,
  rien n'est rejoué. Sinon la clé devient l'`uuid_transaction` des lignes.
  Pas d'`atomic()` englobant (ne change pas ce qui est annulé en cas d'erreur), pas de
  `cache.add()` (une panne memcached bloquerait tous les paiements).
  Sans clé (ancien client), le paiement marche comme avant.

### 4. Icônes : plus effacées en silence à l'enregistrement dans l'admin
**Pourquoi / Why :** la migration 0006 écrivait 6 noms absents de `ICON_POS`
(`apps`, `calendar_month`, `image`, `ink_eraser`, `point_of_sale`, et le repli `category`).
Le sélecteur ne cochait rien, le navigateur n'envoyait rien : l'icône était effacée.
**Correction / Fix :** les 6 noms ajoutés à `ICON_POS` ; le widget affiche une icône hors
liste comme option cochée (le `ChoiceField` demande alors d'en choisir une, au lieu
d'effacer) ; un test vérifie que toute sortie de la migration est dans `ICON_POS`.

### 5. Memcached : une panne ne ressemble plus à un verrou déjà pris
**Pourquoi / Why :** avec `ignore_exc: True`, `cache.add()` renvoie `False` en cas de
panne. La tâche d'onboarding croyait le lieu « déjà en cours » et s'arrêtait sans erreur
(lieu jamais créé) ; un jeton SSO valide était refusé comme un rejeu.
**Correction / Fix :** alias de cache `verrous` (même serveur, mêmes clés, sans
`ignore_exc`) pour le claim `create_tenant_from_draft` et le jeton SSO. En cas de panne,
la tâche écrit l'erreur dans `wc.error_message` (visible à l'écran) puis lève l'exception.
Au passage : `worker_process_init` (Celery) ferme les sockets memcached héritées du
processus maître après le fork (le `close()` vide ne le faisait plus).

### 6. Menu burger et titre du PV : de vrais boutons
**Pourquoi / Why :** le burger portait `aria-hidden="true"` avec `role="button"` : caché
aux lecteurs d'écran, sans focus clavier. `#header-title` était un `div onclick`.
**Correction / Fix :** deux `<button type="button">` avec `aria-controls` et
`aria-expanded` (mis à jour par `toggleMenuBurger` / `hideMenuBurger`), cible 44 px,
anneau `:focus-visible`, style natif du bouton retiré (rendu inchangé).

### 7. Popup de tarif : ne remplace plus la grille d'articles
**Pourquoi / Why :** la popup remplaçait `#products` puis restaurait l'ancien HTML : badge
de quantité jamais incrémenté, mises à jour de stock (WebSocket) écrasées.
**Correction / Fix :** la popup est ajoutée à la fin de `#products` ; les tuiles restent
dans le DOM, `inert` sous le voile. Le défilement est remis en haut et bloqué pendant la
popup, puis rendu à la fermeture. Focus sur le premier tarif, Échap ferme, focus rendu à la
tuile. Elle reste dans `#products` (pas `#messages`) : `#messages` couvre tout l'écran,
panier compris, et reçoit les réponses HTMX de paiement.

### Fichiers modifies / Modified files

| Fichier / File | Changement / Change |
|---|---|
| `fedow_core/signals.py` | `Asset.TIM` retiré de `CATEGORY_TO_RECHARGE` |
| `laboutik/views.py` | Filtre TM (tuiles + panier) ; `_montant_poids_mesure_en_centimes()` ; `_lire_cle_idempotence_paiement()`, `_executer_avec_cle_idempotence()` ; `payer` / `payer_complementaire` en enveloppe, corps dans `_executer_paiement` / `_executer_paiement_complementaire` ; `uuid_transaction_impose` dans les `_payer_*` ; clé dans le contexte des moyens de paiement et de la recharge |
| `laboutik/templates/laboutik/partial/hx_display_type_payment.html` | Champ hors bande `#addition-cle-idempotence` |
| `laboutik/templates/cotton/addition.html` | Champ `cle_idempotence_paiement` ; `hx-sync`, `hx-disabled-elt` |
| `laboutik/templates/laboutik/partial/hx_complement_paiement.html` | `hx-sync`, `hx-disabled-elt` |
| `laboutik/templates/laboutik/partial/hx_card_recharge.html` | Clé d'idempotence ; `hx-sync`, `hx-disabled-elt` |
| `laboutik/static/js/addition.js` | Vide la clé à la remise à zéro du panier |
| `Administration/admin/products.py` | 6 icônes ajoutées à `ICON_POS` ; `IconPickerWidget` signale une valeur hors liste |
| `Administration/templates/admin/widgets/icon_picker.html` | Option cochée pour une icône hors liste |
| `TiBillet/settings.py` | Alias de cache `verrous` |
| `TiBillet/cache_memcached.py` | `fermer_les_connexions_pour_de_vrai()` |
| `TiBillet/celery.py` | Handler `worker_process_init` |
| `onboard/tasks.py` | Claim via `caches["verrous"]`, erreur écrite si le cache est en panne ; commentaires « Redis » corrigés |
| `onboard/views.py` | Jeton SSO via `caches["verrous"]` |
| `laboutik/templates/cotton/header.html` | Burger et `#header-title` en `<button>`, `aria-expanded` |
| `laboutik/static/css/header.css` | Reset des boutons, cible 44 px, `:focus-visible` |
| `laboutik/static/js/tarif.js` | Popup ajoutée (plus de remplacement), `inert`, défilement, focus, Échap |
| `laboutik/static/css/tarif.css` | `#products.tarif-popup-ouverte { overflow: hidden }` |
| `tests/pytest/test_laboutik_recharge_temps_desactivee.py` | **Nouveau** (2 tests) |
| `tests/pytest/test_poids_mesure_prix_serveur.py` | **Nouveau** (6 tests) |
| `tests/pytest/test_paiement_idempotence.py` | **Nouveau** (6 tests) |
| `tests/pytest/test_asset_recharge_signal.py` | Asset TIM : aucun produit créé |
| `tests/pytest/test_laboutik_icones.py` | +3 tests (migration ⊂ ICON_POS, widget hors liste) |
| `onboard/tests/test_create_tenant_task.py` | +1 test (cache des verrous en panne) |
| `tests/e2e/test_tarif_popup.py` | +6 tests (Échap, focus, grille inerte, badge) |

## Tests a realiser / Tests to run

### Automatiques (deja verts dans la worktree) / Automated (green in the worktree)
```bash
docker exec lespass_django poetry run pytest tests/pytest/test_laboutik_recharge_temps_desactivee.py tests/pytest/test_poids_mesure_prix_serveur.py tests/pytest/test_paiement_idempotence.py tests/pytest/test_laboutik_icones.py tests/pytest/test_asset_recharge_signal.py -v
docker exec lespass_django poetry run pytest onboard/tests/test_create_tenant_task.py -v
docker exec lespass_django poetry run pytest tests/e2e/test_tarif_popup.py -v
```

### Manuels, sur la vraie caisse / Manual, on the real POS
1. **Double appui** : panier avec 1 article → VALIDER → ESPÈCE → taper deux fois très vite
   sur « Valider ». Attendu : une seule vente dans l'écran Ventes.
2. **Recharge par la carte** : check carte → Recharger → tarif → Valider deux fois vite.
   Attendu : solde crédité une seule fois.
3. **Complément 2 cartes + reste en espèces** : carte 1 insuffisante → 2ᵉ carte
   insuffisante → reste en espèces → Valider. Attendu : paiement accepté (la clé est
   réutilisée entre les deux passages, rien n'est bloqué à tort).
4. **Vente au poids** : tarif au poids, saisir 350 g à 20 €/kg → panier à 7,00 €.
5. **Popup de tarif** : article multi-tarif, faire défiler la grille vers le bas, ouvrir la
   popup → le voile couvre bien la zone visible ; ajouter 2 tarifs fixes → le badge de la
   tuile affiche 2 à la fermeture ; Échap ferme ; la grille défile de nouveau.
6. **Burger au clavier** : sur petit écran, Tab jusqu'au burger → Entrée ouvre le menu,
   le lecteur d'écran annonce « Menu, bouton, développé ». Vérifier que le rendu visuel du
   burger et du titre du PV n'a pas bougé.
7. **Admin icônes** : un produit avec l'icône `point_of_sale` → la modifier (autre champ),
   enregistrer → l'icône est conservée.
8. **Memcached coupé** (`docker stop` du conteneur memcached, en dev) : relancer un
   onboarding → l'écran affiche « Cache (verrou) indisponible, reessayez » au lieu de
   tourner sans fin. Les pages publiques continuent de marcher (cache `default`).

### Migration
- **Migration necessaire / Migration required :** Non
- Les nouveaux libellés `_()` (icônes, message « paiement déjà enregistré ») ne sont pas
  encore dans les `.po` : à traduire par le mainteneur.

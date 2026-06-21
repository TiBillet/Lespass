# Dette technique — Chantier admin modulaire (post C-A)

Date : 2026-06-20. Dette accumulée en rendant l'admin laboutik/inventaire fonctionnel pendant C-A.

## Contexte

L'admin de `lespass-main` a été refactorisé **monolithique → modulaire** : `admin_tenant.py`
réduit à un shim (906 o) + **18 modules** dans `Administration/admin/*.py`. La branche `Lespass`
(V1) est restée **à mi-chemin** : `admin_tenant.py` encore **monolithique (180 Ko, 28 `@register`)**
+ quelques modules extraits. Pour rendre l'admin fonctionnel sans tout migrer, on a fait le
minimum — d'où cette dette.

## Livré en C-A (fonctionnel, validé Chrome + test client)

- `Administration/admin/products.py` réaligné sur la source → **POSProduct / FutProduct /
  CategorieProduct actifs** (étaient commentés car les champs POS du modèle n'existaient pas avant).
- Modules `laboutik.py` + `inventaire.py` copiés et **branchés** dans l'import de `admin_tenant.py`.
- `TermUser` : enregistrement **minimal** ajouté au monolithe (le dashboard référence son changelist).
- Templates copiés : `admin/widgets/` (palette/icon picker), `admin/inventaire/`, `admin/cloture/`,
  `admin/comptable/`, `cloture_detail.html`.
- `Administration/admin/dashboard.py` : helper **`_safe_rev`** sur les 66 `reverse_lazy` → un lien
  vers un admin **absent** devient `#` au lieu de faire planter tout l'admin (dashboard + sidebar).
- Fix `__str__` de `comptabilite.MappingMoyenDePaiement` (bug **pré-existant V1** : `get_payment_method_display()`
  sur un champ sans `choices`).
- Résultat : **58/59 changelists + change views OK** (`BaseBillet.tva` = 403 **by design**).

## Dette à résorber (lot dédié — après C-C si pas urgent)

1. **`_safe_rev` est PROVISOIRE.** Il masque les liens vers des admins **non portés** : `booking`,
   `controlvanne`, `cards`/`QrcodeCashless`. ⚠️ `controlvanne` et `booking` **n'ont pas de
   `models.py` en V1** (apps absentes/incomplètes). À terme : **porter ces apps+admins OU retirer
   leurs liens du `dashboard.py` V1**, puis **retirer `_safe_rev`** (revenir à `reverse_lazy`).
2. **`TermUser` minimal** → aligner sur `users.py` de lespass-main (⚠️ gérer le doublon `HumanUser`
   déjà enregistré par le monolithe `admin_tenant.py:1007`).
3. **`Administration/admin/fedow.py` (admin `AssetFedowPublic`) NON branché** : doublon avec
   `admin_tenant.py:3920`. À brancher seulement quand le monolithe sera vidé de cet enregistrement.
4. **Modularisation complète** : vider `admin_tenant.py` (180 Ko) vers `Administration/admin/*.py`
   comme lespass-main (12 modules manquants : `cards, configuration, crowds, events, fedow, membership,
   reservations, sales, settings_apps, tags, users`). ⚠️ Risque `AlreadyRegistered` — migrer
   **modèle par modèle** en vidant le monolithe au fur et à mesure.

## Piège runtime observé

Un **état de reload Daphne corrompu** est apparu (AlreadyRegistered au reload, alors que `manage.py
check` en process frais passait à 0). Cause : un fichier admin copié (`fedow.py`) chargé lors d'un
reload puis retiré, sans purge du registre admin. **Fix : restart propre du serveur** (`Ctrl+C` + `rsp`).
À garder en tête lors du chantier modulaire (beaucoup de reloads).

## Méthode recommandée (anti-doublon)

Module par module : (1) copier le module admin depuis lespass-main, (2) **retirer du monolithe**
les `@register` correspondants, (3) brancher l'import dans `admin_tenant.py`, (4) `check` + **restart**
(pas reload) + smoke du changelist. **Ne jamais porter en bloc** (doublons garantis).

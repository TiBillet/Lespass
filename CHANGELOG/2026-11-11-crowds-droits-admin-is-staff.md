# Crowds réservé aux admins du lieu, plafond de codes faux par IP retiré / Crowds reserved to venue admins, per-IP wrong-code cap removed

**Date :** 2026-11-11
**Migration :** Non

## Resume / Summary
**Quoi / What :**
1. Les actions de gestion d'un projet crowds sont réservées à l'admin du lieu ou au superuser : clôturer, archiver, marquer une contribution payée, valider ou rejeter une ligne de budget, valider une participation. Avant, n'importe quel compte connecté pouvait les faire. Le contrôle appelait `is_current_tenant_admin` sans `()`, donc il était toujours vrai.
2. `is_staff` ne donne plus aucun droit : ni dans `crowds/views.py`, ni dans les gabarits crowds, ni dans l'API v2 (valider ou rejeter un budget). Ce drapeau est partagé par tous les lieux, puisque le compte vit dans le schéma `public`. L'admin du lieu A l'a, il ne doit rien pouvoir faire sur le lieu B.
3. La règle est inscrite dans le skill `djc` : un droit d'admin se vérifie par `user.is_superuser or user.is_current_tenant_admin()`, jamais par `is_staff`.
4. Guichet : le plafond de codes faux par adresse IP (N-1 du 2026-11-09, réglage `CONNEXION_CODE_PLAFOND_ECHECS_IP_10_MIN`) est retiré. Derrière le wifi d'un festival, une seule personne pouvait bloquer la connexion de tout le monde pendant 10 minutes. Retour à la décision d'origine (CHANTIER-02 : pas de plafond par IP sur la vérification). Le réglage disparaît de `settings.py` et `env_example` : s'il a été posé dans un `.env`, il est ignoré.

/ 4. Per-IP wrong-code cap removed (festival wifi). 1. Crowds management actions are now venue-admin or superuser only; the check called a method without `()` and was always true. 2. `is_staff` grants nothing anymore (crowds views, templates, API v2): it is shared by all venues. 3. Rule added to the `djc` skill.

**Pourquoi / Why :** relecture de sécurité du chantier OTP (R-1). Avec la connexion par code, créer un compte prend 30 secondes.
/ Security review of the OTP work. With code login, creating an account takes 30 seconds.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `crowds/views.py` | 7 contrôles : `is_superuser or is_current_tenant_admin()` |
| `crowds/templates/crowds/views/detail.html`, `partial/budget_items.html`, `partial/participations.html` | `is_staff` retiré des conditions d'affichage des boutons de gestion |
| `api_v2/views.py` | Budget validé ou rejeté via l'API : admin du lieu ou superuser |
| `tests/pytest/test_crowds_actions_reservees_aux_admins.py` | Nouveau : non-admin et admin d'un autre lieu refusés, admin du lieu accepté |
| `TECH_DOC/SKILLS/djc/SKILL.md`, `references/viewset-patterns.md` | Règle « `is_staff` est banni » |
| `AuthBillet/connexion_par_code.py`, `AuthBillet/views_sso.py`, `TiBillet/settings.py`, `env_example`, `tests/pytest/test_connexion_par_code.py` | Plafond de codes faux par IP retiré, avec son test |

Aucune nouvelle chaîne traduisible. Chaîne devenue inutilisée : « Trop de codes faux depuis cette connexion. Réessayez dans 10 minutes. ».

---

## Comment tester (a la main) / Manual test
### Test 1 — compte connecté non admin
1. Se connecter avec un compte qui n'est pas admin du lieu. Ouvrir un projet crowds.
2. Attendu : aucun bouton de gestion (clôturer, archiver, valider un budget).
3. Poster à la main `/crowd/<uuid>/close/` (console du navigateur, avec le jeton CSRF). Attendu : 403, le projet reste ouvert.

### Test 2 — admin du lieu
1. Se connecter avec l'admin du lieu. Attendu : les boutons de gestion sont là et marchent.

### Verifs DB / Playwright
- `make test ARGS="tests/pytest/test_crowds_actions_reservees_aux_admins.py"`.

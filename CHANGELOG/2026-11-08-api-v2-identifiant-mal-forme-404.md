# API v2 : un identifiant mal formé donne un 404, plus un 500 / API v2: a malformed identifier gives a 404, not a 500

**Date :** 2026-11-08
**Migration :** Non
**Sentry :** BILLETTERIE-COOP-VX, BILLETTERIE-COOP-VY

## Resume / Summary
**Quoi / What :** `PATCH /api/v2/blocs/8d22a6b4-x/` (uuid tronqué) renvoyait un 500 : Django lève `ValidationError` en convertissant le texte en UUID pour le filtre. Les routes qui lisent un uuid dans l'URL passent maintenant par `get_objet_par_uuid_ou_404`, déjà utilisé par les events : blocs (4), initiatives (5), products, reservations et memberships (1 chacune). Un identifiant qui n'est pas un UUID donne un 404.
/ The 12 routes that read a uuid from the URL now use `get_objet_par_uuid_ou_404`: a non-UUID identifier gives a 404 instead of a 500.

**Pages : uuid OU slug partout.** `PATCH`, `DELETE` et `POST /api/v2/pages/{x}/blocs/` acceptent maintenant le slug de la page, comme le `GET` (`get_page_par_uuid_ou_slug_ou_404`, qui réutilise `_resoudre_page`). Un client faisait `PATCH /api/v2/pages/mentions-legales/` : 500, puis 404 alors que la page existe. Doc mise à jour (OpenAPI, `api_v2/GUIDELINES.md`, skill `tibillet-api`).
/ PATCH, DELETE and POST .../blocs/ on a page accept its slug, like GET.

**Pourquoi / Why :** le routeur DRF accepte n'importe quel texte à la place de l'uuid. Une ressource dont l'identifiant n'est pas un UUID ne peut pas exister : c'est un 404, pas une erreur du serveur.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `api_v2/views.py` | `BlocViewSet` (`retrieve`, `partial_update`, `destroy`, `ajouter_image`) : `get_objet_par_uuid_ou_404` ; `PageViewSet` (`partial_update`, `destroy`, `ajouter_bloc`) : nouvelle `get_page_par_uuid_ou_slug_ou_404` |
| `api_v2/views.py` | `CrowdInitiativeViewSet` (`retrieve`, `destroy`, `budget_items`, `votes`, `participations`), `ProductViewSet.retrieve`, `ReservationViewSet.retrieve`, `MembershipViewSet.retrieve` : `get_objet_par_uuid_ou_404` |
| `tests/pytest/test_pages_api.py` | `test_http_identifiant_qui_n_est_pas_un_uuid_renvoie_404` (7 routes pages et blocs) ; `test_http_page_modifiee_enrichie_puis_supprimee_par_son_slug` |
| `api_v2/openapi-schema.yaml`, `api_v2/GUIDELINES.md`, `TECH_DOC/SKILLS/tibillet-api/` | Routes de page : uuid ou slug |
| `tests/pytest/test_api_v2_identifiant_mal_forme.py` | Même test sur les 8 routes initiatives, products, reservations, memberships |

---

## Comment tester (a la main) / Manual test
1. `curl -sk -o /dev/null -w "%{http_code}\n" -X PATCH "https://lespass.tibillet.localhost/api/v2/blocs/8d22a6b4-x/" -H "Authorization: Api-Key <cle>" -H "Content-Type: application/json" -d '{"headline":"x"}'`
2. Attendu : `404`, et aucune erreur dans Sentry.
3. `curl -sk -X PATCH "https://lespass.tibillet.localhost/api/v2/pages/<slug-existant>/" -H "Authorization: Api-Key <cle>" -H "Content-Type: application/json" -d '{"name":"Nouveau titre"}'`
4. Attendu : `200`, le titre de la page a changé.

### Tests automatiques
`docker exec lespass_django poetry run pytest tests/pytest/test_api_v2_identifiant_mal_forme.py tests/pytest/test_pages_api.py -q -k "identifiant_qui_n_est_pas or par_son_slug"`

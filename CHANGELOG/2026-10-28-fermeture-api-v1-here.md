# Fermeture de `/api/here/` et correction de `logo_variations` / Removal of `/api/here/` and `logo_variations` fix

**Date :** 2026-10-28
**Migration :** Non

## Resume / Summary
**Quoi / What :** la route publique `/api/here/` (API v1, `HereViewSet`) est supprimée. Elle répond désormais 404.
/ The public v1 route `/api/here/` (`HereViewSet`) is removed and now returns 404.

**Pourquoi / Why :** aucun appelant, ni dans Lespass (templates, JS, vues, tests) ni dans les projets voisins (LaBoutik, Fedow, kiosk, Discovery, dolibarr). Seules d'anciennes collections Postman de `old-v2-proto` y faisaient référence. La route plantait en 500 (Sentry BILLETTERIE-COOP-VP) pour un lieu qui a un logo sans image principale : `Configuration.logo_variations()` lit `self.img` au lieu de `self.logo`.
/ No caller anywhere; the route crashed (500) for venues with a logo but no main image.

`logo_variations()` lit maintenant les variations du **logo** (`self.logo`), dans `Configuration` et `WaitingConfiguration`. Avant, elle renvoyait les URL de l'image principale, ou plantait si le lieu n'en avait pas.
/ `logo_variations()` now reads the **logo** variations instead of the main image ones.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `ApiBillet/urls.py` | Retrait de `router.register(r'here', ...)`. |
| `ApiBillet/views.py` | Suppression de `HereViewSet` et de l'import `MembershipProduct` devenu inutile. |
| `ApiBillet/serializers.py` | Retrait du commentaire « Utilisé par /here » devenu faux. |
| `BaseBillet/models.py` | `Configuration.logo_variations()` : `self.img` → `self.logo`. |
| `MetaBillet/models.py` | `WaitingConfiguration.logo_variations()` : `self.img` → `self.logo`. |
| `A TESTER et DOCUMENTER/managers-proxys-product.md` | Test 5 (`curl /api/here/`) marqué sans objet. |

---

## Comment tester (a la main) / Manual test
### Test 1 — la route est fermée
1. `curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/api/here/`
2. Attendu : `404`.

### Test 2 — le reste de l'API v1 répond toujours
1. `curl -sk -o /dev/null -w "%{http_code}\n" https://lespass.tibillet.localhost/api/events/`
2. Attendu : `200`.

### Test 3 — `logo_variations` lit le logo
1. `docker exec lespass_django poetry run python manage.py tenant_command shell -s lespass -c "from BaseBillet.models import Configuration; print(Configuration.get_solo().logo_variations())"`
2. Attendu : si le lieu a un logo, des URL qui contiennent le nom du fichier du logo (pas celui de l'image principale). Sinon `[]`.

### Verifs
- `docker exec lespass_django poetry run python manage.py check` → aucune erreur.

# Pages d'erreur 404/500 sur le tenant public / Error pages 404/500 on public tenant

**Date :** 2026-07-17
**Migration :** Non

## Resume / Summary
**Quoi / What :** Ajout de `handler404` / `handler500` dans `TiBillet/urls_public.py`
(ils n'existaient que dans `urls_tenants.py`).
Addition of `handler404` / `handler500` to `TiBillet/urls_public.py` (previously
only in `urls_tenants.py`).

**Pourquoi / Why :** Sur le tenant public (ex. `tibillet.fr`), une URL introuvable
(scan de bot sur `/.flaskenv`) declenchait un `Resolver404`. Faute de handler custom,
Django rendait `404.html`/`500.html` via ses vues par defaut, qui n'injectent PAS
`base_template`. Le `{% extends base_template %}` recevait `''` -> `TemplateSyntaxError`,
ce qui declenchait la page 500 (meme defaut) -> re-crash en boucle (Sentry BILLETTERIE-COOP-S3).
On the public tenant, a missing URL raised `Resolver404`; without a custom handler,
Django's default error views rendered the templates without `base_template`, causing
a `TemplateSyntaxError` loop.

### Fichiers modifies / Modified files
| Fichier / File | Changement / Change |
|---|---|
| `TiBillet/urls_public.py` | Declaration de `handler404` / `handler500` (copie de `urls_tenants.py`) |

---

## Comment tester (a la main) / Manual test

### Test 1 — 404 sur le tenant public (DEBUG=0)
1. Se placer en prod (ou `DEBUG=0`) sur le domaine du tenant public.
2. Requeter une URL inexistante, ex : `http://<domaine-public>/.flaskenv` ou `/nimportequoi`.
3. Attendu : une **page 404 rendue** (skin classic), statut 404, **pas** de `TemplateSyntaxError`
   ni de 500 en boucle dans Sentry.

### Test 2 — non-regression tenant normal
1. Sur un tenant normal, requeter une URL inexistante.
2. Attendu : la 404 skin-aware s'affiche comme avant (comportement inchange).

### Verifs
- `docker exec lespass_django poetry run python /DjangoFiles/manage.py check` -> 0 issue.
- Note : les handlers custom ne sont actifs que si `DEBUG=0` (comportement Django standard) ;
  en local `DEBUG=1`, Django affiche la page de debug technique, pas `404.html`.
